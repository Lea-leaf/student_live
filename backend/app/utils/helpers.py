# -*- coding: utf-8 -*-
"""通用辅助函数：分页参数、权限开关、查询条件拼装。"""

from flask import request

from .config_service import get_config_bool, get_config_int
from .constants import ADMIN_ROLES


def current_page_args():
    """统一解析分页参数，带上限保护。"""
    from .validators import ValidationError

    max_size = get_config_int('page_max_size', 100)
    default_size = get_config_int('page_default_size', 10)
    try:
        page = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        raise ValidationError('page 必须是整数') from None
    try:
        size = int(request.args.get('size', default_size))
    except (TypeError, ValueError):
        raise ValidationError('size 必须是整数') from None
    return max(page, 1), max(1, min(size, max_size))


def keyword_arg():
    """取搜索关键字（用于标题/描述模糊搜索）。"""
    return (request.args.get('keyword') or '').strip()[:64]


def guest_can_list():
    return get_config_bool('guest_can_list', True)


def guest_can_detail():
    return get_config_bool('guest_can_detail', False)


def post_audit_enabled():
    """发帖是否需要审核（管理员发帖默认直通）。"""
    return get_config_bool('post_audit_enabled', True)


def is_admin_role(role):
    return role in ADMIN_ROLES


def want_json_error():
    return True


__all__ = [
    'current_page_args',
    'keyword_arg',
    'guest_can_list',
    'guest_can_detail',
    'post_audit_enabled',
    'is_admin_role',
]
