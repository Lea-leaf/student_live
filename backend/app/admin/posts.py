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
    CAP_POST_AUDIT,
    CAP_POST_MANAGE,
    CAP_POST_VIEW,
    MODULE_LOST_FOUND,
    POST_STATUSES,
    POST_STATUS_LABELS,
)
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import (
    CODE_FORBIDDEN,
    CODE_POST_ASSIGN_TAKEN,
    CODE_POST_AUDIT_DONE,
    error,
    paginated,
    success,
)
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


def _user_brief(user_id):
    """把裸整数 ID 翻译成用户摘要（审核员注销后返回 None，不影响列表）。"""
    if not user_id:
        return None
    from ..models import User

    user = User.query.get(user_id)
    return user.to_brief() if user else None


def _assignment_payload(post, operator):
    """待审列表里每条帖子的指派信息与可操作性。

    前端凭这组字段直接决定按钮：
    - `can_audit`  能否点「通过 / 拒绝」（含禁止自审）
    - `can_claim`  能否点「认领」（公共池 + 有审核能力 + 不是自己的帖子）
    - `can_assign` 能否点「指派」（仅管理员）
    - `can_release` 能否点「放弃」（自己认领的）
    """
    effective = post.effective_assignee_id
    is_mine = effective == operator.id
    return {
        'assignee': _user_brief(effective),
        'assignee_id': effective,
        'assigned_by': _user_brief(post.assigned_by),
        'assigned_at': post.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if post.assigned_at else None,
        'assignment_expires_at': (
            post.assignment_expires_at.strftime('%Y-%m-%d %H:%M:%S')
            if post.assignment_expires_at else None
        ),
        'assignment_expired': post.assignment_expired,
        'is_self_post': post.user_id == operator.id,
        'can_audit': post.is_auditable_by(operator),
        'can_claim': bool(
            post.pending_audit and effective is None
            and post.user_id != operator.id
            and operator.has_capability(CAP_POST_AUDIT)
        ),
        'can_assign': bool(operator.is_admin and post.pending_audit),
        'can_release': bool(is_mine and post.pending_audit),
    }


def _pending_stats(operator):
    """待审概览：公共池 / 我的 / 总计。"""
    from ..utils.constants import AUDIT_PENDING

    base = Post.query.filter(Post.audit_status == AUDIT_PENDING, Post.is_deleted.is_(False))
    return {
        'pool': base.filter(Post.assignee_id.is_(None)).count(),
        'mine': base.filter(Post.assignee_id == operator.id).count(),
        'total': base.count(),
    }


@bp.get('/audit-assignees')
@admin_required(capability=CAP_POST_AUDIT)
def audit_assignees():
    """可被指派的审核员清单 + 各人待审数量（分配面板用）。

    只有管理员能看到完整名单；审核员调用时返回空列表（不需要知道自己同事的负载）。
    """
    from ..models import User
    from ..utils.constants import ADMIN_ROLES, ROLE_LABELS

    operator = current_user()
    if not operator.is_admin:
        return success({'list': [], 'pending_by_assignee': {}})

    users = (
        User.query.filter(User.role.in_(ADMIN_ROLES), User.status == 'active')
        .order_by(User.id.asc()).all()
    )
    counts = svc.count_pending_by_assignee()
    return success({
        'list': [
            {**user.to_brief(), 'pending_count': counts.get(user.id, 0)}
            for user in users
            if user.role != 'user'
        ],
        'pending_by_assignee': {str(k): v for k, v in counts.items() if k is not None},
        'role_labels': ROLE_LABELS,
    })


