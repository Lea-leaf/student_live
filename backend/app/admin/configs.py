# -*- coding: utf-8 -*-
"""管理端 - 系统配置。

需求：「不要一次性写死，留好配置项」。
这里的键值对会覆盖 `utils/constants.py::DEFAULT_CONFIGS` 中的默认值，
包括审核开关、注册验证码开关、回收站保留条数、上传限制、游客权限等。
"""

from flask import Blueprint

from ..utils.auth import admin_required, current_user
from ..utils.config_service import clear_cache, get_group, init_default_configs, set_configs
from ..utils.constants import CAP_CONFIG_MANAGE, DEFAULT_CONFIGS
from ..utils.logger import write_operation_log
from ..utils.response import success
from ..utils.validators import ValidationError, as_error, get_json

bp = Blueprint('admin_configs', __name__, url_prefix='/configs')


@bp.get('')
@admin_required(capability=CAP_CONFIG_MANAGE)
def list_configs():
    """配置列表（按分组）。参数：group。"""
    rows = get_group()
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get('group') or 'common', []).append(row)
    return success({'list': rows, 'grouped': grouped, 'total': len(rows)})


@bp.put('')
@admin_required(capability=CAP_CONFIG_MANAGE)
def update_configs():
    """批量修改配置。

    请求体：
        {"items": [{"key": "post_audit_enabled", "value": "0"}, ...]}
        或直接 {"post_audit_enabled": "0"}
    """
    try:
        payload = get_json()
        items = payload.get('items')
        if not items:
            # 允许直接把键值对放在顶层
            items = [{'key': key, 'value': value} for key, value in payload.items() if key != 'items']
        if not items:
            raise ValidationError('没有需要修改的配置项')

        unknown = [item['key'] for item in items if item.get('key') not in DEFAULT_CONFIGS]
        if unknown:
            raise ValidationError(f'不支持的配置项：{" / ".join(unknown)}')

        set_configs(items)
        write_operation_log('update_configs', module='configs', detail={'keys': [i['key'] for i in items]})
        return success({'updated': len(items)}, msg='配置已保存')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/reset')
@admin_required(capability=CAP_CONFIG_MANAGE)
def reset_configs():
    """恢复默认：把 DEFAULT_CONFIGS 重新写入（已有值会被覆盖）。"""
    try:
        payload = get_json(required=False)
        keys = payload.get('keys')
        targets = keys or list(DEFAULT_CONFIGS.keys())
        items = [{'key': key, 'value': DEFAULT_CONFIGS[key]} for key in targets if key in DEFAULT_CONFIGS]
        set_configs(items)
        write_operation_log('reset_configs', module='configs', detail={'keys': targets})
        return success({'reset': len(items)}, msg='已恢复默认配置')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/init')
@admin_required(capability=CAP_CONFIG_MANAGE)
def init_configs():
    """补齐缺失的配置项（部署后第一次调用）。"""
    created = init_default_configs()
    clear_cache()
    return success({'created': created}, msg=f'已补齐 {created} 项配置')


__all__ = ['bp']
