# -*- coding: utf-8 -*-
"""日志、系统配置、上传记录、管理员-模块授权。

`operation_logs` / `login_logs` 为只追加表，管理端只读。
`system_configs` 承载需求里「不要写死、留配置项」的要求。
"""

import json

from ..extensions import db
from ..utils.constants import LOG_TYPE_OPERATION
from .base import BaseModel


class OperationLog(BaseModel):
    """操作日志：谁在什么时间对什么对象做了什么。"""

    __tablename__ = 'operation_logs'

    user_id = db.Column(db.Integer, nullable=True, index=True, comment='操作人ID（未登录为NULL）')
    username = db.Column(db.String(64), nullable=True, comment='操作人账号快照')
    log_type = db.Column(db.String(16), nullable=False, default=LOG_TYPE_OPERATION, index=True, comment='日志类型')
    module = db.Column(db.String(64), nullable=True, index=True, comment='所属模块')
    action = db.Column(db.String(64), nullable=False, comment='动作，例如 create / audit / ban')
    target_type = db.Column(db.String(32), nullable=True, comment='目标类型')
    target_id = db.Column(db.Integer, nullable=True, comment='目标ID')
    detail = db.Column(db.Text, nullable=True, comment='详情(JSON 或文本)')
    ip = db.Column(db.String(64), nullable=True, comment='来源IP')
    user_agent = db.Column(db.String(255), nullable=True, comment='UA')
    duration_ms = db.Column(db.Integer, nullable=True, comment='耗时(毫秒)')

    def to_dict(self, exclude=None, extra=None):
        data = super().to_dict(exclude=exclude, extra=extra)
        try:
            data['detail'] = json.loads(self.detail) if self.detail else None
        except (TypeError, ValueError):
            pass
        return data


class LoginLog(BaseModel):
    """登录日志：成功与失败都记录，便于排查和统计。"""

    __tablename__ = 'login_logs'

    user_id = db.Column(db.Integer, nullable=True, index=True, comment='用户ID（失败时可能为NULL）')
    student_id = db.Column(db.String(32), nullable=True, index=True, comment='尝试登录的学号')
    success = db.Column(db.Boolean, nullable=False, default=True, index=True, comment='是否成功')
    message = db.Column(db.String(255), nullable=True, comment='结果说明')
    ip = db.Column(db.String(64), nullable=True, comment='来源IP')
    user_agent = db.Column(db.String(255), nullable=True, comment='UA')


class SystemConfig(BaseModel):
    """系统配置键值对（管理员可改，未配置时回落到 constants.DEFAULT_CONFIGS）。"""

    __tablename__ = 'system_configs'

    key = db.Column(db.String(64), unique=True, nullable=False, index=True, comment='配置键')
    value = db.Column(db.Text, nullable=True, comment='配置值')
    value_type = db.Column(db.String(16), nullable=False, default='str', comment='值类型：str/int/bool/json')
    group = db.Column(db.String(32), nullable=False, default='common', index=True, comment='分组')
    title = db.Column(db.String(64), nullable=True, comment='配置项名称')
    description = db.Column(db.String(255), nullable=True, comment='说明')

    def typed_value(self):
        """按声明类型返回值。"""
        raw = self.value
        if raw is None:
            return None
        if self.value_type == 'int':
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        if self.value_type == 'bool':
            return str(raw).lower() in ('1', 'true', 'yes', 'on')
        if self.value_type == 'json':
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None
        return raw


class UploadFile(BaseModel):
    """上传文件记录（图片/视频）。"""

    __tablename__ = 'upload_files'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True, comment='上传者')
    filename = db.Column(db.String(255), nullable=False, comment='存储文件名')
    original_name = db.Column(db.String(255), nullable=True, comment='原始文件名')
    path = db.Column(db.String(255), nullable=False, comment='相对路径')
    url = db.Column(db.String(255), nullable=False, comment='访问地址')
    mime = db.Column(db.String(64), nullable=True, comment='MIME 类型')
    media_type = db.Column(db.String(16), nullable=False, default='image', comment='image / video')
    size = db.Column(db.Integer, nullable=False, default=0, comment='字节数')
    #: 可挂载到帖子；未挂载的视为临时文件，可由定时任务清理（预留）
    post_id = db.Column(db.Integer, nullable=True, index=True, comment='关联帖子ID')


class AdminModuleAccess(BaseModel):
    """管理员 ↔ 模块 授权表（RBAC 预留）。

    原型阶段 role=admin 即全模块可见，此表用于未来「版主只管某个模块」。
    """

    __tablename__ = 'admin_module_access'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True, comment='管理员')
    module_code = db.Column(db.String(64), nullable=False, index=True, comment='模块标识')
    permission = db.Column(db.String(32), nullable=False, default='manage', comment='权限：manage/audit/read')

    admin = db.relationship('User', backref='module_access')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'module_code', name='uq_admin_module'),
    )


__all__ = ['OperationLog', 'LoginLog', 'SystemConfig', 'UploadFile', 'AdminModuleAccess']
