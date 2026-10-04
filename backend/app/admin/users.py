# -*- coding: utf-8 -*-
"""管理端 - 用户管理。

需求：列表、搜索、详情、封禁/解封、重置密码、查看发帖记录。
额外：角色调整（RBAC 预留）、管理员创建用户、管理员重置他人密码。
"""

from flask import Blueprint, request

from ..extensions import db
from ..models import LoginLog, OperationLog, Post, User
from ..models.base import paginate
from ..utils.auth import admin_required, current_user
from ..utils.constants import (
    ADMIN_ROLES,
    CAP_USER_DETAIL,
    CAP_USER_MANAGE,
    CAP_USER_ROLE,
    CAP_USER_VIEW,
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


def _guard_target(operator, target, action='操作'):
    """谁能对谁执行账号处置（封禁 / 解封 / 重置密码 / 删除）。

    规则（收敛成两条）：
    1. **审核员只能管普通用户** —— 对其他后台角色（审核员、管理员）没有处置权；
    2. **管理员之间完全平级** —— 可以互相处置（`admin` 就是最高等级，
       不存在"更高一级"，所以没有"上级才能动下级"这回事）。

    不能对自己操作由各接口单独校验（避免把自己封了 / 删了）。

    历史说明：早期这里写的是「非 super_admin 不能处置管理员」，
    但 `is_super_admin` 对 admin 本身就返回 True，那个判断恒为假，
    实际效果是"管理员互相不能动" —— 与"admin 即最高级"的定位自相矛盾。
    现在随 `super_admin` 档位一起移除了。
    """
    if operator.is_admin:
        return None
    if target.is_staff:
        return error(f'审核员不能对其他管理员或审核员执行{action}', CODE_FORBIDDEN,
                     http_status=403)
    return None


@bp.get('')
@admin_required(capability=CAP_USER_VIEW)
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
@admin_required(capability=CAP_USER_VIEW)
def user_detail(user_id):
    """用户详情 + 发帖统计。

    权限分层（`with_sensitive`）：
    - **管理员**（有 `user.detail`）：带邮箱 / 手机号等敏感字段；
    - **审核员**（只有 `user.view`）：能看基础资料与统计，但**不返回敏感字段** ——
      与他"不能看用户明细、不能重置密码"的权限边界一致。

    发帖记录 / 登录日志 / 媒体清单仍各自需要 `user.detail`，审核员访问会 403。
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        post_total = Post.query.filter_by(user_id=user.id).count()
        deleted_total = Post.query.filter_by(user_id=user.id, is_deleted=True).count()
        pending_total = Post.query.filter_by(user_id=user.id, audit_status='pending').count()
        login_count = LoginLog.query.filter_by(user_id=user.id, success=True).count()
        return success({
            'user': user.to_dict(with_sensitive=operator.has_capability(CAP_USER_DETAIL)),
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
@admin_required(capability=CAP_USER_DETAIL)
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
@admin_required(capability=CAP_USER_MANAGE)
def ban_user(user_id):
    """封禁用户（审核员也可以，但**只能封禁普通用户**）。

    请求体：{"reason": "发布违规信息"}
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        if user.id == operator.id:
            raise ValidationError('不能封禁自己')
        guard = _guard_target(operator, user, '封禁')
        if guard:
            return guard

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
@admin_required(capability=CAP_USER_MANAGE)
def unban_user(user_id):
    """解封用户（审核员同样只能解封普通用户）。"""
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        guard = _guard_target(operator, user, '解封')
        if guard:
            return guard
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
@admin_required(capability=CAP_USER_DETAIL)
def reset_password(user_id):
    """重置用户密码（**仅管理员**；审核员没有此权限，需求明确排除）。

    请求体：{"new_password": "xxxxxx"}  不传则重置为默认密码 123456
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        if user.id == operator.id:
            raise ValidationError('请在「个人中心」修改自己的密码，不要用重置功能')

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
@admin_required(capability=CAP_USER_ROLE)
def change_role(user_id):
    """调整用户角色（**管理员专有**，这正是「任命审核员」的入口）。

    权限：`user.role` 能力只给管理员 —— 审核员没有（需求原文："没有任命审核员的权利"）。

    约束：
    - 角色必须是 `ROLES` 里列出的值（预留角色不在其中，因此无法被分配）；
    - **不能通过这里改自己的角色** —— 管理员把自己降级等于"让出管理员"，
      那要走「管理员移交」（`/admin/handover`），必须先把权限交给别人；
    - **不能把别人直接改成管理员** —— 系统只允许一个管理员，换人只能走移交；
    - 每次变更写操作日志（who 改了谁、从什么改成什么），可追溯。
    """
    try:
        operator = current_user()
        user = _get_user_or_404(user_id)
        payload = get_json()
        role = (payload.get('role') or '').strip()
        if role not in ROLES:
            raise ValidationError(
                f'角色取值非法，可选：{" / ".join(ROLES)}'
                '（其余角色为预留未启用，暂不可分配）'
            )

        if user.id == operator.id:
            if user.is_admin:
                raise ValidationError(
                    '管理员不能直接修改自己的角色。若要让出管理员权限，请使用'
                    '「管理员移交」：先指定接任者，24 小时内可随时撤销，'
                    '到期后你才会变为普通用户'
                )
            raise ValidationError('不能修改自己的角色')

        if role == ROLE_ADMIN:
            raise ValidationError(
                '系统只允许存在一个管理员。如需更换管理员，请使用「管理员移交」功能'
            )

        if user.is_frozen:
            raise ValidationError('该账号正处于管理员交接冻结期，请先撤销移交再调整角色')
        user = _get_user_or_404(user_id)
        payload = get_json()
        role = (payload.get('role') or '').strip()

        old_role = user.role
        user.role = role
        db.session.commit()
        write_operation_log('change_role', module='users', target_type='user', target_id=user.id,
                            detail={'from': old_role, 'to': role})
        return success(user.to_dict(with_sensitive=True), msg='角色已更新')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:user_id>/remark')
@admin_required(capability=CAP_USER_DETAIL)
def update_remark(user_id):
    """管理员备注（例如记录沟通情况，属敏感明细，审核员不可用）。"""
    try:
        user = _get_user_or_404(user_id)
        payload = get_json()
        user.remark = clean_text(payload.get('remark'), 255, '备注')
        db.session.commit()
        return success(user.to_dict(with_sensitive=True), msg='备注已保存')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('')
@admin_required(capability=CAP_USER_DETAIL)
def create_user():
    """管理员直接创建账号（无需验证码，用于导入学生名单；审核员不可用）。

    请求体：{"student_id": "...", "password": "...", "nickname": "...", "role": "user"}
    """
    try:
        operator = current_user()
        payload = get_json()
        student_id = validate_student_id(payload.get('student_id'))
        password = validate_password(payload.get('password'))
        role = (payload.get('role') or ROLE_USER).strip()
        if role not in ROLES:
            raise ValidationError(
                f'角色取值非法，可选：{" / ".join(ROLES)}'
                '（其余角色为预留未启用，暂不可分配）'
            )
        if role == ROLE_ADMIN:
            raise ValidationError(
                '系统只允许存在一个管理员。如需更换管理员，请使用「管理员移交」功能'
            )
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
@admin_required(capability=CAP_USER_MANAGE)
def batch_ban():
    """批量封禁：{"user_ids": [1,2,3], "reason": "..."}

    审核员可用，但批量操作里同样跳过所有后台角色（只能封普通用户）。
    """
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
                # 自己不能被批量封禁（其余无效 ID 一并跳过）
                skipped.append(uid)
                continue
            if not operator.is_admin and user.is_staff:
                # 审核员只能封普通用户
                skipped.append(uid)
                continue
            user.ban(reason=reason, operator_id=operator.id)
            affected += 1
        db.session.commit()
        write_operation_log('batch_ban', module='users',
                            detail={'ids': ids, 'affected': affected, 'skipped': skipped})
        return success({'affected': affected, 'skipped': skipped}, msg=f'已封禁 {affected} 个账号')
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:user_id>/logs')
@admin_required(capability=CAP_USER_DETAIL)
def user_logs(user_id):
    """某用户的操作日志与登录日志（排查用，含登录 IP，审核员无权查看）。"""
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


@bp.get('/<int:user_id>/media')
@admin_required(capability=CAP_USER_DETAIL)
def user_media(user_id):
    """查看某用户的媒体文件清单（数据库记录 + 磁盘实际占用）。

    删除用户前先用它确认「要删掉哪些东西」，也让「数据归属」可见。
    审核员无权查看（含磁盘路径，属敏感明细）。
    """
    try:
        from ..models import UploadFile
        from ..utils.uploads import user_upload_dir

        user = _get_user_or_404(user_id)
        rows = UploadFile.query.filter_by(user_id=user.id).order_by(UploadFile.id.desc()).all()
        directory = user_upload_dir(user)
        files_on_disk, bytes_on_disk = 0, 0
        import os

        if os.path.isdir(directory):
            for dirpath, _dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    files_on_disk += 1
                    try:
                        bytes_on_disk += os.path.getsize(os.path.join(dirpath, filename))
                    except OSError:
                        pass

        return success({
            'user': user.to_brief(),
            'upload_dir': directory,
            'db_records': [row.to_dict() for row in rows],
            'db_record_count': len(rows),
            'files_on_disk': files_on_disk,
            'bytes_on_disk': bytes_on_disk,
        })
    except ValidationError as exc:
        return as_error(exc)


@bp.delete('/<int:user_id>')
@admin_required(capability=CAP_USER_DETAIL)
def delete_user(user_id):
    """**彻底删除用户**（不可恢复）。

    删除范围（级联，确保不留下孤儿指针与孤儿文件）：
        - 该用户发布的全部帖子，及其评论 / 收藏 / 媒体记录 / 举报引用解除
        - 该用户发出的评论、收藏、举报、私信、通知、模块授权、上传记录
        - 磁盘目录 `uploads/<学号>/` 整个删除
        - 操作日志保留（审计需要），但把 user_id 置空

    安全约束：
        - 仅管理员可调用（`user.detail` 能力，审核员没有）；
        - 不能删除自己；
        - **不能删除管理员**（系统只允许一个管理员，换人走「管理员移交」）；
        - 请求体必须带 `confirm_student_id` 且与该用户学号完全一致（二次确认，防误删）。
    """
    try:
        from ..utils.cleanup import purge_user

        operator = current_user()
        user = _get_user_or_404(user_id)

        if user.id == operator.id:
            raise ValidationError('不能删除自己的账号')
        if user.is_admin:
            raise ValidationError(
                '不能删除管理员账号。如需更换管理员，请使用「管理员移交」功能'
            )

        payload = get_json(required=False) or {}
        confirm = (payload.get('confirm_student_id') or '').strip()
        if confirm != user.student_id:
            raise ValidationError(
                f'二次确认失败：请在 confirm_student_id 中填写该用户的学号「{user.student_id}」'
            )

        student_id = user.student_id
        stats = purge_user(user, delete_files=True)

        # 用户已删，日志里只留快照
        write_operation_log('delete_user', module='users', target_type='user', target_id=user_id,
                            detail=stats)
        total_files = stats['media_files'] + stats['leftover_files']
        return success(stats, msg=f'已彻底删除用户 {student_id}（含 {stats["posts"]} 条帖子、'
                                  f'{stats["media_rows"]} 条媒体记录、{total_files} 个磁盘文件）')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
