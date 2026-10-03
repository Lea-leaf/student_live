# -*- coding: utf-8 -*-
"""点赞模块（帖子点赞 + 评论点赞）。

需求把「点赞」与「收藏」明确拆成两个独立功能：
- 收藏是私有书签（/favorites），点赞是公开表态（/likes）；
- 帖子点赞计数写 `posts.like_count`，评论点赞计数写 `comments.like_count`；
- 唯一约束保证同一用户对同一对象只点赞一次，再次调用即取消（幂等切换）。

互动通知：点赞成功时通知内容作者（自己赞自己不通知）。
"""

from flask import Blueprint

from ...extensions import db
from ...models import Comment, CommentLike, Post, PostLike
from ...utils.auth import current_user, token_required
from ...utils.constants import NOTIFY_LIKE
from ...utils.logger import write_operation_log
from ...utils.notification_service import send
from ...utils.response import CODE_FORBIDDEN, error, success
from ...utils.validators import ValidationError, as_error
from .. import posts_service as svc

bp = Blueprint('likes', __name__, url_prefix='/likes')


def _display_name(user):
    return getattr(user, 'nickname', None) or getattr(user, 'username', None) or getattr(user, 'student_id', '同学')


def _link_post(post_id):
    return {'route': 'post-detail', 'post_id': post_id}


# ---------------------------------------------------------------------------
# 帖子点赞
# ---------------------------------------------------------------------------
@bp.post('/posts/<int:post_id>')
@token_required
def toggle_post_like(post_id):
    """帖子点赞 / 取消点赞（幂等切换）。"""
    user = current_user()
    post = svc.get_post(post_id)
    if post is None:
        return error('帖子不存在或已删除', 4001)
    if not svc.can_view_detail(post, user):
        return error('该信息当前不可访问', 4002)

    existing = PostLike.query.filter_by(user_id=user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        post.like_count = max((post.like_count or 1) - 1, 0)
        db.session.commit()
        write_operation_log('unlike', module='likes', target_type='post', target_id=post_id)
        return success({'liked': False, 'like_count': post.like_count}, msg='已取消点赞')

    db.session.add(PostLike(user_id=user.id, post_id=post_id))
    post.like_count = (post.like_count or 0) + 1
    db.session.commit()
    write_operation_log('like', module='likes', target_type='post', target_id=post_id)

    if post.user_id != user.id:
        send(
            post.user_id,
            '你的信息被点赞了',
            f'{_display_name(user)} 赞了《{post.title or "无标题"}》',
            notify_type=NOTIFY_LIKE,
            ref_id=post.id,
            link=_link_post(post.id),
        )
    return success({'liked': True, 'like_count': post.like_count}, msg='点赞成功')


@bp.get('/posts/<int:post_id>')
@token_required
def post_like_state(post_id):
    """查询当前用户是否已点赞某帖子。"""
    user = current_user()
    post = Post.query.get(post_id)
    if post is None or post.is_deleted:
        return error('帖子不存在或已删除', 4001)
    liked = PostLike.query.filter_by(user_id=user.id, post_id=post_id).first() is not None
    return success({'liked': liked, 'like_count': post.like_count or 0})


# ---------------------------------------------------------------------------
# 评论点赞
# ---------------------------------------------------------------------------
@bp.post('/comments/<int:comment_id>')
@token_required
def toggle_comment_like(comment_id):
    """评论点赞 / 取消点赞（楼中楼的标配）。"""
    user = current_user()
    comment = Comment.query.get(comment_id)
    if comment is None or comment.is_deleted:
        return error('评论不存在或已删除', 1002)
    post = Post.query.get(comment.post_id)
    if post is None or post.is_deleted:
        return error('帖子不存在或已删除', 4001)
    if not svc.can_view_detail(post, user):
        return error('该信息当前不可访问', 4002)

    existing = CommentLike.query.filter_by(user_id=user.id, comment_id=comment_id).first()
    if existing:
        db.session.delete(existing)
        comment.like_count = max((comment.like_count or 1) - 1, 0)
        db.session.commit()
        write_operation_log('unlike', module='likes', target_type='comment', target_id=comment_id)
        return success({'liked': False, 'like_count': comment.like_count}, msg='已取消点赞')

    db.session.add(CommentLike(user_id=user.id, comment_id=comment_id))
    comment.like_count = (comment.like_count or 0) + 1
    db.session.commit()
    write_operation_log('like', module='likes', target_type='comment', target_id=comment_id)

    if comment.user_id != user.id:
        summary = (comment.content or '')[:30]
        if not summary:
            summary = '[媒体评论]'
        send(
            comment.user_id,
            '你的评论被点赞了',
            f'{_display_name(user)} 赞了你的评论：{summary}',
            notify_type=NOTIFY_LIKE,
            ref_id=comment.id,
            link={'route': 'post-detail', 'post_id': post.id, 'comment_id': comment.id},
        )
    return success({'liked': True, 'like_count': comment.like_count}, msg='点赞成功')


@bp.get('/comments/<int:comment_id>')
@token_required
def comment_like_state(comment_id):
    """查询当前用户是否已点赞某评论。"""
    user = current_user()
    comment = Comment.query.get(comment_id)
    if comment is None or comment.is_deleted:
        return error('评论不存在或已删除', 1002)
    liked = CommentLike.query.filter_by(user_id=user.id, comment_id=comment_id).first() is not None
    return success({'liked': liked, 'like_count': comment.like_count or 0})


__all__ = ['bp']