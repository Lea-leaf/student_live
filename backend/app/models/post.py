# -*- coding: utf-8 -*-
"""统一帖子模型。

需求明确「帖子统一存储，用 type 字段区分模块」，因此失物招领、二手交易、
拼单、跑腿共用 `posts` 一张表，由 `type` 指向 `modules.code`。
模块特有的字段差异放在 `ext_json` 里，避免后期每加一个模块就改表结构。
"""

import json

from ..extensions import db
from ..utils.constants import (
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_STATUS_LABELS,
    AUDIT_STATUSES,
    MODULE_LOST_FOUND,
    MODULE_STATUS_LABELS,
    POST_DETAIL_VISIBLE_STATUSES,
    POST_LIST_VISIBLE_STATUSES,
    POST_ONGOING,
    POST_STATUS_LABELS,
    POST_STATUSES,
)
from .base import BaseModel


class Post(BaseModel):
    """帖子（跨模块统一表）。"""

    __tablename__ = 'posts'

    # ---- 归属与分类 ----
    type = db.Column(db.String(64), nullable=False, default=MODULE_LOST_FOUND,
                     index=True, comment='模块标识，对应 modules.code')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='发布者')

    # ---- 内容 ----
    title = db.Column(db.String(128), nullable=True, comment='标题（选填）')
    content = db.Column(db.Text, nullable=True, comment='描述（选填）')
    media = db.Column(db.Text, nullable=True, comment='图片/视频(JSON数组)')
    location = db.Column(db.String(128), nullable=True, comment='地点（选填）')
    happened_at = db.Column(db.DateTime, nullable=True, comment='发生时间（选填）')
    contact = db.Column(db.String(128), nullable=False, comment='联系方式（必填，公开可见）')

    # ---- 状态 ----
    status = db.Column(db.String(16), nullable=False, default=POST_ONGOING, index=True, comment='业务状态')
    audit_status = db.Column(db.String(16), nullable=False, default=AUDIT_PENDING, index=True, comment='审核状态')
    audit_remark = db.Column(db.String(255), nullable=True, comment='审核意见')
    audited_by = db.Column(db.Integer, nullable=True, comment='审核人')
    audited_at = db.Column(db.DateTime, nullable=True, comment='审核时间')

    # ---- 运营 ----
    is_top = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='是否置顶')
    view_count = db.Column(db.Integer, nullable=False, default=0, comment='浏览量')
    comment_count = db.Column(db.Integer, nullable=False, default=0, comment='评论数（含楼中楼回复）')
    favorite_count = db.Column(db.Integer, nullable=False, default=0, comment='收藏数')
    #: 点赞与收藏是独立功能，各自计数互不影响
    like_count = db.Column(db.Integer, nullable=False, default=0, comment='点赞数')

    # ---- 软删除（回收站） ----
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True, comment='是否已删除(软删除)')
    deleted_at = db.Column(db.DateTime, nullable=True, comment='删除时间')
    deleted_by = db.Column(db.Integer, nullable=True, comment='删除人')

    # ---- 扩展 ----
    #: 模块特有字段，例如二手交易的 price、拼单的 target_count
    ext_json = db.Column(db.Text, nullable=True, comment='模块扩展字段(JSON)')

    __table_args__ = (
        db.Index('ix_posts_type_status_deleted', 'type', 'status', 'is_deleted'),
        db.Index('ix_posts_audit_created', 'audit_status', 'created_at'),
    )

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def _media_list(self):
        try:
            return json.loads(self.media) if self.media else []
        except (TypeError, ValueError):
            return []

    def _ext_dict(self):
        try:
            return json.loads(self.ext_json) if self.ext_json else {}
        except (TypeError, ValueError):
            return {}

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['media'] = self._media_list()
        data['ext'] = self._ext_dict()
        data['status_label'] = MODULE_STATUS_LABELS.get(self.type, POST_STATUS_LABELS).get(
            self.status, self.status)
        data['audit_status_label'] = AUDIT_STATUS_LABELS.get(self.audit_status, self.audit_status)
        data['author'] = self.author.to_brief() if self.author else None
        data['happened_at'] = data.get('happened_at') or None
        return data

    def to_brief(self):
        """列表页精简字段，减少传输体积。

        注意：点赞数、收藏数、评论数都要带上 —— 列表卡片上会显示，
        漏掉的话前端拿到的是 undefined（曾漏过 like_count）。
        """
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'content': (self.content or '')[:80],
            'media': self._media_list()[:1],
            'location': self.location,
            'happened_at': self.happened_at.strftime('%Y-%m-%d %H:%M:%S') if self.happened_at else None,
            'status': self.status,
            'status_label': MODULE_STATUS_LABELS.get(self.type, POST_STATUS_LABELS).get(
                self.status, self.status),
            'audit_status': self.audit_status,
            'is_top': self.is_top,
            'view_count': self.view_count,
            'comment_count': self.comment_count,
            'favorite_count': self.favorite_count,
            'like_count': self.like_count,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'author': self.author.to_brief() if self.author else None,
            'module_name': self.module_ref.name if self.module_ref else self.type,
            # 列表卡片展示模块差异字段（例如二手交易价格）
            'ext': self._ext_dict(),
        }

    # ------------------------------------------------------------------
    # 状态判断
    # ------------------------------------------------------------------
    @property
    def is_public(self):
        """是否对普通用户公开（已通过审核 + 未删除）。"""
        return (not self.is_deleted) and self.audit_status == AUDIT_APPROVED

    @property
    def list_visible(self):
        """列表可见：已关闭的帖子不进公开列表。"""
        return self.is_public and self.status in POST_LIST_VISIBLE_STATUSES

    @property
    def detail_visible(self):
        """详情可点：仅进行中的帖子可查看详情。"""
        return self.is_public and self.status in POST_DETAIL_VISIBLE_STATUSES

    def soft_delete(self, operator_id=None):
        """软删除，进入回收站。"""
        from datetime import datetime

        self.is_deleted = True
        self.deleted_at = datetime.now()
        self.deleted_by = operator_id

    def restore(self):
        """从回收站恢复。"""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None

    def __repr__(self):
        return f'<Post {self.id} type={self.type} status={self.status} audit={self.audit_status}>'


__all__ = ['Post', 'AUDIT_STATUSES', 'POST_STATUSES']
