# -*- coding: utf-8 -*-
"""系统配置服务。

读取顺序：`system_configs` 表 → 环境变量/Config → `constants.DEFAULT_CONFIGS`。
带进程内缓存（默认 30 秒），管理员改配置后立即失效，避免每次请求都查库。
"""

import json
import threading
import time

from flask import current_app

from .constants import DEFAULT_CONFIGS

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 30  # 秒


def clear_cache():
    """清空配置缓存（改配置 / 测试时调用）。"""
    with _CACHE_LOCK:
        _CACHE.clear()


def _db_overrides():
    """一次性取回表内所有配置，放进缓存。"""
    from ..extensions import db
    from ..models import SystemConfig

    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get('__all__')
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
    data = {}
    try:
        for row in SystemConfig.query.all():
            data[row.key] = row.typed_value()
    except Exception:  # noqa: BLE001 - 表尚未创建时回落到默认值
        db.session.rollback()
        data = {}
    with _CACHE_LOCK:
        _CACHE['__all__'] = (now, data)
    return data


def get_config(key, default=None):
    """取配置（字符串）。"""
    overrides = _db_overrides()
    if key in overrides and overrides[key] is not None:
        return overrides[key]
    if default is not None:
        return default
    if key in DEFAULT_CONFIGS:
        return DEFAULT_CONFIGS[key]
    # 最后尝试 Flask 配置（大写形式）
    try:
        return current_app.config.get(key.upper(), default)
    except RuntimeError:
        return default


def get_config_int(key, default=0):
    value = get_config(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_config_bool(key, default=False):
    value = get_config(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def get_config_json(key, default=None):
    value = get_config(key, None)
    if value is None:
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else {}


def get_group(group=None):
    """取配置分组（管理端配置页面用）。"""
    from ..models import SystemConfig

    query = SystemConfig.query
    if group:
        query = query.filter_by(group=group)
    return [row.to_dict() | {'value': row.typed_value()} for row in query.order_by(SystemConfig.group, SystemConfig.key).all()]


def set_config(key, value, value_type=None, group=None, title=None, description=None, commit=True):
    """新增或更新配置项。"""
    from ..extensions import db
    from ..models import SystemConfig

    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
        value_type = value_type or 'json'
    elif isinstance(value, bool):
        value = '1' if value else '0'
        value_type = value_type or 'bool'
    elif isinstance(value, int):
        value = str(value)
        value_type = value_type or 'int'

    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        row = SystemConfig(key=key, value_type=value_type or 'str')
        db.session.add(row)
    row.value = None if value is None else str(value)
    if value_type:
        row.value_type = value_type
    if group:
        row.group = group
    if title:
        row.title = title
    if description:
        row.description = description
    if commit:
        db.session.commit()
    clear_cache()
    return row


def set_configs(items, commit=True):
    """批量更新：items 为 [{key, value}] 或 {key: value}。"""
    from ..extensions import db

    if isinstance(items, dict):
        items = [{'key': k, 'value': v} for k, v in items.items()]
    rows = [set_config(item['key'], item.get('value'), commit=False) for item in items if item.get('key')]
    if commit:
        db.session.commit()
    clear_cache()
    return rows


def init_default_configs():
    """把 DEFAULT_CONFIGS 中缺失的键写入表（幂等，不覆盖已有值）。"""
    from ..extensions import db
    from ..models import SystemConfig

    meta = _CONFIG_META()
    created = 0
    for key, value in DEFAULT_CONFIGS.items():
        if SystemConfig.query.filter_by(key=key).first():
            continue
        info = meta.get(key, {})
        value_type = 'str'
        if key.startswith(('upload_max_mb', 'page_')) or key == 'recycle_retention_count':
            value_type = 'int'
        elif key.endswith('_enabled') or key.startswith('guest_can'):
            value_type = 'bool'
        db.session.add(SystemConfig(
            key=key,
            value=str(value),
            value_type=info.get('value_type', value_type),
            group=info.get('group', 'common'),
            title=info.get('title', key),
            description=info.get('description'),
        ))
        created += 1
    if created:
        db.session.commit()
    clear_cache()
    return created


def _CONFIG_META():
    """配置项的中文名称与分组，仅用于后台展示。"""
    return {
        'site_name': {'group': 'common', 'title': '站点名称'},
        'site_notice': {'group': 'common', 'title': '站点公告'},
        'api_prefix': {'group': 'common', 'title': '接口前缀'},
        'security_notice_enabled': {'group': 'security', 'title': '启用安全公告', 'value_type': 'bool'},
        'security_notice_text': {'group': 'security', 'title': '安全公告内容'},
        'post_audit_enabled': {'group': 'audit', 'title': '发帖需审核', 'value_type': 'bool'},
        'register_captcha_enabled': {'group': 'audit', 'title': '注册需验证码', 'value_type': 'bool'},
        'recycle_retention_count': {'group': 'recycle', 'title': '回收站保留条数', 'value_type': 'int'},
        'recycle_retention_mode': {'group': 'recycle', 'title': '超量处理方式'},
        'upload_allowed_ext': {'group': 'upload', 'title': '允许的文件后缀'},
        'upload_max_mb_image': {'group': 'upload', 'title': '图片大小上限(MB)', 'value_type': 'int'},
        'upload_max_mb_video': {'group': 'upload', 'title': '视频大小上限(MB)', 'value_type': 'int'},
        'upload_max_mb_audio': {'group': 'upload', 'title': '语音大小上限(MB)', 'value_type': 'int'},
        'page_default_size': {'group': 'common', 'title': '默认分页条数', 'value_type': 'int'},
        'page_max_size': {'group': 'common', 'title': '最大分页条数', 'value_type': 'int'},
        'guest_can_list': {'group': 'guest', 'title': '游客可浏览列表', 'value_type': 'bool'},
        'guest_can_detail': {'group': 'guest', 'title': '游客可查看详情', 'value_type': 'bool'},
    }


__all__ = [
    'get_config', 'get_config_int', 'get_config_bool', 'get_config_json',
    'get_group', 'set_config', 'set_configs', 'init_default_configs', 'clear_cache',
]