@bp.post('/<int:post_id>/assign')
@admin_required(capability=CAP_POST_AUDIT)
def assign_post(post_id):
    """指派 / 改派 / 收回审核任务（**仅管理员**）。

    请求体：
        {"assignee_id": 7, "remark": "张三负责"}   指派或改派
        {"assignee_id": null}                       收回公共池
        {"ttl_hours": 24}                           可选：N 小时后自动退回
    """
    try:
        operator = current_user()
        if not operator.is_admin:
            return error('只有管理员可以指派审核员', CODE_FORBIDDEN, http_status=403)

        post = _get_post_or_404(post_id)
        if not post.pending_audit:
            return error('该帖子不在待审核状态，无法指派', CODE_POST_AUDIT_DONE)

        payload = get_json(required=False) or {}
        assignee_id = payload.get('assignee_id')

        if assignee_id in (None, '', 0, '0'):
            svc.assign(post, None, operator, remark=payload.get('remark'))
            db.session.commit()
            write_operation_log('assign_audit', module=post.type, target_type='post',
                                target_id=post.id, detail={'assignee_id': None})
            return success(post.to_dict(), msg='已收回至公共池')

        from ..models import User

        assignee = User.query.get(int(assignee_id))
        if assignee is None:
            raise ValidationError('指派的审核员不存在')
        if not assignee.has_capability(CAP_POST_AUDIT):
            raise ValidationError('该用户没有审核权限，不能作为审核员')
        if assignee.id == post.user_id:
            raise ValidationError('不能把帖子指派给作者本人（禁止自审）')

        ttl = payload.get('ttl_hours')
        try:
            ttl = int(ttl) if ttl not in (None, '') else None
        except (TypeError, ValueError):
            raise ValidationError('ttl_hours 必须是整数') from None

        svc.assign(post, assignee, operator, remark=payload.get('remark'), ttl_hours=ttl)
        db.session.commit()
        write_operation_log('assign_audit', module=post.type, target_type='post',
                            target_id=post.id,
                            detail={'assignee_id': assignee.id, 'ttl_hours': ttl})
        # 通知被指派的审核员
        send(assignee.id, '有新的待审内容指派给你',
             f'《{post.title or "无标题"}》已指派给你审核，请及时处理。',
             notify_type='system', ref_id=post.id,
             link={'route': 'admin-audit'})
        return success(post.to_dict(), msg=f'已指派给 {assignee.to_brief()["display_name"]}')
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            return as_error(exc)
        return error('assignee_id 必须是整数')


@bp.post('/<int:post_id>/claim')
@admin_required(capability=CAP_POST_AUDIT)
def claim_post(post_id):
    """审核员自助认领待审帖子（**先到先得**，并发安全）。

    两位审核员同时点认领时，数据库层的原子条件更新保证只有一个人成功，
    另一位收到「已被 XX 认领」的提示。
    """
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)

        if not post.pending_audit:
            return error('该帖子不在待审核状态', CODE_POST_AUDIT_DONE)
        if post.user_id == operator.id:
            return error('不能认领自己发布的帖子（禁止自审）', CODE_FORBIDDEN, http_status=403)

        # 懒执行超时退回，避免"抢"到一条其实已经过期的指派
        svc.release_expired_assignments()
        db.session.refresh(post)

        if post.assignee_id not in (None, operator.id):
            holder = _user_brief(post.assignee_id)
            name = holder['display_name'] if holder else '其他审核员'
            return error(f'该帖子已被 {name} 认领', CODE_POST_ASSIGN_TAKEN)

        ok, message = svc.claim(post, operator)
        if not ok:
            holder = _user_brief(post.assignee_id)
            name = holder['display_name'] if holder else '其他审核员'
            return error(f'该帖子已被 {name} 认领', CODE_POST_ASSIGN_TAKEN)
        write_operation_log('claim_audit', module=post.type, target_type='post',
                            target_id=post.id, detail={'assignee_id': operator.id})
        return success({**post.to_dict(), **_assignment_payload(post, operator)}, msg=message)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/release')
