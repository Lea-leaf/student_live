# -*- coding: utf-8 -*-
"""失物招领模块（P0）。

接口一览（前缀 /api/v1/lost_found）：
    GET    /posts                 列表（游客可浏览，按需求默认开放）
    GET    /posts/{id}            详情（仅「进行中」可看）
    POST   /posts                 发布（登录 + 联系方式必填）
    POST   /posts/upload          上传图片/视频
    PUT    /posts/{id}            编辑（作者 / 管理员）
    DELETE /posts/{id}            删除（作者 / 管理员，软删除进回收站）
    GET    /my/posts              我的发布
    POST   /posts/{id}/status     更新状态（进行中/已认领/已过期/已关闭）
    POST   /posts/{id}/claim      标记已认领（状态流转的语义化快捷接口）

模块通用能力（评论/收藏/举报/私信/通知）统一走 /api/v1/common/*，
由 posts_service 与对应模块提供，本文件只做失物招领特有逻辑。
"""

from flask import Blueprint, request

from ...extensions import db
from ...models import Post
from ...models.base import paginate
from ...utils.auth import optional_token, token_required
from ...utils.config_service import get_config, get_config_int
from ...utils.constants import MODULE_LOST_FOUND, POST_CLAIMED, POST_STATUSES
from ...utils.helpers import current_page_args, guest_can_detail, guest_can_list, keyword_arg, post_audit_enabled
from ...utils.logger import write_operation_log
from ...utils.response import CODE_FORBIDDEN, CODE_POST_CLOSED, error, paginated, success
from ...utils.validators import ValidationError, as_error, get_json, parse_datetime, validate_contact
from .. import posts_service as svc

bp = Blueprint('lost_found', __name__, url_prefix='/lost_found')

MODULE = MODULE_LOST_FOUND


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------
@bp.get('/posts')
@optional_token
def list_posts():
    """帖子列表。

    查询参数：
        page / size          分页
        keyword              标题/描述模糊搜索
        status               进行中/已认领/已过期（已关闭不进公开列表）
        mine=1               只看我的发布（需登录，含全部状态）
        all=1                管理员查看全部（含待审核/已关闭）
        sort                 latest(默认) / hot / oldest
    """
    from ...utils.auth import current_user

    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        status = (request.args.get('status') or '').strip() or None
        mine = request.args.get('mine') in ('1', 'true', 'yes')
        show_all = request.args.get('all') in ('1', 'true', 'yes')
        sort = (request.args.get('sort') or 'latest').strip()
        user = current_user()

        # ---- 游客策略（需求待定项 1：默认可看列表，不能看详情） ----
        if user is None and not guest_can_list():
            return error('请先登录后浏览', CODE_FORBIDDEN, http_status=401)

        if mine and user is None:
            return error('请先登录', CODE_FORBIDDEN, http_status=401)

        query = Post.query.filter(Post.type == MODULE)

        if mine:
            # 我的发布：包含待审核 / 已拒绝 / 已关闭，且包含已软删除的？
            # 软删除不进「我的发布」，但会出现在回收站提示里（由 detail 接口返回提示）
            query = query.filter(Post.user_id == user.id, Post.is_deleted.is_(False))
        elif show_all and user and user.is_admin:
            # 管理员总览：含软删除以外的全部
            query = query.filter(Post.is_deleted.is_(False))
        else:
            query = query.filter(
                Post.is_deleted.is_(False),
                Post.audit_status == 'approved',
            )
            # 已关闭的帖子不在公开列表展示
            query = query.filter(Post.status != 'closed')

        if status:
            if status not in POST_STATUSES:
                raise ValidationError('status 取值非法')
            query = query.filter(Post.status == status)

        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(Post.title.like(like), Post.content.like(like),
                                        Post.location.like(like)))

        # 排序：置顶永远在最前
        if sort == 'hot':
            query = query.order_by(Post.is_top.desc(), Post.view_count.desc(), Post.id.desc())
        elif sort == 'oldest':
            query = query.order_by(Post.is_top.desc(), Post.id.asc())
        else:
            query = query.order_by(Post.is_top.desc(), Post.id.desc())

        items, total, page, size = paginate(query, page, size,
                                            max_size=get_config_int('page_max_size', 100))
        return paginated([item.to_brief() for item in items], total, page, size)
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------
@bp.get('/posts/<int:post_id>')
@optional_token
def post_detail(post_id):
    """帖子详情。"""
    from ...utils.auth import current_user

    try:
        user = current_user()
        post = svc.get_post(post_id, MODULE)
        if post is None:
            raise ValidationError('帖子不存在或已删除', 4001)

        # 游客不能看详情（可配置）
        if user is None and not guest_can_detail():
            return error('请先登录后查看详情', CODE_FORBIDDEN, http_status=401)

        # 作者/管理员之外，只允许「进行中且已通过审核」的帖子
        if not svc.can_view_detail(post, user):
            return error(
                '该信息当前状态不可查看详情（已认领/已过期/已关闭或未通过审核）',
                CODE_POST_CLOSED,
            )

        # 浏览量：作者本人与管理员查看不计数
        if not user or (post.user_id != user.id and not user.is_admin):
            svc.bump_view(post)

        data = post.to_dict()
        data['can_edit'] = svc.can_edit(post, user)
        data['can_audit'] = bool(user and user.is_admin and post.audit_status == 'pending')
        # 联系方式公开可见（需求明确要求），此处显式标注便于前端提示风险
        data['contact_public'] = True
        return success(data)
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 发布
# ---------------------------------------------------------------------------
@bp.post('/posts')
@token_required
def create_post():
    """发布帖子。

    支持两种提交方式：
    1. application/json：media 传已上传文件的 [{id,url,type,name}]；
    2. multipart/form-data：同时上传文件（字段名 files）+ 其他字段。
    """
    from ...utils.auth import current_user
    from ...utils.uploads import save_media_list

    try:
        user = current_user()
        is_multipart = request.content_type and 'multipart/form-data' in request.content_type
        if is_multipart:
            data = request.form.to_dict()
            files = request.files.getlist('files')
            media = []
            if files:
                media, errors = save_media_list(files, user=user)
                if errors:
                    return error('；'.join(errors), 6001)
        else:
            data = get_json()
            media = data.get('media') or []

        post = svc.build_post(MODULE, user, data, audit_enabled=post_audit_enabled())
        svc.save_post(post, media=media, ext=data.get('ext'))
        svc.attach_media(post, media)

        write_operation_log('create', module=MODULE, target_type='post', target_id=post.id,
                            detail={'title': post.title})

        msg = '发布成功' if post.audit_status == 'approved' else '发布成功，等待管理员审核后公开'
        return success(post.to_dict(), msg=msg)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/posts/upload')
