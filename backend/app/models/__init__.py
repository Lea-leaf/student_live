# -*- coding: utf-8 -*-
"""模型包：集中导出，便于 `from app.models import User, Post`。"""

from .base import BaseModel, paginate
from .interaction import Comment, Favorite, Message, Notification, Report
from .like import CommentLike, PostLike
from .module import Module, default_modules
from .post import Post
from .system import AdminModuleAccess, LoginLog, OperationLog, SystemConfig, UploadFile
from .user import User

__all__ = [
    'BaseModel',
    'paginate',
    'User',
    'Post',
    'Module',
    'default_modules',
    'Comment',
    'Message',
    'Favorite',
    'Report',
    'Notification',
    'PostLike',
    'CommentLike',
    'OperationLog',
    'LoginLog',
    'SystemConfig',
    'UploadFile',
    'AdminModuleAccess',
]
