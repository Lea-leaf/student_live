# -*- coding: utf-8 -*-
"""JWT 认证与权限装饰器。

设计：
- 使用 PyJWT 自行签发/校验，token 载荷里带 uid / role / type / exp；
- `token_required`    必须登录（顺带校验封禁状态）；
- `admin_required`    必须管理员（RBAC 预留：角色集合来自 constants.ADMIN_ROLES）；
- `optional_token`    游客可访问，登录则注入 current_user；
- 登录用户通过 Flask 的 `g.current_user` 在整个请求周期内可用，
  方便操作日志统一记录「谁做的」。

扩展点：
- 未来接入 RBAC 分级，只需给 `admin_required` 传 roles 参数；
- 未来接入 Redis 黑名单，只需在 `_decode_token` 后加一层校验。
"""

from functools import wraps

import jwt
from flask import current_app, g, request

from .constants import ADMIN_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN
from .response import (
    CODE_ACCOUNT_BANNED,
    CODE_FORBIDDEN,
    CODE_TOKEN_EXPIRED,
    CODE_UNAUTHORIZED,
    error,
)

TOKEN_TYPE_ACCESS = 'access'
TOKEN_TYPE_REFRESH = 'refresh'


# ---------------------------------------------------------------------------
# 签发
# ---------------------------------------------------------------------------
def generate_token(user, token_type=TOKEN_TYPE_ACCESS, expires_delta=None):
    """为用户签发 JWT。

    :param user: User 实例
    :param token_type: access / refresh
    :param expires_delta: 覆盖默认有效期（timedelta）
    """
    from datetime import datetime

    now = datetime.utcnow()
    if expires_delta is None:
        expires_delta = (
            current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
            if token_type == TOKEN_TYPE_ACCESS
            else current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
        )
    payload = {
        'uid': user.id,
        'sub': str(user.id),          # 兼容标准 claim
        'student_id': user.student_id,
        'role': user.role,
        'type': token_type,
        'iat': now,
        'exp': now + expires_delta,
        'iss': current_app.config.get('JWT_ISSUER', 'school-life-platform'),
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'],
                      algorithm=current_app.config.get('JWT_ALGORITHM', 'HS256'))


def generate_token_pair(user):
    """同时签发 access / refresh token。"""
    return {
        'access_token': generate_token(user, TOKEN_TYPE_ACCESS),
        'refresh_token': generate_token(user, TOKEN_TYPE_REFRESH),
        'token_type': 'Bearer',
        'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()),
    }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _extract_token():
    """从 Authorization 头（或 ?token= 查询参数，便于下载类接口）取 token。"""
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:].strip()
    if header:
        return header.strip()
    return request.args.get('token')


def decode_token(token, verify_type=TOKEN_TYPE_ACCESS):
    """解码并校验 token，返回 payload；失败抛出 jwt 异常。"""
    payload = jwt.decode(
        token,
        current_app.config['JWT_SECRET_KEY'],
        algorithms=[current_app.config.get('JWT_ALGORITHM', 'HS256')],
        issuer=current_app.config.get('JWT_ISSUER', 'school-life-platform'),
        options={'verify_iss': True},
    )
    if verify_type and payload.get('type') != verify_type:
        raise jwt.InvalidTokenError('token 类型不匹配')
    return payload


def resolve_token():
    """解析当前请求的 token 并返回 (payload, err_response)。"""
    token = _extract_token()
    if not token:
        return None, error('缺少认证信息，请先登录', CODE_UNAUTHORIZED, http_status=401)
    try:
        return decode_token(token), None
    except jwt.ExpiredSignatureError:
        return None, error('登录已过期，请重新登录', CODE_TOKEN_EXPIRED, http_status=401)
    except jwt.InvalidTokenError as exc:
        return None, error(f'认证失败：{exc}', CODE_UNAUTHORIZED, http_status=401)


# ---------------------------------------------------------------------------
# 装饰器
# ---------------------------------------------------------------------------
def _load_user(payload, allow_banned=False):
    """按 payload 取用户，并做状态校验。"""
    from ..models import User

    user = User.query.get(payload.get('uid'))
    if user is None:
        return None, error('用户不存在或已注销', CODE_UNAUTHORIZED, http_status=401)
    if user.is_banned and not allow_banned:
        return None, error('账号已被封禁，请联系管理员', CODE_ACCOUNT_BANNED, http_status=403)
    return user, None


def token_required(view_func):
    """必须登录。"""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload, err = resolve_token()
        if err:
            return err
        user, err = _load_user(payload)
        if err:
            return err
        g.current_user = user
        g.jwt_payload = payload
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    """必须是管理员。

    扩展：`admin_required(roles=('auditor',))` 可按 RBAC 角色收窄，
    当前实现保持 `@admin_required` 无参用法，兼容后续改造。
    """
    roles = None
    if callable(view_func):
        pass
    else:  # 被当作 admin_required(roles=(...)) 调用
        roles = view_func
        view_func = None

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            payload, err = resolve_token()
            if err:
                return err
            user, err = _load_user(payload)
            if err:
                return err
            g.current_user = user
            g.jwt_payload = payload
            if not user.is_admin:
                return error('需要管理员权限', CODE_FORBIDDEN, http_status=403)
            if roles and user.role not in roles and user.role != ROLE_SUPER_ADMIN:
                return error('当前管理员角色无此权限', CODE_FORBIDDEN, http_status=403)
            return func(*args, **kwargs)

        return wrapper

    return decorator(view_func) if view_func else decorator


def super_admin_required(view_func):
    """最高权限（原型阶段 admin 即最高）。"""

    @admin_required
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = g.current_user
        if user.role not in (ROLE_ADMIN, ROLE_SUPER_ADMIN):
            return error('需要超级管理员权限', CODE_FORBIDDEN, http_status=403)
        return view_func(*args, **kwargs)

    return wrapper


def optional_token(view_func):
    """可选登录：游客也能访问。

    - 未带 token：g.current_user = None，交给视图按游客策略处理；
    - 带了有效 token：正常注入用户；
    - 带了无效 token：直接报错，避免「看似登录实为游客」的迷惑行为。
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        g.current_user = None
        if _extract_token():
            payload, err = resolve_token()
            if err:
                return err
            user, err = _load_user(payload)
            if err:
                return err
            g.current_user = user
            g.jwt_payload = payload
        return view_func(*args, **kwargs)

    return wrapper


def module_permission_required(module_code, permission='manage'):
    """模块级权限（RBAC 预留）。

    超级管理员通过一切；其他管理员需在 admin_module_access 表中有授权，
    未授权则按「原型阶段全模块可见」的默认策略放行，但会记录到 g.module_scope，
    方便后续收紧时不用改视图代码。
    """

    def decorator(view_func):
        @admin_required
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = g.current_user
            if not user.is_super_admin:
                from ..models import AdminModuleAccess

                access = AdminModuleAccess.query.filter_by(
                    user_id=user.id, module_code=module_code
                ).first()
                g.module_scope = access.permission if access else None
            else:
                g.module_scope = 'all'
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------
def current_user():
    """取当前登录用户（未登录返回 None）。"""
    return getattr(g, 'current_user', None)


def is_admin():
    user = current_user()
    return bool(user and user.is_admin)


__all__ = [
    'generate_token',
    'generate_token_pair',
    'decode_token',
    'token_required',
    'admin_required',
    'super_admin_required',
    'optional_token',
    'module_permission_required',
    'current_user',
    'is_admin',
    'ADMIN_ROLES',
    'TOKEN_TYPE_ACCESS',
    'TOKEN_TYPE_REFRESH',
]
