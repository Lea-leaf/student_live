# -*- coding: utf-8 -*-
"""认证模块路由。

接口一览（前缀 /api/v1/auth）：
    GET  /captcha           获取图形验证码
    POST /register          学号 + 验证码注册
    POST /login             登录，返回 access/refresh token
    POST /refresh           刷新 token
    GET  /me                当前用户信息
    PUT  /me                修改个人资料
    PUT  /password          修改密码
    POST /logout            登出（原型阶段前端清 token；预留服务端黑名单）
    GET  /security-notice   安全公告文案
"""

from flask import Blueprint, g, request

from ...extensions import db
from ...models import LoginLog, User
from ...utils import captcha as captcha_service
from ...utils.auth import (
    TOKEN_TYPE_REFRESH,
    current_user,
    decode_token,
    generate_token_pair,
    token_required,
)
from ...utils.config_service import get_config, get_config_bool
from ...utils.constants import ROLE_USER, STATUS_ACTIVE
from ...utils.logger import write_login_log, write_operation_log
from ...utils.response import (
    CODE_ACCOUNT_BANNED,
    CODE_CAPTCHA_ERROR,
    CODE_PASSWORD_ERROR,
    CODE_UNAUTHORIZED,
    CODE_USER_EXISTS,
    error,
    success,
)
from ...utils.validators import (
    ValidationError,
    as_error,
    get_json,
    validate_password,
    validate_student_id,
    validate_username,
)

bp = Blueprint('auth', __name__, url_prefix='/auth')

#: 简单的登录失败节流：IP + 学号 维度，防止暴力破解（内存版，重启即清空）
_FAILED_ATTEMPTS = {}
_MAX_FAILED = 10
_LOCK_SECONDS = 300


def _throttle_key():
    student_id = (get_json(required=False).get('student_id') or '').strip()
    return f'{request.remote_addr}|{student_id}'


def _is_locked(key):
    import time

    item = _FAILED_ATTEMPTS.get(key)
    if not item:
        return False, 0
    count, first_at = item
    if time.time() - first_at > _LOCK_SECONDS:
        _FAILED_ATTEMPTS.pop(key, None)
        return False, 0
    return count >= _MAX_FAILED, _LOCK_SECONDS - int(time.time() - first_at)


def _record_failure(key):
    import time

    count, first_at = _FAILED_ATTEMPTS.get(key, (0, time.time()))
    _FAILED_ATTEMPTS[key] = (count + 1, first_at)


def _clear_failure(key):
    _FAILED_ATTEMPTS.pop(key, None)


# ---------------------------------------------------------------------------
# 验证码
# ---------------------------------------------------------------------------
@bp.get('/captcha')
def get_captcha():
    """获取图形验证码。

    返回 data.image 为可直接塞进 <img src> 的 data URI。
    """
    data = captcha_service.issue_svg()
    return success(data)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
