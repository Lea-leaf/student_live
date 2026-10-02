# -*- coding: utf-8 -*-
"""用户模型。"""

from datetime import datetime

from ..extensions import db
from ..utils.constants import (
    ADMIN_ROLES,
    DEFAULT_MODULE_CODE,
    ROLE_LABELS,
    ROLE_USER,
    STATUS_ACTIVE,
    STATUS_BANNED,
    USER_STATUS_LABELS,
)
from .base import BaseModel


class User(BaseModel):
    """学生 / 管理员账号。

    说明：
    - 登录账号为学号 `student_id`（需求：学号 + 验证码注册）；
      `username` 保留为可选的昵称式账号，便于后续扩展邮箱/手机号登录。
    - `role` 当前仅使用 user / admin 两值，但已经按 RBAC 预留了常量集合，
      未来分级只需扩展 `utils/constants.py` 中的 ADMIN_ROLES。
    """

    __tablename__ = 'users'

    username = db.Column(db.String(64), unique=True, nullable=False, index=True, comment='登录名（默认=学号）')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    role = db.Column(db.String(32), nullable=False, default=ROLE_USER, index=True, comment='角色')
    status = db.Column(db.String(16), nullable=False, default=STATUS_ACTIVE, index=True, comment='账号状态')
    student_id = db.Column(db.String(32), unique=True, nullable=False, index=True, comment='学号')
    nickname = db.Column(db.String(64), nullable=True, comment='昵称')
    avatar = db.Column(db.String(255), nullable=True, comment='头像地址')
    email = db.Column(db.String(128), nullable=True, comment='邮箱（预留）')
    phone = db.Column(db.String(32), nullable=True, comment='手机号（预留）')
    ban_reason = db.Column(db.String(255), nullable=True, comment='封禁原因')
    banned_at = db.Column(db.DateTime, nullable=True, comment='封禁时间')
    banned_by = db.Column(db.Integer, nullable=True, comment='封禁操作人ID')
    last_login_at = db.Column(db.DateTime, nullable=True, comment='最后登录时间')
    last_login_ip = db.Column(db.String(64), nullable=True, comment='最后登录IP')
    login_count = db.Column(db.Integer, nullable=False, default=0, comment='累计登录次数')
    post_count = db.Column(db.Integer, nullable=False, default=0, comment='发帖计数（冗余，便于统计）')
    remark = db.Column(db.String(255), nullable=True, comment='管理员备注')

    # 关联：帖子 / 评论 / 通知 / 收藏
    posts = db.relationship('Post', backref='author', lazy='dynamic', foreign_keys='Post.user_id')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')

    # ------------------------------------------------------------------
    # 密码
    # ------------------------------------------------------------------
    def set_password(self, raw_password):
        """设置密码（Werkzeug scrypt 哈希，自带随机盐）。"""
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """校验明文密码。"""
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, raw_password)

    # ------------------------------------------------------------------
    # 权限
    # ------------------------------------------------------------------
    @property
    def is_admin(self):
        """是否具备后台访问权限（管理员分级后依然成立）。"""
        return self.role in ADMIN_ROLES

    @property
    def is_super_admin(self):
        from ..utils.constants import ROLE_ADMIN, ROLE_SUPER_ADMIN

        # 原型阶段 admin 即最高权限，后续分级后 super_admin 独立
        return self.role in (ROLE_SUPER_ADMIN, ROLE_ADMIN)

    @property
    def is_banned(self):
        return self.status == STATUS_BANNED

    def is_owner_of(self, obj):
        """是否为某资源的属主。"""
        return getattr(obj, 'user_id', None) == self.id

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------
    def ban(self, reason=None, operator_id=None):
        """封禁账号。"""
        self.status = STATUS_BANNED
        self.ban_reason = reason
        self.banned_at = datetime.now()
        self.banned_by = operator_id

    def unban(self):
        """解封账号。"""
        self.status = STATUS_ACTIVE
        self.ban_reason = None
        self.banned_at = None
        self.banned_by = None

    def mark_login(self, ip=None):
        """记录一次成功登录。"""
        self.last_login_at = datetime.now()
        self.last_login_ip = ip
        self.login_count = (self.login_count or 0) + 1

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def to_dict(self, exclude=None, extra=None, with_sensitive=False):
        """默认剔除密码哈希；管理员接口通过 with_sensitive 决定是否带敏感字段。"""
        exclude = set(exclude or ())
        exclude.add('password_hash')
        data = super().to_dict(exclude=exclude, extra=extra)
        data['role_label'] = ROLE_LABELS.get(self.role, self.role)
        data['status_label'] = USER_STATUS_LABELS.get(self.status, self.status)
        data['is_admin'] = self.is_admin
        data['display_name'] = self.nickname or self.username or self.student_id
        if with_sensitive:
            data['email'] = self.email
            data['phone'] = self.phone
        return data

    def to_brief(self):
        """帖子/评论中展示的用户摘要（不含任何敏感信息）。"""
        return {
            'id': self.id,
            'student_id': self.student_id,
            'nickname': self.nickname,
            'username': self.username,
            'avatar': self.avatar,
            'display_name': self.nickname or self.username or self.student_id,
        }

    def __repr__(self):
        return f'<User {self.student_id} role={self.role} status={self.status}>'


__all__ = ['User', 'DEFAULT_MODULE_CODE', 'STATUS_ACTIVE', 'STATUS_BANNED']
