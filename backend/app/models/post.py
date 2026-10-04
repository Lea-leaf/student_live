# -*- coding: utf-8 -*-
"""统一帖子模型。

需求明确「帖子统一存储，用 type 字段区分模块」，因此失物招领、二手交易、
拼单、跑腿共用 `posts` 一张表，由 `type` 指向 `modules.code`。
模块特有的字段差异放在 `ext_json` 里，避免后期每加一个模块就改表结构。
"""

import json

from ..extensions import db
from ..utils.constants import (
    AUDIT_ACTION_LABELS,
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_STATUS_LABELS,
    AUDIT_STATUSES,
    CAP_POST_AUDIT,
    MODULE_LOST_FOUND,
    MODULE_DETAIL_VISIBLE_STATUSES,
    MODULE_LIST_VISIBLE_STATUSES,
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

    # ---- 审核指派（管理员指定审核员；审核员可自助认领） ----
    #: 当前负责审核的人。NULL = 在公共池（谁都能认领 / 管理员可指派）。
    #: 沿用 audited_by 的"裸整数"风格：审核员注销后历史记录仍可保留，不因外键被阻塞。
    assignee_id = db.Column(db.Integer, nullable=True, index=True, comment='当前指派/认领的审核员ID')
    #: 指派人：管理员手动指派时记录，审核员自助认领时等于审核员自己
    assigned_by = db.Column(db.Integer, nullable=True, comment='指派人ID')
    assigned_at = db.Column(db.DateTime, nullable=True, comment='指派/认领时间')
    #: 到期自动退回公共池；NULL = 不过期（管理员指派的默认不设期限，管理员可改派）
    assignment_expires_at = db.Column(db.DateTime, nullable=True, index=True,
                                      comment='认领到期时间（超时自动退回公共池）')

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
        db.Index('ix_posts_audit_assignee', 'audit_status', 'assignee_id'),
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
        """列表可见：默认沿用全局规则，拼单 / 跑腿 / 日常按模块覆盖。"""
        allowed = MODULE_LIST_VISIBLE_STATUSES.get(self.type, POST_LIST_VISIBLE_STATUSES)
        return self.is_public and self.status in allowed

    @property
    def detail_visible(self):
        """详情可点：默认仅进行中；拼单 / 跑腿 / 日常结束后仍可回看。"""
        allowed = MODULE_DETAIL_VISIBLE_STATUSES.get(self.type, POST_DETAIL_VISIBLE_STATUSES)
        return self.is_public and self.status in allowed

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

    # ------------------------------------------------------------------
    # 审核指派
    # ------------------------------------------------------------------
    @property
    def assignment_expired(self):
        """认领是否已到期（到期后应视为回到公共池）。"""
        if self.assignment_expires_at is None:
            return False
        from datetime import datetime

        return self.assignment_expires_at <= datetime.now()

    @property
    def pending_audit(self):
        """是否处于待审核状态。"""
        return (not self.is_deleted) and self.audit_status == AUDIT_PENDING

    @property
    def effective_assignee_id(self):
        """生效的审核人：已到期或已审完的指派视为无主（回公共池）。"""
        if not self.pending_audit or self.assignment_expired:
            return None
        return self.assignee_id

    def is_auditable_by(self, user):
        """该用户现在能不能审这条帖子。

        规则：
        - 未登录 / 无审核能力 → 否；
        - 帖子已删除或不是待审核 → 否（避免重复审核）；
        - **禁止自审**：不能审自己发的帖子（无论管理员还是审核员）；
        - 管理员：不受指派限制，随时可审；
        - 其他后台角色：只能审公共池或指派给自己的帖子。
        """
        if user is None or not self.pending_audit:
            return False
        if not user.has_capability(CAP_POST_AUDIT):
            return False
        if self.user_id == user.id:
            return False
        if user.is_admin:
            return True
        return self.effective_assignee_id in (None, user.id)

    def __repr__(self):
        return f'<Post {self.id} type={self.type} status={self.status} audit={self.audit_status}>'


class PostAuditLog(BaseModel):
    """审核指派与审核动作的**流水账**（只追加）。

    为什么需要它：`posts.assignee_id` 这类字段只保留**当前状态** ——
    认领超时退回公共池、被管理员改派之后，之前"谁认领过、谁审过"就丢了。
    这张表把每一次指派 / 认领 / 释放 / 审核决定都记下来，用于：

    - 审核台账与追责（出问题能定位到具体的人和时间）；
    - 审核员工作量统计（每人接了多少、审了多少、平均耗时）；
    - 答辩演示「多审核员协作 + 先到先得」的完整证据链。

    与 `operation_logs` 的分工：后者是**全平台通用**的操作日志，
    这里是**审核业务专用**的结构化流水（可 SQL 聚合统计）。
    """

    __tablename__ = 'post_audit_logs'

    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True, comment='帖子ID')
    #: 指派 / 认领 / 释放 / 通过 / 拒绝 / 改派
    action = db.Column(db.String(16), nullable=False, comment='assign/claim/release/approve/reject')
    #: 动作发起人（管理员指派时是管理员，自助认领时是审核员自己）
    actor_id = db.Column(db.Integer, nullable=True, index=True, comment='操作人ID')
    #: 被指派的审核员（区别于 actor：管理员可以指派给别人）
    assignee_id = db.Column(db.Integer, nullable=True, index=True, comment='被指派/认领的审核员ID')
    #: 归属类型：admin=管理员指派，self=审核员自助认领
    assign_source = db.Column(db.String(16), nullable=True, comment='admin/self')
    remark = db.Column(db.String(255), nullable=True, comment='备注（审核意见 / 改派说明）')
    #: 从指派到做出决定的耗时（毫秒），用于统计审核效率
    duration_ms = db.Column(db.Integer, nullable=True, comment='处理耗时(毫秒)')

    post = db.relationship('Post', backref=db.backref('audit_logs', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_post_audit_logs_post_action', 'post_id', 'action'),
    )

    def __repr__(self):
        return f'<PostAuditLog post={self.post_id} action={self.action} assignee={self.assignee_id}>'

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        data['action_label'] = AUDIT_ACTION_LABELS.get(self.action, self.action)
        return data


__all__ = ['Post', 'PostAuditLog', 'AUDIT_STATUSES', 'POST_STATUSES']