@bp.post('/register')
def register():
    """学号 + 验证码注册。

    请求体：
        {
            "student_id": "20210001",
            "password": "123456",
            "confirm_password": "123456",   # 可选
            "nickname": "小明",              # 可选
            "captcha_id": "xxx",            # 开启验证码时必填
            "captcha": "A3F9"
        }
    """
    try:
        payload = get_json()
        student_id = validate_student_id(payload.get('student_id'))
        password = validate_password(payload.get('password'))
        confirm = payload.get('confirm_password')
        if confirm is not None and confirm != password:
            raise ValidationError('两次输入的密码不一致')
        nickname = payload.get('nickname')
        if nickname:
            nickname = validate_username(nickname)

        # 验证码校验（默认开启，可在后台配置里关闭）
        if get_config_bool('register_captcha_enabled', True):
            ok = captcha_service.verify(payload.get('captcha_id'), payload.get('captcha'))
            if not ok:
                return error('验证码错误或已过期', CODE_CAPTCHA_ERROR)

        if User.query.filter_by(student_id=student_id).first():
            return error('该学号已注册，请直接登录', CODE_USER_EXISTS)

        # username 默认与学号一致；若已存在同名（例如自定义账号）则加后缀
        username = student_id
        if User.query.filter_by(username=username).first():
            username = f'{student_id}_{User.query.count()}'

        user = User(
            student_id=student_id,
            username=username,
            nickname=nickname or student_id,
            role=ROLE_USER,
            status=STATUS_ACTIVE,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        write_operation_log('register', module='auth', target_type='user', target_id=user.id, user=user)
        tokens = generate_token_pair(user)
        return success({'user': user.to_dict(), **tokens}, msg='注册成功')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
@bp.post('/login')
def login():
    """登录。支持学号或用户名。"""
    try:
        payload = get_json()
        account = (payload.get('student_id') or payload.get('username') or '').strip()
        password = payload.get('password') or ''
        if not account or not password:
            raise ValidationError('请输入学号和密码')

        key = f'{request.remote_addr}|{account}'
        locked, remain = _is_locked(key)
        if locked:
            return error(f'失败次数过多，请 {remain} 秒后再试', CODE_UNAUTHORIZED)

        user = User.query.filter(
            (User.student_id == account) | (User.username == account)
        ).first()

        if user is None or not user.check_password(password):
            _record_failure(key)
            write_login_log(account, False, '账号或密码错误', user=user)
            return error('学号或密码错误', CODE_PASSWORD_ERROR)

        if user.is_banned:
            write_login_log(account, False, f'账号已封禁：{user.ban_reason or ""}', user=user)
            return error(
                f'账号已被封禁：{user.ban_reason or "请联系管理员"}',
                CODE_ACCOUNT_BANNED,
                http_status=403,
            )

        # 登录成功
        _clear_failure(key)
        user.mark_login(ip=request.remote_addr)
        db.session.commit()
        write_login_log(account, True, '登录成功', user=user, commit=False)
        write_operation_log('login', module='auth', target_type='user', target_id=user.id,
                            user=user, commit=False)
        db.session.commit()

        tokens = generate_token_pair(user)
        return success({'user': user.to_dict(), **tokens}, msg='登录成功')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/refresh')
def refresh():
    """用 refresh_token 换新的 access_token。"""
    try:
        payload = get_json()
        token = payload.get('refresh_token')
        if not token:
            raise ValidationError('缺少 refresh_token')
        try:
            data = decode_token(token, verify_type=TOKEN_TYPE_REFRESH)
        except Exception as exc:  # noqa: BLE001
            return error(f'刷新失败：{exc}', CODE_UNAUTHORIZED, http_status=401)
        user = User.query.get(data.get('uid'))
        if not user or user.is_banned:
            return error('账号不可用', CODE_UNAUTHORIZED, http_status=401)
        return success({'user': user.to_dict(), **generate_token_pair(user)})
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/logout')
@token_required
def logout():
    """登出。

    原型阶段由前端删除本地 token；这里预留服务端失效逻辑
    （接入 Redis 黑名单时，把当前 token 的 jti 写入黑名单即可）。
    """
    write_operation_log('logout', module='auth', target_type='user', target_id=g.current_user.id)
    return success({'msg': '已登出'})


# ---------------------------------------------------------------------------
# 个人资料
# ---------------------------------------------------------------------------
@bp.get('/me')
@token_required
def me():
    """当前登录用户信息。"""
    user = current_user()
    data = user.to_dict(with_sensitive=True)
    from ...utils.config_service import get_config_int

    data['unread_notification'] = _unread(user.id)
    data['security_notice_enabled'] = get_config_bool('security_notice_enabled', True)
    data['site_name'] = get_config('site_name', '校园生活平台')
    return success(data)


@bp.put('/me')
@token_required
def update_me():
    """修改昵称 / 头像。"""
    try:
        payload = get_json()
        user = current_user()
        if 'nickname' in payload and payload['nickname']:
            user.nickname = validate_username(payload['nickname'])
        if 'avatar' in payload:
            user.avatar = (payload.get('avatar') or '')[:255] or None
        if 'email' in payload:
            user.email = (payload.get('email') or '')[:128] or None
        db.session.commit()
        return success(user.to_dict(with_sensitive=True), msg='资料已更新')
    except ValidationError as exc:
        return as_error(exc)


@bp.put('/password')
@token_required
def change_password():
    """修改密码（需校验原密码）。"""
    try:
        payload = get_json()
        user = current_user()
        old = payload.get('old_password') or ''
        new = validate_password(payload.get('new_password'))
        if not user.check_password(old):
            return error('原密码不正确', CODE_PASSWORD_ERROR)
        user.set_password(new)
        db.session.commit()
        write_operation_log('change_password', module='auth', target_type='user', target_id=user.id)
        return success(msg='密码修改成功，请重新登录')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 安全公告
# ---------------------------------------------------------------------------
@bp.get('/security-notice')
def security_notice():
    """安全公告（首次使用 / 发布信息前弹出）。"""
    return success({
        'enabled': get_config_bool('security_notice_enabled', True),
        'text': get_config('security_notice_text', ''),
        'site_name': get_config('site_name', '校园生活平台'),
    })


def _unread(user_id):
    from ...utils.notification_service import unread_count

    return unread_count(user_id)


__all__ = ['bp']