@token_required
def upload_media():
    """上传图片/视频（发布前先传，拿到 media 结构再提交帖子）。"""
    from ...utils.auth import current_user
    from ...utils.uploads import save_media_list

    files = request.files.getlist('files') or request.files.getlist('file')
    if not files:
        return error('请选择要上传的文件', 6003)
    media, errors = save_media_list(files, user=current_user())
    if errors and not media:
        return error('；'.join(errors), 6001)
    return success({'media': media, 'errors': errors}, msg='上传成功')


# ---------------------------------------------------------------------------
# 编辑 / 删除
# ---------------------------------------------------------------------------
@bp.put('/posts/<int:post_id>')
@token_required
def update_post(post_id):
    """编辑帖子（作者或管理员）。"""
    from ...utils.auth import current_user
    from ...utils.validators import clean_text

    try:
        user = current_user()
        post = svc.require_post(post_id, MODULE)
        if not svc.can_edit(post, user):
            return error('只能编辑自己发布的信息', CODE_FORBIDDEN, http_status=403)

        payload = get_json()
        if 'title' in payload:
            post.title = clean_text(payload.get('title'), 128, '标题')
        if 'content' in payload:
            post.content = clean_text(payload.get('content'), 5000, '描述')
        if 'location' in payload:
            post.location = clean_text(payload.get('location'), 128, '地点')
        if 'happened_at' in payload:
            post.happened_at = parse_datetime(payload.get('happened_at'), '发生时间')
        if 'contact' in payload:
            post.contact = validate_contact(payload.get('contact'))
        if 'media' in payload:
            post.media = None
            svc.save_post(post, media=payload.get('media') or [], commit=False)
        if 'ext' in payload:
            svc.save_post(post, ext=payload.get('ext') or {}, commit=False)

        # 已通过的帖子被编辑后重新进入待审核（管理员编辑不受影响）
        if not user.is_admin and post_audit_enabled():
            post.audit_status = 'pending'
            post.audit_remark = None

        db.session.commit()
        write_operation_log('update', module=MODULE, target_type='post', target_id=post.id)
        return success(post.to_dict(), msg='修改成功')
    except ValidationError as exc:
        return as_error(exc)


