# -*- coding: utf-8 -*-
"""公共接口：枚举字典、模块列表、文件上传/访问。

这些接口不隶属于任何业务模块，但被所有模块共用。
"""

from flask import Blueprint, request

from ...utils.auth import token_required
from ...utils.config_service import get_config, get_config_bool
from ...utils.constants import (
    AUDIT_STATUS_LABELS,
    MODULE_LOST_FOUND,
    POST_STATUS_LABELS,
    REPORT_STATUS_LABELS,
    ROLE_LABELS,
    USER_STATUS_LABELS,
)
from ...utils.response import error, success

bp = Blueprint('common', __name__, url_prefix='/common')


@bp.get('/enums')
def enums():
    """一次性返回所有字典，前端启动时拉一次即可。"""
    return success({
        'post_status': _pairs(POST_STATUS_LABELS),
        'audit_status': _pairs(AUDIT_STATUS_LABELS),
        'report_status': _pairs(REPORT_STATUS_LABELS),
        'user_status': _pairs(USER_STATUS_LABELS),
        'role': _pairs(ROLE_LABELS),
    })


@bp.get('/modules')
def modules():
    """启用中的模块列表（前端导航 / 筛选器使用）。"""
    from ...models import Module

    rows = Module.query.filter_by(enabled=True).order_by(Module.sort_order.asc(), Module.id.asc()).all()
    data = [{'code': row.code, 'name': row.name, 'icon': row.icon,
             'description': row.description, 'sort_order': row.sort_order} for row in rows]
    return success({'list': data, 'default': data[0]['code'] if data else MODULE_LOST_FOUND})


@bp.get('/configs')
def public_configs():
    """公开配置（前端渲染站点名、公告、上传限制等）。"""
    return success({
        'site_name': get_config('site_name', '校园生活平台'),
        'site_notice': get_config('site_notice', ''),
        'security_notice_enabled': get_config_bool('security_notice_enabled', True),
        'security_notice_text': get_config('security_notice_text', ''),
        'post_audit_enabled': get_config_bool('post_audit_enabled', True),
        'register_captcha_enabled': get_config_bool('register_captcha_enabled', True),
        'guest_can_list': get_config_bool('guest_can_list', True),
        'guest_can_detail': get_config_bool('guest_can_detail', False),
        'upload_max_mb_image': get_config('upload_max_mb_image', '10'),
        'upload_max_mb_video': get_config('upload_max_mb_video', '50'),
    })


@bp.get('/health')
def health():
    """健康检查（部署探活用）。"""
    from ...extensions import db

    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return success({'status': 'ok' if db_ok else 'degraded', 'database': db_ok})


@bp.post('/upload')
@token_required
def upload():
    """通用上传接口（不绑定模块）。

    表单字段：files（可多文件）
    返回：{"media": [{id,url,type,name,size}]}
    """
    from ...utils.auth import current_user
    from ...utils.uploads import save_media_list

    files = request.files.getlist('files') or request.files.getlist('file')
    if not files:
        return error('请选择要上传的文件', 6003)
    media, errors = save_media_list(files, user_id=current_user().id)
    if errors and not media:
        return error('；'.join(errors), 6001)
    return success({'media': media, 'errors': errors}, msg='上传成功')


__all__ = ['bp']


def _pairs(label_map):
    return [{'value': key, 'label': label} for key, label in label_map.items()]
