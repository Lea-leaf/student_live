# -*- coding: utf-8 -*-
"""管理端 - 内容管理。

需求：所有帖子、按模块/状态筛选、审核、删除、置顶。
覆盖全部模块（失物招领、二手交易、拼单、跑腿……），
因为帖子统一存放在 posts 表，这里天然是「跨模块总览」。
"""

from flask import Blueprint, request

from ..extensions import db
from ..models import Module, Post
from ..models.base import paginate
from ..utils.auth import admin_required, current_user
from ..utils.constants import (
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_REJECTED,
    MODULE_LOST_FOUND,
    POST_STATUSES,
    POST_STATUS_LABELS,
)
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import error, paginated, success
from ..utils.validators import (
    ValidationError,
    as_error,
    clean_text,
    get_json,
    parse_datetime,
    parse_int_list,
    validate_contact,
)
from ..modules import posts_service as svc

bp = Blueprint('admin_posts', __name__, url_prefix='/posts')

#: 允许的管理员状态覆盖（管理员可直接把帖子置为任意业务状态）
ADMIN_SETTABLE_STATUSES = POST_STATUSES


def _get_post_or_404(post_id):
    post = Post.query.get(post_id)
    if post is None:
        raise ValidationError('帖子不存在', 4001)
    return post


@bp.get('')
@admin_required
def list_posts():
    """全部帖子列表。

    查询参数：
        page / size / keyword / type（模块）/ status / audit_status
        is_deleted（0/1，默认 0）/ is_top / user_id / order
    """
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        post_type = (request.args.get('type') or '').strip()
        status = (request.args.get('status') or '').strip()
        audit_status = (request.args.get('audit_status') or '').strip()
        is_deleted = request.args.get('is_deleted', '0') in ('1', 'true')
        is_top = request.args.get('is_top')
        user_id = request.args.get('user_id')

        query = Post.query.filter(Post.is_deleted.is_(is_deleted))
        if post_type:
            query = query.filter(Post.type == post_type)
        if status:
            query = query.filter(Post.status == status)
        if audit_status:
            query = query.filter(Post.audit_status == audit_status)
        if is_top in ('0', '1'):
            query = query.filter(Post.is_top.is_(is_top == '1'))
        if user_id:
            query = query.filter(Post.user_id == int(user_id))
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(
                Post.title.like(like), Post.content.like(like),
                Post.contact.like(like), Post.location.like(like),
            ))

        order = (request.args.get('order') or 'newest').strip()
        if order == 'oldest':
            query = query.order_by(Post.id.asc())
        elif order == 'audit':
            query = query.order_by(Post.audit_status.asc(), Post.id.desc())
        else:
            query = query.order_by(Post.id.desc())

        items, total, page, size = paginate(query, page, size)
        modules = [{'code': item.code, 'name': item.name} for item in
                   Module.query.order_by(Module.sort_order.asc()).all()]
        return paginated([item.to_dict() for item in items], total, page, size,
                         extra={'modules': modules,
                                'statuses': [{'value': k, 'label': v} for k, v in POST_STATUS_LABELS.items()]})
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            return as_error(exc)
        return error('user_id 必须是整数')


@bp.get('/pending')
@admin_required
def pending_posts():
    """待审核列表（审核工作台主入口）。"""
    try:
        page, size = current_page_args()
        post_type = (request.args.get('type') or '').strip() or None
        query = svc.pending_audit_query(post_type).order_by(Post.id.asc())
        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size)
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:post_id>')
@admin_required
def post_detail(post_id):
    """帖子详情（管理员可看任意状态，含已软删除）。"""
    try:
        post = Post.query.get(post_id)
        if post is None:
            raise ValidationError('帖子不存在', 4001)
        data = post.to_dict()
        data['deleted'] = post.is_deleted
        data['auditor'] = None
        if post.audited_by:
            from ..models import User

            auditor = User.query.get(post.audited_by)
            data['auditor'] = auditor.to_brief() if auditor else None
        return success(data)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/audit')
@admin_required
def audit_post(post_id):
    """审核帖子。

    请求体：
        {"audit_status": "approved"|"rejected", "remark": "审核意见",
         "status": "ongoing"（可选，管理员可直接改业务状态）}
    """
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)
        payload = get_json()
        target = (payload.get('audit_status') or '').strip()
        if target not in (AUDIT_APPROVED, AUDIT_REJECTED):
            raise ValidationError('audit_status 只能是 approved / rejected')
        if post.audit_status == target:
            return error('该帖子已处于该审核状态', 4003)

        remark = clean_text(payload.get('remark'), 255, '审核意见')
        if target == AUDIT_APPROVED:
            svc.approve(post, operator, remark)
            title, content = '你的信息已通过审核', f'《{post.title or "无标题"}》已公开展示。'
        else:
            svc.reject(post, operator, remark)
            title = '你的信息未通过审核'
            content = f'《{post.title or "无标题"}》未通过审核：{post.audit_remark}'

        # 管理员可选直接调整业务状态
        new_status = (payload.get('status') or '').strip()
        if new_status:
            if new_status not in ADMIN_SETTABLE_STATUSES:
                raise ValidationError('状态取值非法')
            post.status = new_status

        db.session.commit()
        write_operation_log('audit', module=post.type, target_type='post', target_id=post.id,
                            detail={'audit_status': target, 'remark': remark})
        send(post.user_id, title, content, notify_type='audit', ref_id=post.id,
             link={'route': 'post-detail', 'post_id': post.id})
        return success(post.to_dict(), msg='审核完成' if target == AUDIT_APPROVED else '已拒绝该帖子')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/batch/audit')
