# -*- coding: utf-8 -*-
"""点赞模型（与「收藏」是两个独立功能）。

**为什么点赞和收藏要分开**（需求明确要求）：

| 维度 | 收藏 `Favorite` | 点赞 `PostLike` |
|---|---|---|
| 语义 | 私有书签，「我留着以后看」 | 公开表态，「我觉得有用/喜欢」 |
| 可见性 | 只有自己能看到列表 | 计数公开显示在帖子上 |
| 计数 | `posts.favorite_count` | `posts.like_count` |
| 取消 | 从收藏夹移除 | 再点一次取消点赞 |

两者都是「用户 + 对象」的唯一约束结构，但**语义与展示不同**，因此分开建表；
合并成一张表加 `type` 字段虽然可行，但会让「我的收藏」和「点赞数」的查询互相干扰。

评论点赞同理，单独一张 `comment_likes`。
"""

from ..extensions import db
from .base import BaseModel


class PostLike(BaseModel):
    """帖子点赞。"""

    __tablename__ = 'post_likes'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='点赞人')
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True, comment='帖子')

    user = db.relationship('User', foreign_keys=[user_id], backref='post_likes')
    post = db.relationship('Post', backref=db.backref('likes_rel', lazy='dynamic'))

    __table_args__ = (
        # 同一个人对同一帖子只能点赞一次（再点即取消）
        db.UniqueConstraint('user_id', 'post_id', name='uq_post_like_user_post'),
    )

    def __repr__(self):
        return f'<PostLike user={self.user_id} post={self.post_id}>'


class CommentLike(BaseModel):
    """评论点赞（楼中楼里每条评论独立计数）。"""

    __tablename__ = 'comment_likes'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='点赞人')
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False, index=True, comment='评论')

    user = db.relationship('User', foreign_keys=[user_id], backref='comment_likes')
    comment = db.relationship('Comment', backref=db.backref('likes_rel', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'comment_id', name='uq_comment_like_user_comment'),
    )

    def __repr__(self):
        return f'<CommentLike user={self.user_id} comment={self.comment_id}>'


__all__ = ['PostLike', 'CommentLike']
