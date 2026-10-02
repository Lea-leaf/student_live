# -*- coding: utf-8 -*-
"""收藏模块。

v1.0 直接可用（表结构简单、前端入口已预留），
目的是让「模块通用能力」清单里的收藏项不留空。
"""

from flask import Blueprint

from ...extensions import db
from ...models import Favorite, Post
from ...models.base import paginate
from ...utils.auth import token_required
from ...utils.helpers import current_page_args
from ...utils.logger import write_operation_log
from ...utils.response import error, paginated, success
from ...utils.validators import ValidationError, as_error

bp = Blueprint('favorites', __name__, url_prefix='/favorites')


@bp.get('')
@token_required
def list_favorites():
    """我的收藏列表。"""
    from ...utils.auth import current_user

    try:
        page, size = current_page_args()
        query = (
            Favorite.query.join(Post, Favorite.post_id == Post.id)
            .filter(Favorite.user_id == current_user().id, Post.is_deleted.is_(False))
            .order_by(Favorite.id.desc())
        )
        items, total, page, size = paginate(query, page, size)
        data = []
        for fav in items:
            item = fav.post.to_brief() if fav.post else None
            if item:
                item['favorite_id'] = fav.id
                item['favorited_at'] = fav.created_at.strftime('%Y-%m-%d %H:%M:%S') if fav.created_at else None
                data.append(item)
        return paginated(data, total, page, size)
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/posts/<int:post_id>')
@token_required
def toggle_favorite(post_id):
    """收藏 / 取消收藏（幂等切换）。"""
    from ...utils.auth import current_user

    user = current_user()
    post = Post.query.filter(Post.id == post_id, Post.is_deleted.is_(False)).first()
    if post is None:
        return error('帖子不存在或已删除', 4001)

    existing = Favorite.query.filter_by(user_id=user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        post.favorite_count = max((post.favorite_count or 1) - 1, 0)
        db.session.commit()
        return success({'favorited': False, 'favorite_count': post.favorite_count}, msg='已取消收藏')

    db.session.add(Favorite(user_id=user.id, post_id=post_id))
    post.favorite_count = (post.favorite_count or 0) + 1
    db.session.commit()
    write_operation_log('favorite', module=post.type, target_type='post', target_id=post_id)
    return success({'favorited': True, 'favorite_count': post.favorite_count}, msg='收藏成功')


@bp.get('/check/<int:post_id>')
@token_required
def check_favorite(post_id):
    """查询是否已收藏。"""
    from ...utils.auth import current_user

    exists = Favorite.query.filter_by(user_id=current_user().id, post_id=post_id).first() is not None
    return success({'favorited': exists})


__all__ = ['bp']
