# -*- coding: utf-8 -*-
"""评论模块（v1.2：发表 / 楼中楼回复 / 图片语音 / 互动通知）。

接口一览（前缀 /api/v1/comments）：
    GET    /posts/{id}/comments   评论列表（顶级评论分页，自带整棵楼中楼子树）
    POST   /posts/{id}/comments   发表评论 / 回复（content + media + parent_id）
    DELETE /{id}                  删除评论（本人或管理员；管理员可 ?purge=1 彻底删除）
    （点赞接口在 /api/v1/likes/comments/{id}）

楼中楼规则：
- `parent_id` 指向直接父评论，`root_id` 始终指向顶级评论；
- 列表接口用 `root_id` 一次性取回整棵子树，前端不需要递归请求；
- `reply_to_user_id` 记录被回复的人，默认取直接父评论作者，用于「回复 @某人」展示与通知。
"""

import json
import re
from datetime import datetime

from flask import Blueprint, request

from ...extensions import db
from ...models import Comment, CommentLike, Post, User
from ...models.base import paginate
from ...utils.auth import current_user, optional_token, token_required
from ...utils.constants import ADMIN_ROLES, NOTIFY_COMMENT, NOTIFY_MENTION
from ...utils.helpers import current_page_args
from ...utils.logger import write_operation_log
from ...utils.notification_service import send
from ...utils.response import CODE_FORBIDDEN, CODE_MESSAGE_RECALL_EXPIRED, error, paginated, success
from ...utils.uploads import attach_upload_owners, sanitize_media_list
from ...utils.validators import ValidationError, as_error, clean_text, get_json
from .. import posts_service as svc

bp = Blueprint('comments', __name__, url_prefix='/comments')

#: @ 用户昵称 / 学号 / 用户名，例：@小明、@20210001
MENTION_RE = re.compile(r'@([A-Za-z0-9_\u4e00-\u9fff-]{1,20})')
#: 单条评论最多提醒的人数，避免一次 @ 全站造成通知刷屏
MENTION_NOTIFY_LIMIT = 5

#: 用户撤回自己评论的时间窗口：5 分钟
RECALL_WINDOW_SECONDS = 5 * 60


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _display_name(user):
    return getattr(user, 'nickname', None) or getattr(user, 'username', None) \
        or getattr(user, 'student_id', '同学')


def _as_int(value, field):
    if value in (None, '', 'null', 'undefined'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'{field} 必须是整数') from None


def _summary(comment):
    """通知里显示的内容摘要（纯媒体评论给类型占位）。"""
    text = (comment.content or '').strip()
    if text:
        return text[:40]
    types = [item.get('type') for item in comment.media_list() if isinstance(item, dict)]
    if not types:
        return '[评论]'
    return {'audio': '[语音]', 'image': '[图片]', 'video': '[视频]'}.get(types[0], '[媒体]')


def _sync_comment_count(post_id):
    """回写帖子的评论计数（含楼中楼，避免计数漂移）。"""
    post = Post.query.get(post_id) if post_id else None
    if post:
        post.comment_count = Comment.query.filter_by(
            post_id=post_id, is_deleted=False).count()
    return post


def _mention_users(content, exclude_ids):
    """解析内容里的 @xxx，返回匹配到的用户（去重、排除操作者与已通知对象）。"""
    names = list(dict.fromkeys(MENTION_RE.findall(content or '')))
    if not names:
        return []
    users = User.query.filter(
        db.or_(
            User.nickname.in_(names),
            User.username.in_(names),
            User.student_id.in_(names),
        )
    ).limit(20).all()
    result = []
    for user in users:
        if user.id in exclude_ids:
            continue
        result.append(user)
        if len(result) >= MENTION_NOTIFY_LIMIT:
            break
    return result


