# -*- coding: utf-8 -*-
"""互动类模型：评论、私信、收藏、点赞、举报、通知、上传记录。

设计要点（v1.1 结构收口）：
- **评论支持楼中楼**：`root_id` 指向顶级评论、`parent_id` 指向直接父级。
  只查一层用 `parent_id`，一次取整棵子树用 `root_id`（避免递归查库）。
- **评论与私信都能带媒体**：`media` 列存 JSON 数组，结构与帖子完全一致
  （图片/视频/语音），因此存储层、展示组件、上传接口全部复用。
- **点赞与收藏是两个独立功能**：`Favorite`（收藏，私有书签）与
  `Like`（点赞，公开计数，见 `like.py`）分开建表，各自计数互不影响。
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
    """帖子评论（支持**楼中楼**多级回复）。"""

    __tablename__ = 'comments'

    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True, comment='帖子ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='评论人')
    #: 直接父级；顶级评论为 NULL
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True, index=True,
                          comment='父评论ID（直接上级）')
    #: 顶级评论 ID；顶级评论自己存自己的 id（插入后再回填），便于一次查出整棵子树
    root_id = db.Column(db.Integer, nullable=True, index=True, comment='顶级评论ID（楼中楼）')
    content = db.Column(db.Text, nullable=False, comment='评论内容')
    #: 图片 / 视频 / 语音，JSON 数组，结构与 posts.media 完全一致
    media = db.Column(db.Text, nullable=True, comment='图片/视频/语音(JSON数组)')
    #: 被回复的用户（用于「回复 @某人」提示与通知）
    reply_to_user_id = db.Column(db.Integer, nullable=True, index=True, comment='被回复的用户ID')
    like_count = db.Column(db.Integer, nullable=False, default=0, comment='点赞数')
    reply_count = db.Column(db.Integer, nullable=False, default=0, comment='直接回复数（冗余计数）')
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='软删除')

    post = db.relationship('Post', backref=db.backref('comments_rel', lazy='dynamic'))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side='Comment.id'),
                              lazy='dynamic', foreign_keys=[parent_id])

    # ------------------------------------------------------------------
    def media_list(self):
        """解析 media JSON，容错返回列表。"""
        import json

        try:
            data = json.loads(self.media) if self.media else []
            return data if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['media'] = self.media_list()
        data['author'] = self.author.to_brief() if self.author else None
        if self.reply_to_user_id:
            from .user import User

            target = User.query.get(self.reply_to_user_id)
            data['reply_to'] = target.to_brief() if target else None
        else:
            data['reply_to'] = None
        return data

    def to_brief(self):
        """楼中楼列表用的精简结构。"""
        return {
            'id': self.id,
            'post_id': self.post_id,
            'parent_id': self.parent_id,
            'root_id': self.root_id,
            'content': self.content,
            'media': self.media_list(),
            'like_count': self.like_count,
            'reply_count': self.reply_count,
            'author': self.author.to_brief() if self.author else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class Message(BaseModel):
    """站内私信（支持文字 / 图片 / 语音）。

    已读回执：`is_read` + `read_at`；接收方读取后回写，发送方借此显示「已读」。
    未读红点：由 `GET /messages/unread-count` 汇总，前端轮询。
    实时化预留：加 WebSocket 时只需在发送成功后推送事件，本表结构不用改。
    """

    __tablename__ = 'messages'

    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='发送者')
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='接收者')
    content = db.Column(db.Text, nullable=True, comment='文本内容（发表情/语音时可空）')
    #: 消息类型：text / image / voice / video；便于前端按类型渲染气泡
    msg_type = db.Column(db.String(16), nullable=False, default='text', index=True, comment='消息类型')
    #: 图片 / 语音 / 视频，JSON 数组，结构与 posts.media 一致
    media = db.Column(db.Text, nullable=True, comment='图片/语音/视频(JSON数组)')
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='是否已读')
    read_at = db.Column(db.DateTime, nullable=True, comment='阅读时间')
    #: 会话分组键：min_max 形式的用户对，便于按会话拉取消息
    conversation_key = db.Column(db.String(64), nullable=True, index=True, comment='会话键')
    #: 可选：关联帖子（从帖子详情发起私信时记录）
    post_id = db.Column(db.Integer, nullable=True, comment='关联帖子ID')
    #: 发送方是否已撤回/删除（单边删除，不影响对方）
    sender_deleted = db.Column(db.Boolean, nullable=False, default=False, comment='发送方已删除')
    receiver_deleted = db.Column(db.Boolean, nullable=False, default=False, comment='接收方已删除')

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

    def media_list(self):
        import json

        try:
            data = json.loads(self.media) if self.media else []
            return data if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['media'] = self.media_list()
        data['sender'] = self.sender.to_brief() if self.sender else None
        data['receiver'] = self.receiver.to_brief() if self.receiver else None
        return data

    @staticmethod
    def make_conversation_key(user_a, user_b):
        """生成会话键：两个用户 ID 排序后拼接，保证双方算出的键一致。"""
        low, high = sorted([int(user_a), int(user_b)])
        return f'{low}_{high}'


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