@bp.delete('/posts/<int:post_id>')
@token_required
def delete_post(post_id):
    """删除帖子（软删除，进入回收站，仅管理员可见）。"""
    from ...utils.auth import current_user

    try:
        user = current_user()
        post = svc.require_post(post_id, MODULE)
        if not svc.can_edit(post, user):
            return error('只能删除自己发布的信息', CODE_FORBIDDEN, http_status=403)
        svc.soft_delete(post, operator=user)
        write_operation_log('delete', module=MODULE, target_type='post', target_id=post.id)
        return success(msg='已删除，可在管理员回收站中恢复')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 我的发布
# ---------------------------------------------------------------------------
@bp.get('/my/posts')
@token_required
def my_posts():
    """我的发布（含待审核 / 已拒绝 / 已关闭 / 已认领）。"""
    from ...utils.auth import current_user

    try:
        page, size = current_page_args()
        user = current_user()
        status = (request.args.get('status') or '').strip() or None
        audit_status = (request.args.get('audit_status') or '').strip() or None

        query = Post.query.filter(
            Post.type == MODULE, Post.user_id == user.id, Post.is_deleted.is_(False)
        )
        if status:
            query = query.filter(Post.status == status)
        if audit_status:
            query = query.filter(Post.audit_status == audit_status)

        query = query.order_by(Post.id.desc())
        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size)
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 状态流转
# ---------------------------------------------------------------------------
@bp.post('/posts/<int:post_id>/status')
@token_required
def update_status(post_id):
    """更新帖子状态。

    请求体：{"status": "claimed", "reason": "已被我领回"}
    规则：作者只能改自己的（需求 4.2），管理员可改全部。
    """
    from ...utils.auth import current_user
    from ...utils.constants import POST_STATUS_LABELS

    try:
        user = current_user()
        post = svc.require_post(post_id, MODULE)
        if not svc.can_edit(post, user):
            return error('只能修改自己发布的信息状态', CODE_FORBIDDEN, http_status=403)

        payload = get_json()
        target = (payload.get('status') or '').strip()
        if target not in POST_STATUSES:
            raise ValidationError(f'状态取值非法，可选：{" / ".join(POST_STATUSES)}')

        svc.apply_status(post, target, operator=user, reason=payload.get('reason'))
        db.session.commit()
        write_operation_log('update_status', module=MODULE, target_type='post', target_id=post.id,
                            detail={'status': target})
        return success(post.to_dict(), msg=f'已标记为「{POST_STATUS_LABELS.get(target, target)}」')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/posts/<int:post_id>/claim')
@token_required
def claim_post(post_id):
    """标记已认领（语义化快捷接口，等价于 status=claimed）。"""
    from ...utils.auth import current_user

    try:
        user = current_user()
        post = svc.require_post(post_id, MODULE)
        if not svc.can_edit(post, user):
            return error('只能操作自己发布的信息', CODE_FORBIDDEN, http_status=403)
        svc.apply_status(post, POST_CLAIMED, operator=user)
        db.session.commit()
        write_operation_log('claim', module=MODULE, target_type='post', target_id=post.id)
        return success(post.to_dict(), msg='已标记为「已认领」，该信息不再可查看详情')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 模块元信息
# ---------------------------------------------------------------------------
@bp.get('/meta')
def module_meta():
    """模块元信息：状态字典、字段要求、公告等，供前端渲染筛选器。"""
    from ...utils.constants import AUDIT_STATUS_LABELS, POST_STATUS_LABELS

    return success({
        'module': MODULE,
        'name': get_config('site_name', '校园生活平台'),
        'statuses': [{'value': key, 'label': label} for key, label in POST_STATUS_LABELS.items()],
        'audit_statuses': [{'value': key, 'label': label} for key, label in AUDIT_STATUS_LABELS.items()],
        'fields': {
            'title': {'required': False, 'label': '标题'},
            'content': {'required': False, 'label': '描述'},
            'media': {'required': False, 'label': '图片/视频'},
            'location': {'required': False, 'label': '地点'},
            'happened_at': {'required': False, 'label': '时间'},
            'contact': {'required': True, 'label': '联系方式', 'public': True},
        },
        'audit_enabled': post_audit_enabled(),
    })


__all__ = ['bp']
