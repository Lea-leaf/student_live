# -*- coding: utf-8 -*-
"""互动类模型：评论、私信、收藏、举报、通知、上传记录。

这些表在 v1.0 就建好并注册路由占位，v1.2 再补业务细节，
避免后期改表结构（需求：可扩展优先）。
"""

from ..extensions import db
from ..utils.constants import (
    NOTIFY_SYSTEM,
    NOTIFY_TYPES,
    REPORT_PENDING,
    REPORT_STATUSES,
    REPORT_STATUS_LABELS,
)
from .base import BaseModel


class Comment(BaseModel):
    """帖子评论（支持一级回复）。"""

    __tablename__ = 'comments'

    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True, comment='帖子ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='评论人')
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True, comment='父评论ID（回复）')
    content = db.Column(db.Text, nullable=False, comment='评论内容')
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='软删除')

    post = db.relationship('Post', backref=db.backref('comments_rel', lazy='dynamic'))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side='Comment.id'), lazy='dynamic')

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['author'] = self.author.to_brief() if self.author else None
        return data


class Message(BaseModel):
    """站内私信。

    当前为普通接口（拉取式）；需求预留实时化，
    未来加 WebSocket 时只需在发送成功后推送事件，表结构不用改。
    """

    __tablename__ = 'messages'

    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='发送者')
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='接收者')
    content = db.Column(db.Text, nullable=False, comment='内容')
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='是否已读')
    read_at = db.Column(db.DateTime, nullable=True, comment='阅读时间')
    #: 会话分组键：min_max 形式的用户对，便于按会话拉取消息
    conversation_key = db.Column(db.String(64), nullable=True, index=True, comment='会话键')
    #: 可选：关联帖子（从帖子详情发起私信时记录）
    post_id = db.Column(db.Integer, nullable=True, comment='关联帖子ID')

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


class Favorite(BaseModel):
    """收藏。"""

    __tablename__ = 'favorites'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='用户')
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True, comment='帖子')

    post = db.relationship('Post', backref=db.backref('favorites_rel', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='uq_favorite_user_post'),
    )


class Report(BaseModel):
    """举报。"""

    __tablename__ = 'reports'

    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='举报人')
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True, index=True, comment='被举报帖子')
    target_user_id = db.Column(db.Integer, nullable=True, index=True, comment='被举报用户（举报用户时）')
    reason = db.Column(db.String(255), nullable=False, comment='举报原因')
    detail = db.Column(db.Text, nullable=True, comment='补充说明')
    status = db.Column(db.String(16), nullable=False, default=REPORT_PENDING, index=True, comment='处理状态')
    handled_by = db.Column(db.Integer, nullable=True, comment='处理人')
    handled_at = db.Column(db.DateTime, nullable=True, comment='处理时间')
    handle_remark = db.Column(db.String(255), nullable=True, comment='处理意见')

    post = db.relationship('Post', backref=db.backref('reports_rel', lazy='dynamic'))
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='my_reports')

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['status_label'] = REPORT_STATUS_LABELS.get(self.status, self.status)
        data['reporter'] = self.reporter.to_brief() if self.reporter else None
        return data


class Notification(BaseModel):
    """站内通知（审核结果、评论、私信、系统公告统一走这里）。"""

    __tablename__ = 'notifications'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='接收人')
    type = db.Column(db.String(32), nullable=False, default=NOTIFY_SYSTEM, index=True, comment='通知类型')
    title = db.Column(db.String(128), nullable=False, comment='标题')
    content = db.Column(db.Text, nullable=True, comment='内容')
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='是否已读')
    read_at = db.Column(db.DateTime, nullable=True, comment='阅读时间')
    #: 前端跳转目标，例如 {"route": "post-detail", "post_id": 12}
    link = db.Column(db.String(255), nullable=True, comment='跳转信息(JSON)')
    ref_id = db.Column(db.Integer, nullable=True, comment='关联业务ID')

    def to_dict(self, exclude=None, extra=None):
        import json

        data = super().to_dict(exclude=exclude, extra=extra)
        try:
            data['link'] = json.loads(self.link) if self.link else None
        except (TypeError, ValueError):
            data['link'] = None
        return data


__all__ = ['Comment', 'Message', 'Favorite', 'Report', 'Notification',
           'NOTIFY_TYPES', 'REPORT_STATUSES']