@admin_required
def batch_audit():
    """批量审核：{"post_ids": [1,2], "audit_status": "approved", "remark": "..."}"""
    try:
        operator = current_user()
        payload = get_json()
        ids = parse_int_list(payload.get('post_ids'), '帖子ID')
        target = (payload.get('audit_status') or '').strip()
        if not ids:
            raise ValidationError('请选择要审核的帖子')
        if target not in (AUDIT_APPROVED, AUDIT_REJECTED):
            raise ValidationError('audit_status 只能是 approved / rejected')
        remark = clean_text(payload.get('remark'), 255, '审核意见')

        affected = 0
        for pid in ids:
            post = Post.query.get(pid)
            if post is None or post.audit_status == target:
                continue
            if target == AUDIT_APPROVED:
                svc.approve(post, operator, remark)
            else:
                svc.reject(post, operator, remark)
            send(post.user_id,
                 '你的信息已通过审核' if target == AUDIT_APPROVED else '你的信息未通过审核',
                 f'《{post.title or "无标题"}》' + ('' if target == AUDIT_APPROVED else f'：{post.audit_remark}'),
                 notify_type='audit', ref_id=post.id, commit=False)
            affected += 1
        db.session.commit()
        write_operation_log('batch_audit', module='posts', detail={'ids': ids, 'audit_status': target})
        return success({'affected': affected}, msg=f'已处理 {affected} 条')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/status')
@admin_required
def change_status(post_id):
    """管理员直接调整业务状态：{"status": "closed", "reason": "..."}"""
    try:
        post = _get_post_or_404(post_id)
        payload = get_json()
        target = (payload.get('status') or '').strip()
        if target not in ADMIN_SETTABLE_STATUSES:
            raise ValidationError(f'状态取值非法，可选：{" / ".join(ADMIN_SETTABLE_STATUSES)}')
        post.status = target
        remark = clean_text(payload.get('reason'), 255, '说明')
        if remark:
            post.audit_remark = remark
        db.session.commit()
        write_operation_log('change_status', module=post.type, target_type='post', target_id=post.id,
                            detail={'status': target})
        return success(post.to_dict(), msg=f'已标记为「{POST_STATUS_LABELS.get(target, target)}」')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/top')
@admin_required
def toggle_top(post_id):
    """置顶 / 取消置顶。"""
    try:
        post = _get_post_or_404(post_id)
        payload = get_json(required=False)
        if 'is_top' in payload:
            post.is_top = bool(payload.get('is_top'))
        else:
            post.is_top = not post.is_top
        db.session.commit()
        write_operation_log('toggle_top', module=post.type, target_type='post', target_id=post.id,
                            detail={'is_top': post.is_top})
        return success({'is_top': post.is_top}, msg='已置顶' if post.is_top else '已取消置顶')
    except ValidationError as exc:
        return as_error(exc)


@bp.delete('/<int:post_id>')
@admin_required
def delete_post(post_id):
    """删除任意帖子（软删除 → 回收站）。"""
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)
        if post.is_deleted:
            return error('该帖子已在回收站中')
        svc.soft_delete(post, operator=operator)
        write_operation_log('delete', module=post.type, target_type='post', target_id=post.id,
                            detail={'admin': True})
        send(post.user_id, '你的信息已被管理员删除',
             f'《{post.title or "无标题"}》已被管理员删除，如有疑问请联系管理员。',
             notify_type='system', ref_id=post.id)
        return success(msg='已删除并移入回收站')
    except ValidationError as exc:
        return as_error(exc)


@bp.put('/<int:post_id>')
@admin_required
def update_post(post_id):
    """管理员编辑帖子内容（纠正明显错误，例如联系方式写错）。"""
    try:
        post = _get_post_or_404(post_id)
        payload = get_json()
        if 'title' in payload:
            post.title = clean_text(payload.get('title'), 128, '标题')
        if 'content' in payload:
            post.content = clean_text(payload.get('content'), 5000, '描述')
        if 'location' in payload:
            post.location = clean_text(payload.get('location'), 128, '地点')
        if 'contact' in payload:
            post.contact = validate_contact(payload.get('contact'))
        if 'happened_at' in payload:
            post.happened_at = parse_datetime(payload.get('happened_at'), '发生时间')
        db.session.commit()
        write_operation_log('update', module=post.type, target_type='post', target_id=post.id,
                            detail={'admin': True})
        return success(post.to_dict(), msg='已保存')
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/stats/summary')
@admin_required
def posts_summary():
    """内容概览：各状态 / 各模块数量，便于后台仪表盘。"""
    total = Post.query.filter(Post.is_deleted.is_(False)).count()
    rows = (
        db.session.query(Post.audit_status, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(False))
        .group_by(Post.audit_status)
        .all()
    )
    by_audit = {status: count for status, count in rows}
    by_module = {
        code: count for code, count in
        db.session.query(Post.type, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(False))
        .group_by(Post.type).all()
    }
    return success({
        'total': total,
        'by_audit': {
            'pending': by_audit.get(AUDIT_PENDING, 0),
            'approved': by_audit.get(AUDIT_APPROVED, 0),
            'rejected': by_audit.get(AUDIT_REJECTED, 0),
        },
        'by_module': by_module,
        'default_module': MODULE_LOST_FOUND,
    })


__all__ = ['bp']
