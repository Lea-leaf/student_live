# -*- coding: utf-8 -*-
"""功能模块表。

需求要求「模块可后台启停 / 排序 / 配置」，因此模块不写死在代码里，
而是以数据行形式存在：代码中只内置 P0 失物招领的默认配置，其余模块
（二手交易、拼单、跑腿……）都可以由管理员在后台新增。
"""

from ..extensions import db
from ..utils.constants import MODULE_DAILY, MODULE_LOST_FOUND
from .base import BaseModel


class Module(BaseModel):
    """功能模块定义。"""

    __tablename__ = 'modules'

    code = db.Column(db.String(64), unique=True, nullable=False, index=True, comment='模块标识（=posts.type）')
    name = db.Column(db.String(64), nullable=False, comment='模块名称')
    icon = db.Column(db.String(64), nullable=True, comment='图标名（前端 Element Plus 图标）')
    description = db.Column(db.String(255), nullable=True, comment='模块简介')
    sort_order = db.Column(db.Integer, nullable=False, default=0, comment='排序，越小越靠前')
    enabled = db.Column(db.Boolean, nullable=False, default=True, comment='是否启用')
    is_system = db.Column(db.Boolean, nullable=False, default=False, comment='系统内置模块不允许删除')
    #: 模块级配置（JSON 字符串），例如是否强制审核、字段开关，便于按模块差异化扩展
    config = db.Column(db.Text, nullable=True, comment='模块配置(JSON)')
    #: 允许发布的角色，逗号分隔，默认所有登录用户（预留：某些模块仅管理员可发布）
    allow_roles = db.Column(db.String(255), nullable=True, comment='允许发布的角色，逗号分隔')

    posts = db.relationship('Post', backref='module_ref', lazy='dynamic', foreign_keys='Post.type',
                            primaryjoin='Module.code == foreign(Post.type)')

    def to_dict(self, exclude=None, extra=None):
        import json

        data = super().to_dict(exclude=exclude, extra=extra)
        try:
            data['config'] = json.loads(self.config) if self.config else {}
        except (TypeError, ValueError):
            data['config'] = {}
        return data

    def __repr__(self):
        return f'<Module {self.code} enabled={self.enabled}>'


def default_modules():
    """内置模块种子数据（P0 失物招领 + 后续模块占位）。"""
    return [
        {
            'code': MODULE_LOST_FOUND,
            'name': '失物招领',
            'icon': 'Search',
            'description': '丢失物品登记与招领信息发布',
            'sort_order': 10,
            'enabled': True,
            'is_system': True,
        },
        {
            'code': 'second_hand',
            'name': '二手交易',
            'icon': 'ShoppingCart',
            'description': '闲置物品买卖（v1.3 已实现，ext_json 承载价格/成色/交易方式）',
            'sort_order': 20,
            'enabled': True,
            'is_system': False,
        },
        {
            'code': 'group_buy',
            'name': '拼单',
            'icon': 'ShoppingBag',
            'description': '拼单凑单：目标人数 / 当前人数 / 开始日期（v1.5 已实现）',
            'sort_order': 30,
            'enabled': False,
            'is_system': False,
        },
        {
            'code': 'errand',
            'name': '跑腿',
            'icon': 'Bicycle',
            'description': '代取快递 / 代买：期望时间 + 联系方式（v1.5 已实现）',
            'sort_order': 40,
            'enabled': False,
            'is_system': False,
        },
        {
            'code': MODULE_DAILY,
            'name': '日常',
            'icon': 'ChatDotRound',
            'description': '校园日常分享与闲聊（v1.5 已实现）',
            'sort_order': 45,
            'enabled': False,
            'is_system': False,
        },
    ]