def _notify_comment_created(comment, post, actor, parent):
    """评论 / 回复 / @ 三类互动通知，同一用户只发一条。"""
    notified = set()
    link = {'route': 'post-detail', 'post_id': post.id, 'comment_id': comment.id}
    summary = _summary(comment)
    actor_name = _display_name(actor)

    def notify(user_id, title, content, notify_type=NOTIFY_COMMENT):
        if not user_id or user_id == actor.id or user_id in notified:
            return
        send(user_id, title, content, notify_type=notify_type,
             ref_id=comment.id, link=link)
        notified.add(user_id)

    # 1) 帖子作者：你的信息收到新评论
    notify(post.user_id, '你的信息收到新评论', f'{actor_name}：{summary}')

    # 2) 直接父评论作者：有人回复了你的评论
    if parent:
        notify(parent.user_id, '有人回复了你的评论', f'{actor_name} 回复：{summary}')

    # 3) 显式回复某人（reply_to_user_id）
    notify(comment.reply_to_user_id, '有人在评论中 @ 了你', f'{actor_name}：{summary}')

    # 4) 正文里的 @xxx
    for user in _mention_users(comment.content or '', notified | {actor.id}):
        notify(user.id, '有人在评论中 @ 了你', f'{actor_name}：{summary}',
               notify_type=NOTIFY_MENTION)


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------
@bp.get('/posts/<int:post_id>/comments')
@optional_token
def list_comments(post_id):
    """帖子评论列表：顶级评论分页，每条顶级评论自带整棵楼中楼子树。

    返回字段额外包含 `liked`（当前用户是否已点赞）与 `total_all`（全部评论数）。
    """
    try:
        post = Post.query.filter(Post.id == post_id, Post.is_deleted.is_(False)).first()
        if post is None:
            raise ValidationError('帖子不存在或已删除', 4001)

        page, size = current_page_args()
        user = current_user()
        query = (
            Comment.query.filter_by(post_id=post_id, is_deleted=False)
            .filter(Comment.parent_id.is_(None))
            .order_by(Comment.id.desc())
        )
        roots, total, page, size = paginate(query, page, size)
        root_ids = [item.id for item in roots]

        # 一次取回整棵子树：root_id 指向顶级评论，不需要递归查库
        children = []
        if root_ids:
            children = (
                Comment.query.filter(
                    Comment.post_id == post_id,
                    Comment.is_deleted.is_(False),
                    Comment.root_id.in_(root_ids),
                    Comment.id.notin_(root_ids),
                )
                .order_by(Comment.id.asc())
                .all()
            )

        liked_ids = set()
        all_ids = root_ids + [item.id for item in children]
        if user and all_ids:
            liked_ids = {
                row[0]
                for row in db.session.query(CommentLike.comment_id)
                .filter(CommentLike.user_id == user.id, CommentLike.comment_id.in_(all_ids))
                .all()
            }

        children_by_root = {}
        for child in children:
            children_by_root.setdefault(child.root_id, []).append(child)

        data = []
        for root in roots:
            root_data = root.to_dict()
            root_data['liked'] = root.id in liked_ids
            replies = []
            for child in children_by_root.get(root.id, []):
                child_data = child.to_dict()
                child_data['liked'] = child.id in liked_ids
                replies.append(child_data)
            root_data['replies'] = replies
            data.append(root_data)

        total_all = Comment.query.filter_by(post_id=post_id, is_deleted=False).count()
        return paginated(data, total, page, size,
                         extra={'total_all': total_all, 'post_id': post_id})
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 发表 / 回复
# ---------------------------------------------------------------------------
@bp.post('/posts/<int:post_id>/comments')
@token_required
def create_comment(post_id):
    """发表评论或楼中楼回复。

    请求体（JSON 或 multipart/form-data）：
        content            文本内容（纯图片/语音评论可为空）
        parent_id          直接父评论 ID（顶级评论留空）
        reply_to_user_id   被回复用户 ID（留空默认父评论作者）
        media              已上传媒体数组（先调 /common/upload）
        files              multipart 时可随表单一起上传
    """
    from ...utils.auth import current_user as _current_user
    from ...utils.uploads import save_media_list

    try:
        user = _current_user()
        post = svc.get_post(post_id)
        if post is None:
            raise ValidationError('帖子不存在或已删除', 4001)
        if not svc.can_view_detail(post, user):
            return error('该信息当前不可评论', 4002)

        is_multipart = bool(request.content_type and 'multipart/form-data' in request.content_type)
        if is_multipart:
            data = request.form.to_dict()
            files = request.files.getlist('files') or request.files.getlist('file')
        else:
            data = get_json()
            files = []

        content = clean_text(data.get('content'), 2000, '评论内容')
        parent_id = _as_int(data.get('parent_id'), 'parent_id')
        reply_to_user_id = _as_int(data.get('reply_to_user_id'), 'reply_to_user_id')

        parent = None
        root_id = None
        if parent_id:
            parent = Comment.query.filter_by(
                id=parent_id, post_id=post_id, is_deleted=False).first()
            if parent is None:
                raise ValidationError('父评论不存在或已删除', 1002)
            root_id = parent.root_id or parent.id
            if reply_to_user_id is None:
                reply_to_user_id = parent.user_id
        if reply_to_user_id:
            target = User.query.get(reply_to_user_id)
            if target is None:
                raise ValidationError('被回复的用户不存在', 3002)

        # 媒体：multipart 先落盘，JSON 则校验引用的是否为当前用户上传的文件
        if files:
            saved, errors = save_media_list(files, user=user)
            if errors and not saved:
                return error('；'.join(errors), 6001)
            media, media_error = sanitize_media_list(saved, user=user)
        else:
            media, media_error = sanitize_media_list(data.get('media') or [], user=user)
        if media_error:
            raise ValidationError(media_error)

        if not content and not media:
            raise ValidationError('评论内容不能为空')

        comment = Comment(
            post_id=post_id,
            user_id=user.id,
            parent_id=parent_id,
            root_id=root_id,
            content=content or '',
            media=json.dumps(media, ensure_ascii=False) if media else None,
            reply_to_user_id=reply_to_user_id,
            like_count=0,
            reply_count=0,
        )
        db.session.add(comment)
        db.session.flush()
        if comment.root_id is None:
            comment.root_id = comment.id

        attach_upload_owners(media, 'comment', comment.id)
        if parent:
            parent.reply_count = (parent.reply_count or 0) + 1
        _sync_comment_count(post_id)
        db.session.commit()

        write_operation_log('create_comment', module='comments', target_type='comment',
                            target_id=comment.id,
                            detail={'post_id': post_id, 'parent_id': parent_id})
        _notify_comment_created(comment, post, user, parent)

        result = comment.to_dict()
        result['liked'] = False
        result['replies'] = []
        return success(result, msg='评论成功')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------