@admin_required(capability=CAP_POST_AUDIT)
def release_post(post_id):
    """放弃认领，退回公共池（只能放弃自己名下的；管理员可释放任意一条）。"""
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)
        if not post.pending_audit:
            return error('该帖子不在待审核状态', CODE_POST_AUDIT_DONE)
        if post.assignee_id is None:
            return error('该帖子本来就在公共池，无需退回')
        if post.assignee_id != operator.id and not operator.is_admin:
            return error('只能放弃自己认领的帖子', CODE_FORBIDDEN, http_status=403)

        svc.release(post, operator, remark=(get_json(required=False) or {}).get('remark'))
        db.session.commit()
        write_operation_log('release_audit', module=post.type, target_type='post',
                            target_id=post.id, detail={'assignee_id': operator.id})
        return success({**post.to_dict(), **_assignment_payload(post, operator)},
                       msg='已退回公共池')
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:post_id>/audit-logs')
@admin_required(capability=CAP_POST_AUDIT)
def post_audit_logs(post_id):
    """某条帖子的审核流水（指派 / 认领 / 退回 / 通过 / 拒绝）。"""
    try:
        from ..models import PostAuditLog

        post = _get_post_or_404(post_id)
        rows = (PostAuditLog.query.filter_by(post_id=post.id)
                .order_by(PostAuditLog.id.asc()).all())
        data = []
        for row in rows:
            item = row.to_dict()
            item['actor'] = _user_brief(row.actor_id)
            item['assignee'] = _user_brief(row.assignee_id)
            data.append(item)
        return success({'post_id': post.id, 'list': data, 'total': len(data)})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('')
@admin_required(capability=CAP_POST_VIEW)
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
@admin_required(capability=CAP_POST_AUDIT)
def pending_posts():
    """待审核列表（审核工作台主入口）。

    查询参数：
        page / size / type（模块）
        scope = mine（指派给我的）| pool（公共池，无人认领）| all（默认）
        assignee_id（管理员用：看某位审核员名下有多少）

    审核员默认只看「我的 + 公共池」—— 别人已认领的帖子在待审台里看不到，
    避免多人重复审同一条；管理员不受限制。
    """
    try:
        operator = current_user()
        page, size = current_page_args()
        post_type = (request.args.get('type') or '').strip() or None
        scope = (request.args.get('scope') or '').strip()
        assignee_raw = (request.args.get('assignee_id') or '').strip()

        # 懒执行：把超时未处理的认领退回公共池（不需要定时任务）
        svc.release_expired_assignments(post_type)

        assignee_id = None
        if assignee_raw.isdigit():
            assignee_id = int(assignee_raw)

        query = svc.build_pending_query(
            post_type, scope=scope, current_user_id=operator.id, assignee_id=assignee_id
        ).order_by(Post.id.asc())
        items, total, page, size = paginate(query, page, size)

        # 列表里带上指派信息与「我能不能审」，前端直接渲染认领 / 审核按钮
        data = []
        for post in items:
            row = post.to_dict()
            row.update(_assignment_payload(post, operator))
            data.append(row)
        return paginated(data, total, page, size,
                         extra={'stats': _pending_stats(operator)})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/<int:post_id>')
@admin_required(capability=CAP_POST_VIEW)
def post_detail(post_id):
    """帖子详情（后台角色可看任意状态，含已软删除）。"""
    try:
        operator = current_user()
        post = Post.query.get(post_id)
        if post is None:
            raise ValidationError('帖子不存在', 4001)
        data = post.to_dict()
        data['deleted'] = post.is_deleted
        data['auditor'] = _user_brief(post.audited_by)
        data['author'] = _user_brief(post.user_id)
        data.update(_assignment_payload(post, operator))
        return success(data)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/audit')
