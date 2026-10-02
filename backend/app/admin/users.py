# -*- coding: utf-8 -*-
"""管理端 - 用户管理。

需求：列表、搜索、详情、封禁/解封、重置密码、查看发帖记录。
额外：角色调整（RBAC 预留）、管理员创建用户、管理员重置他人密码。
"""

from flask import Blueprint, request

from ..extensions import db
from ..models import LoginLog, OperationLog, Post, User
from ..models.base import paginate
from ..utils.auth import admin_required, current_user, super_admin_required
from ..utils.constants import (
    ADMIN_ROLES,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_USER,
    ROLES,
    STATUS_ACTIVE,
    STATUS_BANNED,
    USER_STATUS_LABELS,
)
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import CODE_FORBIDDEN, error, paginated, success
from ..utils.validators import (
    ValidationError,
    as_error,
    clean_text,
    get_json,
    parse_int_list,
    validate_password,
    validate_student_id,
)

bp = Blueprint('admin_users', __name__, url_prefix='/users')

#: 重置密码后的默认值（原型阶段固定，正式部署建议改为随机 + 强制改密）
DEFAULT_RESET_PASSWORD = '123456'


def _get_user_or_404(user_id):
    user = User.query.get(user_id)
    if user is None:
        raise ValidationError('用户不存在', 3002)
    return user


@bp.get('')
@admin_required
def list_users():
    """用户列表。

    查询参数：page / size / keyword / role / status / order
    """
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        role = (request.args.get('role') or '').strip()
        status = (request.args.get('status') or '').strip()

        query = User.query
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(
                User.student_id.like(like),
                User.username.like(like),
                User.nickname.like(like),
            ))
        if role:
            query = query.filter(User.role == role)
        if status:
            query = query.filter(User.status == status)

        order = (request.args.get('order') or 'newest').strip()
        if order == 'oldest':
            query = query.order_by(User.id.asc())
        elif order == 'posts':
            query = query.order_by(User.post_count.desc(), User.id.desc())
        else:
            query = query.order_by(User.id.desc())

        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict(with_sensitive=True) for item in items], total, page, size,
                         extra={'roles': [{'value': r, 'label': ROLE_LABELS.get(r, r)} for r in ROLES],
                                'statuses': [{'value': k, 'label': v} for k, v in USER_STATUS_LABELS.items()]})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:user_id>')
@admin_required
def user_detail(user_id):
    """用户详情 + 发帖统计。"""
    try:
        user = _get_user_or_404(user_id)
        post_total = Post.query.filter_by(user_id=user.id).count()
        deleted_total = Post.query.filter_by(user_id=user.id, is_deleted=True).count()
        pending_total = Post.query.filter_by(user_id=user.id, audit_status='pending').count()
        login_count = LoginLog.query.filter_by(user_id=user.id, success=True).count()
        return success({
            'user': user.to_dict(with_sensitive=True),
            'stats': {
                'post_total': post_total,
                'post_deleted': deleted_total,
                'post_pending': pending_total,
                'login_count': login_count,
            },
        })
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:user_id>/posts')
@admin_required
def user_posts(user_id):
    """查看某用户的发帖记录（含软删除，便于管理员判断）。"""
    try:
        user = _get_user_or_404(user_id)
        page, size = current_page_args()
        include_deleted = request.args.get('include_deleted', '1') not in ('0', 'false')
        post_type = (request.args.get('type') or '').strip() or None

        query = Post.query.filter_by(user_id=user.id)
        if not include_deleted:
            query = query.filter(Post.is_deleted.is_(False))
        if post_type:
            query = query.filter(Post.type == post_type)
        query = query.order_by(Post.id.desc())

        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size,
                         extra={'user': user.to_brief()})
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/ban')
@admin_required
def ban_user(user_id):
    """封禁用户。

    请求体：{"reason": "发布违规信息"}
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        if user.id == operator.id:
            raise ValidationError('不能封禁自己')
        if user.is_admin and not operator.is_super_admin:
            return error('只有超级管理员可以封禁管理员账号', CODE_FORBIDDEN, http_status=403)

        payload = get_json(required=False)
        reason = clean_text(payload.get('reason'), 255, '封禁原因') or '违反平台规范'
        user.ban(reason=reason, operator_id=operator.id)
        db.session.commit()

        write_operation_log('ban', module='users', target_type='user', target_id=user.id,
                            detail={'reason': reason})
        send(user.id, '账号已被封禁', f'原因：{reason}', notify_type='system')
        return success(user.to_dict(with_sensitive=True), msg='已封禁该用户')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/unban')
@admin_required
def unban_user(user_id):
    """解封用户。"""
    try:
        user = _get_user_or_404(user_id)
        if user.status != STATUS_BANNED:
            return error('该用户当前未被封禁')
        user.unban()
        db.session.commit()
        write_operation_log('unban', module='users', target_type='user', target_id=user.id)
        send(user.id, '账号已解封', '你的账号已恢复正常，请遵守平台规范。', notify_type='system')
        return success(user.to_dict(with_sensitive=True), msg='已解封该用户')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/reset-password')
@admin_required
def reset_password(user_id):
    """重置用户密码。

    请求体：{"new_password": "xxxxxx"}  不传则重置为默认密码 123456
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        if user.is_admin and not operator.is_super_admin:
            return error('只有超级管理员可以重置管理员密码', CODE_FORBIDDEN, http_status=403)

        payload = get_json(required=False)
        raw = payload.get('new_password') or DEFAULT_RESET_PASSWORD
        new_password = validate_password(raw)
        user.set_password(new_password)
        db.session.commit()

        write_operation_log('reset_password', module='users', target_type='user', target_id=user.id)
        send(user.id, '密码已被重置', '管理员重置了你的密码，请尽快登录后修改。', notify_type='system')
        # 原型阶段直接回传明文，方便答辩演示；正式环境应改为邮件/短信下发
        return success({'student_id': user.student_id, 'new_password': raw},
                       msg=f'密码已重置为 {raw}')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/role')
