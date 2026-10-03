# -*- coding: utf-8 -*-
"""管理端 - 评论管理。

管理员需要能看到并删除库里的评论（含种子数据与历史评论）。
v1.2 起评论区不再对用户提供软删除：管理员删除 = 数据库物理删除，
并同步清理子回复、点赞、媒体文件与相关互动通知；操作日志保留评论内容快照。

接口一览（前缀 /api/v1/admin/comments）：
    GET    /              评论列表（按帖子/用户/关键词筛选）
    GET    /stats         评论概览
    DELETE /{id}          删除评论（物理删除，含整棵子回复；兼容保留 ?purge=1 参数）
"""

from flask import Blueprint, request

from ..extensions import db
from ..models import Comment, Post, User
from ..models.base import paginate
from ..utils.auth import admin_required
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.response import paginated, success
from ..utils.validators import ValidationError, as_error

bp = Blueprint('admin_comments', __name__, url_prefix='/comments')


@bp.get('')
@admin_required
def list_comments():
    """评论列表。

    查询参数：page / size / keyword / post_id / user_id / include_deleted
    """
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        post_id = request.args.get('post_id')
        user_id = request.args.get('user_id')
        include_deleted = request.args.get('include_deleted', '0') in ('1', 'true')

        query = Comment.query
        if not include_deleted:
            query = query.filter(Comment.is_deleted.is_(False))
        if keyword:
            query = query.filter(Comment.content.like(f'%{keyword}%'))
        if post_id:
            query = query.filter(Comment.post_id == int(post_id))
        if user_id:
            query = query.filter(Comment.user_id == int(user_id))
        query = query.order_by(Comment.id.desc())

        items, total, page, size = paginate(query, page, size)
        data = []
        for item in items:
            row = item.to_dict()
            post = Post.query.get(item.post_id)
            row['post'] = {'id': post.id, 'title': post.title, 'is_deleted': post.is_deleted} if post else None
            data.append(row)
        return paginated(data, total, page, size)
    except (ValidationError, TypeError, ValueError) as exc:
        return as_error(exc)


@bp.get('/stats')
@admin_required
def comment_stats():
    """评论概览。"""
    total = Comment.query.count()
    deleted = Comment.query.filter(Comment.is_deleted.is_(True)).count()
    top = (
        db.session.query(Comment.post_id, db.func.count(Comment.id))
        .filter(Comment.is_deleted.is_(False))
        .group_by(Comment.post_id)
        .order_by(db.func.count(Comment.id).desc())
        .limit(5)
        .all()
    )
    return success({
        'total': total,
        'visible': total - deleted,
        'deleted': deleted,
        'top_posts': [{'post_id': pid, 'count': count} for pid, count in top],
    })


@bp.delete('/<int:comment_id>')
@admin_required
def delete_comment(comment_id):
    """管理员删除评论：数据库物理删除（含子回复、点赞、媒体与相关通知）。

    兼容旧的 `?purge=1` 参数，但无论是否传参都是物理删除。
    删除前把评论内容、作者、帖子等数据库信息写进操作日志，便于审计。
    """
    try:
        comment = Comment.query.get(comment_id)
        if comment is None:
            raise ValidationError('评论不存在', 1002)

        from ..utils.cleanup import purge_comment

        detail = {
            'content': (comment.content or '')[:200],
            'post_id': comment.post_id,
            'user_id': comment.user_id,
            'parent_id': comment.parent_id,
            'like_count': comment.like_count,
            'reply_count': comment.reply_count,
            'by_admin': True,
        }
        stats = purge_comment(comment)
        detail.update(stats)
        write_operation_log('delete_comment', module='comments', target_type='comment',
                            target_id=comment_id, detail=detail)
        return success(stats, msg='评论已删除')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