@admin_required(capability=CAP_POST_AUDIT)
def audit_post(post_id):
    """审核帖子。

    请求体：
        {"audit_status": "approved"|"rejected", "remark": "审核意见",
         "status": "ongoing"（可选，管理员可直接改业务状态）}

    权限：
    - **禁止自审**：谁都不能审自己发的帖子（管理员也不例外，避免自己给自己放行）；
    - 审核员只能审公共池或指派给自己的帖子；管理员不受指派限制。
    """
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)
        payload = get_json()
        target = (payload.get('audit_status') or '').strip()
        if target not in (AUDIT_APPROVED, AUDIT_REJECTED):
            raise ValidationError('audit_status 只能是 approved / rejected')
        if post.is_deleted:
            return error('该帖子已删除，无法审核', CODE_POST_AUDIT_DONE)
        if post.user_id == operator.id:
            return error('不能审核自己发布的帖子', CODE_FORBIDDEN, http_status=403)
        if post.audit_status == target:
            return error('该帖子已处于该审核状态', CODE_POST_AUDIT_DONE)
        if not post.pending_audit:
            return error('该帖子已被审核处理', CODE_POST_AUDIT_DONE)
        if not post.is_auditable_by(operator):
            holder = _user_brief(post.effective_assignee_id)
            name = holder['display_name'] if holder else '其他审核员'
            return error(f'该帖子当前由 {name} 负责审核', CODE_POST_ASSIGN_TAKEN)

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
@admin_required(capability=CAP_POST_AUDIT)
def batch_audit():
    """批量审核：{"post_ids": [1,2], "audit_status": "approved", "remark": "..."}

    逐条做与单条审核相同的校验（禁止自审、指派归属、状态合法性），
    不合规的条目跳过并在 `skipped` 里说明原因，不会因为一条不合格而整批失败。
    """
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
        skipped = []
        for pid in ids:
            post = Post.query.get(pid)
            if post is None:
                skipped.append({'id': pid, 'reason': '帖子不存在'})
                continue
            if post.user_id == operator.id:
                skipped.append({'id': pid, 'reason': '不能审核自己发布的帖子'})
                continue
            if not post.pending_audit:
                skipped.append({'id': pid, 'reason': '不在待审核状态'})
                continue
            if not post.is_auditable_by(operator):
                skipped.append({'id': pid, 'reason': '该帖子由其他审核员负责'})
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
        write_operation_log('batch_audit', module='posts',
                            detail={'ids': ids, 'audit_status': target,
                                    'affected': affected, 'skipped': skipped})
        msg = f'已处理 {affected} 条'
        if skipped:
            msg += f'，{len(skipped)} 条被跳过'
        return success({'affected': affected, 'skipped': skipped}, msg=msg)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/status')
@admin_required(capability=CAP_POST_MANAGE)
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
@admin_required(capability=CAP_POST_MANAGE)
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
@admin_required(capability=CAP_POST_MANAGE)
def delete_post(post_id):
    """删除任意帖子（软删除 → 回收站）。审核员也具备内容处置权（按需求授予）。"""
    try:
        operator = current_user()
        post = _get_post_or_404(post_id)
        if post.is_deleted:
            return error('该帖子已在回收站中')
        svc.soft_delete(post, operator=operator)
        write_operation_log('delete', module=post.type, target_type='post', target_id=post.id,
                            detail={'operator_role': operator.role})
        send(post.user_id, '你的信息已被管理员删除',
             f'《{post.title or "无标题"}》已被管理员删除，如有疑问请联系管理员。',
             notify_type='system', ref_id=post.id)
        return success(msg='已删除并移入回收站')
    except ValidationError as exc:
        return as_error(exc)


@bp.put('/<int:post_id>')
@admin_required(capability=CAP_POST_MANAGE)
def update_post(post_id):
    """编辑帖子内容（纠正明显错误，例如联系方式写错）。

    ⚠️ 这里额外要求 `is_admin`：审核员可以删帖 / 置顶 / 改状态，
    但**不替用户改正文** —— 改内容属发布者权利，代改会造成责任不清。
    """
    try:
        operator = current_user()
        if not operator.is_admin:
            return error('审核员不能修改他人帖子内容，可先删除或退回', CODE_FORBIDDEN,
                         http_status=403)
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
@admin_required(capability=CAP_POST_VIEW)
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
