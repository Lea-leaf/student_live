# -*- coding: utf-8 -*-
"""评论模块。

**当前状态**：
- 「删除评论」已可用（v1.0 补齐）—— 管理员需要能清理不当言论，
  否则库里出现违规评论却无法处理；
- 「发表评论」仍为 v1.2 占位，返回明确的待开放错误码，接口形状已固定。

接口一览（前缀 /api/v1/comments）：
    GET    /posts/{id}/comments   评论列表（已可返回真实数据）
    POST   /posts/{id}/comments   发表评论（v1.2 开放，501）
    DELETE /{id}                  删除评论（本人或管理员；管理员可 ?purge=1 彻底删除）
"""

from flask import Blueprint, request

from ...extensions import db
from ...models import Comment, Post
from ...models.base import paginate
from ...utils.auth import current_user, token_required
from ...utils.constants import ADMIN_ROLES
from ...utils.helpers import current_page_args
from ...utils.logger import write_operation_log
from ...utils.response import CODE_FORBIDDEN, error, paginated, success
from ...utils.validators import ValidationError, as_error

bp = Blueprint('comments', __name__, url_prefix='/comments')

FEATURE_CODE = 7001
FEATURE_MSG = '评论发布将在 v1.2 版本开放，接口形状已固定'


def _sync_comment_count(post_id):
    """回写帖子的评论计数，避免计数与实际行数漂移。"""
    post = Post.query.get(post_id) if post_id else None
    if post:
        post.comment_count = Comment.query.filter_by(post_id=post_id, is_deleted=False).count()
        db.session.commit()


@bp.get('/posts/<int:post_id>/comments')
def list_comments(post_id):
    """帖子评论列表（分页，只返回未删除的）。"""
    try:
        page, size = current_page_args()
        query = (
            Comment.query.filter_by(post_id=post_id, is_deleted=False)
            .order_by(Comment.id.asc())
        )
        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/posts/<int:post_id>/comments')
@token_required
def create_comment(post_id):
    """发表评论（待 v1.2 开放）。"""
    return error(FEATURE_MSG, FEATURE_CODE, http_status=501)


@bp.delete('/<int:comment_id>')
@token_required
def delete_comment(comment_id):
    """删除评论。

    - 普通用户：只能删自己的评论，软删除（`is_deleted=True`），内容不再展示；
    - 管理员：可删任意评论，并可用 `?purge=1` 彻底删除；
    - 两种方式都会回写帖子的 `comment_count`。
    """
    try:
        user = current_user()
        comment = Comment.query.get(comment_id)
        if comment is None or comment.is_deleted:
            raise ValidationError('评论不存在或已删除', 1002)

        is_admin = user.role in ADMIN_ROLES
        if not is_admin and comment.user_id != user.id:
            return error('只能删除自己的评论', CODE_FORBIDDEN, http_status=403)

        if is_admin and request.args.get('purge') in ('1', 'true', 'yes'):
            from ...utils.cleanup import purge_comment

            stats = purge_comment(comment)
            write_operation_log('purge_comment', module='comments', target_type='comment',
                                target_id=comment_id, detail=stats)
            return success(stats, msg='评论已彻底删除')

        comment.is_deleted = True
        db.session.commit()
        _sync_comment_count(comment.post_id)
        write_operation_log('delete_comment', module='comments', target_type='comment',
                            target_id=comment_id)
        return success({'comment_id': comment_id}, msg='评论已删除')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
