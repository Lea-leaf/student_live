# -*- coding: utf-8 -*-
"""模型基类与公共工具。

设计要点：
1. 统一主键、创建/更新时间字段，避免每张表重复定义；
2. 提供 `to_dict()` 通用序列化，子类按需覆写；
3. 提供分页查询助手，让所有列表接口共用同一套分页语义。
"""

from datetime import datetime

from ..extensions import db


class BaseModel(db.Model):
    """所有业务表的抽象基类。"""

    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='主键')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间'
    )

    def to_dict(self, exclude=None, extra=None):
        """把模型实例转成字典。

        :param exclude: 需要排除的字段名集合（例如 password_hash）
        :param extra: 需要附加的键值对（例如关联对象摘要）
        """
        exclude = set(exclude or ())
        data = {}
        for column in self.__table__.columns:
            if column.name in exclude:
                continue
            data[column.name] = _serialize(getattr(self, column.name))
        if extra:
            data.update(extra)
        return data

    def save(self, commit=True):
        """写入会话。"""
        db.session.add(self)
        if commit:
            db.session.commit()
        return self

    def delete(self, commit=True):
        """物理删除。软删除请使用各模型的专用方法。"""
        db.session.delete(self)
        if commit:
            db.session.commit()


def _serialize(value):
    """把 datetime / date 转成前端友好的字符串。"""
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def paginate(query, page=1, size=10, max_size=100):
    """统一分页助手。

    :param query: SQLAlchemy Query 对象
    :param page: 页码，从 1 开始
    :param size: 每页条数，超过 max_size 会被截断，防止恶意大分页
    :return: (items, total, page, size)
    """
    page = max(int(page or 1), 1)
    size = int(size or 10)
    size = max(1, min(size, max_size))
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    return pagination.items, pagination.total, page, size