@super_admin_required
def change_role(user_id):
    """调整用户角色（RBAC 预留：未来分级管理员靠这里授权）。"""
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        payload = get_json()
        role = (payload.get('role') or '').strip()
        if role not in ROLES:
            raise ValidationError(f'角色取值非法，可选：{" / ".join(ROLES)}')
        if user.id == operator.id and role not in ADMIN_ROLES:
            raise ValidationError('不能取消自己的管理员权限')

        old_role = user.role
        user.role = role
        db.session.commit()
        write_operation_log('change_role', module='users', target_type='user', target_id=user.id,
                            detail={'from': old_role, 'to': role})
        return success(user.to_dict(with_sensitive=True), msg='角色已更新')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/remark')
@admin_required
def update_remark(user_id):
    """管理员备注（例如记录沟通情况）。"""
    try:
        user = _get_user_or_404(user_id)
        payload = get_json()
        user.remark = clean_text(payload.get('remark'), 255, '备注')
        db.session.commit()
        return success(user.to_dict(with_sensitive=True), msg='备注已保存')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('')
@admin_required
def create_user():
    """管理员直接创建账号（无需验证码，用于导入学生名单）。

    请求体：{"student_id": "...", "password": "...", "nickname": "...", "role": "user"}
    """
    try:
        operator = current_user()
        payload = get_json()
        student_id = validate_student_id(payload.get('student_id'))
        password = validate_password(payload.get('password'))
        role = (payload.get('role') or ROLE_USER).strip()
        if role not in ROLES:
            raise ValidationError('角色取值非法')
        if role in ADMIN_ROLES and not operator.is_super_admin:
            return error('只有超级管理员可以创建管理员账号', CODE_FORBIDDEN, http_status=403)
        if User.query.filter_by(student_id=student_id).first():
            return error('该学号已存在', 3001)

        user = User(
            student_id=student_id,
            username=student_id,
            nickname=clean_text(payload.get('nickname'), 20, '昵称') or student_id,
            role=role,
            status=STATUS_ACTIVE,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        write_operation_log('create_user', module='users', target_type='user', target_id=user.id)
        return success(user.to_dict(with_sensitive=True), msg='账号创建成功')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/batch/ban')
@admin_required
def batch_ban():
    """批量封禁：{"user_ids": [1,2,3], "reason": "..."}"""
    try:
        operator = current_user()
        payload = get_json()
        ids = parse_int_list(payload.get('user_ids'), '用户ID')
        if not ids:
            raise ValidationError('请选择要封禁的用户')
        reason = clean_text(payload.get('reason'), 255, '封禁原因') or '违反平台规范'

        affected = 0
        skipped = []
        for uid in ids:
            user = User.query.get(uid)
            if not user or user.id == operator.id:
                skipped.append(uid)
                continue
            if user.is_admin and not operator.is_super_admin:
                skipped.append(uid)
                continue
            user.ban(reason=reason, operator_id=operator.id)
            affected += 1
        db.session.commit()
        write_operation_log('batch_ban', module='users', detail={'ids': ids, 'affected': affected})
        return success({'affected': affected, 'skipped': skipped}, msg=f'已封禁 {affected} 个账号')
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:user_id>/logs')
@admin_required
def user_logs(user_id):
    """某用户的操作日志与登录日志（排查用）。"""
    try:
        user = _get_user_or_404(user_id)
        page, size = current_page_args()
        login_query = LoginLog.query.filter_by(user_id=user.id).order_by(LoginLog.id.desc())
        logins, login_total, _, _ = paginate(login_query, page, size)
        operations = (
            OperationLog.query.filter_by(user_id=user.id)
            .order_by(OperationLog.id.desc())
            .limit(size)
            .all()
        )
        return success({
            'login_logs': [item.to_dict() for item in logins],
            'login_total': login_total,
            'operation_logs': [item.to_dict() for item in operations],
        })
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
