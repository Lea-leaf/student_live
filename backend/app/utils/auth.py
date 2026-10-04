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

from ..extensions import db
from .constants import ADMIN_ROLES
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


def admin_required(view_func=None, *, capability=None, roles=None):
    """必须是后台用户，且（可选）具备指定能力。

    两种用法：

        @admin_required                                  # 任何后台角色
        @admin_required(capability=CAP_POST_AUDIT)       # 需要「审核内容」能力
        @admin_required(roles=(ROLE_ADMIN,))             # 需要指定角色（少用）

    能力判定走 `constants.ROLE_PERMISSIONS`（角色 → 能力集合），
    超级管理员持有通配能力，因此永远通过。
    未通过时返回 403 / code 2003，与历史行为一致。

    历史说明：早期只判断 `user.is_admin`，而 `is_admin` 等同于「在 ADMIN_ROLES 里」，
    导致审核员一旦创建就拿到全部管理员权限。现在判定拆成两步：
    先看「能不能进后台」（is_staff），再看「能不能做这件事」（capability）。
    """
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
            if not user.is_staff:
                return error('需要管理员权限', CODE_FORBIDDEN, http_status=403)
            # 懒执行：管理员移交到期后，第一次访问后台接口时自动完成切换。
            # 放在这里而不是定时任务里，是为了不引入调度器依赖。
            _settle_due_handover(user)
            # 注意：**不再对冻结者一刀切 403**。
            # 冻结中的待上任管理员按"原角色"继续工作（原本是审核员就还能审帖），
            # 只是拿不到管理员那些能力 —— 由下面的 capability 判定自然挡住。
            # `user.is_frozen` 时 `is_admin` 为假、`capabilities` 取自原角色，
            # 因此这里无需特判，能力校验会给出准确的拒绝理由。
            if roles and not user.is_admin and user.role not in roles:
                return error('当前角色无此后台权限', CODE_FORBIDDEN, http_status=403)
            if capability and not user.has_capability(capability):
                return error('当前角色无此后台权限', CODE_FORBIDDEN, http_status=403)
            return func(*args, **kwargs)

        return wrapper

    # 兼容 `@admin_required`（直接装饰）与 `@admin_required(...)`（带参调用）两种写法
    if view_func is not None and callable(view_func):
        return decorator(view_func)
    return decorator


def _settle_due_handover(user):
    """若存在已到期的管理员移交，就地落地，并把当前用户的身份刷新一次。

    失败不阻断请求：只在后台接口这一层做结算，出问题也只是"晚一次生效"。
    """
    try:
        from .handover import finalize_due_handover, find_pending_handover

        initiator, target = find_pending_handover()
        if not initiator or not initiator.handover_effective_at:
            return
        if user.id not in (initiator.id, target.id):
            return
        done, _, _ = finalize_due_handover()
        if done:
            # 本请求的 g.current_user 还是旧快照，重新取一次，让权限立即正确
            from ..models import User

            db.session.expire_all()
            refreshed = User.query.get(user.id)
            if refreshed is not None:
                g.current_user = refreshed
    except Exception:  # noqa: BLE001 - 结算失败不影响本次请求本身
        db.session.rollback()


# ---------------------------------------------------------------------------
# 说明：早期有一个 `super_admin_required` 装饰器（"只有超级管理员能调"），
# 随 `super_admin` 档位一起移除了。它内部判的 `is_super_admin` 对 admin 本身就返回 True，
# 因此从来就等价于 `@admin_required`，只是多了一层"存在更高档位"的误导。
# 需要"最高级操作"语义时，直接用 `@admin_required(capability=...)`。
# ---------------------------------------------------------------------------


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
    """模块级权限（**预留 · 未启用**）。

    设计意图：管理员通过一切；其他后台角色需在 `admin_module_access` 表中有授权，
    未授权时**拒绝**（403）而不是放行 —— 早期实现是"未授权按全模块可见放行"，
    属于"预留设施默认开门"的隐患，已收紧为安全默认。

    ⚠️ 当前**零处调用**，且 `admin_module_access` 表没有任何写入接口，
    因此"按模块分权"实际尚未启用。要启用需先补授权写入接口，
    详见 docs/AUDIT.md 的 P8。
    """

    def decorator(view_func):
        @admin_required
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user = g.current_user
            if user.is_admin:
                g.module_scope = 'all'
                return view_func(*args, **kwargs)

            from ..models import AdminModuleAccess

            access = AdminModuleAccess.query.filter_by(
                user_id=user.id, module_code=module_code
            ).first()
            if access is None:
                return error(
                    f'未获得模块「{module_code}」的管理授权', CODE_FORBIDDEN, http_status=403
                )
            g.module_scope = access.permission
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
    'optional_token',
    'module_permission_required',
    'current_user',
    'is_admin',
    'ADMIN_ROLES',
    'TOKEN_TYPE_ACCESS',
    'TOKEN_TYPE_REFRESH',
]