@bp.delete('/<int:comment_id>')
@token_required
def delete_comment(comment_id):
    """撤回自己的评论 / 管理员删除评论。

    - 普通用户：只能撤回**自己**的评论，且必须在发出后 5 分钟内，**数据库物理删除**；
    - 管理员：可删除任意评论，同样是**数据库物理删除**（含子回复、点赞、媒体、相关通知），
      删除前会把评论内容等数据库信息写进操作日志，便于审计；
    - 不再提供用户软删除：`comments.is_deleted` 仅用于兼容历史数据与后台旧的软删记录。
    """
    try:
        user = current_user()
        comment = Comment.query.get(comment_id)
        if comment is None:
            raise ValidationError('评论不存在或已删除', 1002)

        is_admin = user.role in ADMIN_ROLES
        if is_admin:
            action = 'delete_comment'
            success_msg = '评论已删除'
        else:
            if comment.user_id != user.id:
                return error('只能撤回自己的评论', CODE_FORBIDDEN, http_status=403)
            elapsed = (datetime.now() - comment.created_at).total_seconds()
            if elapsed > RECALL_WINDOW_SECONDS:
                return error('超过 5 分钟的评论不能撤回', CODE_MESSAGE_RECALL_EXPIRED)
            action = 'recall_comment'
            success_msg = '评论已撤回'

        # 管理员删除前保留一份数据库信息快照，便于日志审计
        detail = {
            'content': (comment.content or '')[:200],
            'post_id': comment.post_id,
            'user_id': comment.user_id,
            'parent_id': comment.parent_id,
            'like_count': comment.like_count,
            'reply_count': comment.reply_count,
            'by_admin': is_admin,
        }
        from ...utils.cleanup import purge_comment

        stats = purge_comment(comment)
        detail.update(stats)
        write_operation_log(action, module='comments', target_type='comment',
                            target_id=comment_id, detail=detail)
        return success(stats, msg=success_msg)
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']