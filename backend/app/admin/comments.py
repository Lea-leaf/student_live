# -*- coding: utf-8 -*-
"""管理端 - 评论管理。

v1.0 补齐：管理员需要能看到并删除库里的评论（含种子数据与历史评论），
否则违规评论只能靠直接改数据库，这在实际使用中不可接受。
**发表评论**仍属 v1.2，不在此模块提供。

接口一览（前缀 /api/v1/admin/comments）：
    GET    /              评论列表（按帖子/用户/关键词筛选）
    GET    /stats         评论概览
    DELETE /{id}          删除评论（软删除；?purge=1 彻底删除）
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
    """删除评论。默认软删除，`?purge=1` 彻底删除（含子回复）。"""
    try:
        comment = Comment.query.get(comment_id)
        if comment is None:
            raise ValidationError('评论不存在', 1002)

        post_id = comment.post_id

        if request.args.get('purge') in ('1', 'true', 'yes'):
            from ..utils.cleanup import purge_comment

            stats = purge_comment(comment)
            write_operation_log('purge_comment', module='comments', target_type='comment',
                                target_id=comment_id, detail=stats)
            return success(stats, msg='评论已彻底删除')

        comment.is_deleted = True
        db.session.commit()
        post = Post.query.get(post_id)
        if post:
            post.comment_count = Comment.query.filter_by(post_id=post_id, is_deleted=False).count()
            db.session.commit()
        write_operation_log('delete_comment', module='comments', target_type='comment',
                            target_id=comment_id)
        return success({'comment_id': comment_id}, msg='评论已删除')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
