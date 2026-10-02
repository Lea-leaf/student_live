# -*- coding: utf-8 -*-
"""评论模块（v1.2 实现）。

v1.0 先把接口形状固定下来并返回明确的「未实现」响应码，
前端可以按最终接口写代码，后端补齐时无需改前端。
"""

from flask import Blueprint

from ...utils.auth import token_required
from ...utils.response import success

bp = Blueprint('comments', __name__, url_prefix='/comments')

FEATURE_CODE = 7001
FEATURE_MSG = '评论功能将在 v1.2 版本开放，接口形状已固定'


@bp.get('/posts/<int:post_id>/comments')
def list_comments(post_id):
    """帖子评论列表。"""
    return success({'list': [], 'total': 0, 'page': 1, 'size': 10}, msg='评论功能待 v1.2 开放')


@bp.post('/posts/<int:post_id>/comments')
@token_required
def create_comment(post_id):
    """发表评论。"""
    from ...utils.response import error

    return error(FEATURE_MSG, FEATURE_CODE, http_status=501)


@bp.delete('/<int:comment_id>')
@token_required
def delete_comment(comment_id):
    """删除评论（作者本人或管理员）。

    完整路径：DELETE /api/v1/comments/{id}
    """
    from ...utils.response import error

    return error(FEATURE_MSG, FEATURE_CODE, http_status=501)


__all__ = ['bp']
