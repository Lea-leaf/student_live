# -*- coding: utf-8 -*-
"""管理端 - 日志管理。

需求：登录日志、操作日志、异常日志（可选）。
异常日志直接读 app/logs/error.log 尾部，避免再建一张表。
"""

import os

from flask import Blueprint, current_app, request

from ..extensions import db
from ..models import LoginLog, OperationLog
from ..models.base import paginate
from ..utils.auth import admin_required
from ..utils.constants import CAP_LOG_VIEW
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.response import success
from ..utils.validators import ValidationError, as_error, get_int

bp = Blueprint('admin_logs', __name__, url_prefix='/logs')


@bp.get('/operations')
@admin_required(capability=CAP_LOG_VIEW)
def operation_logs():
    """操作日志。

    查询参数：page / size / keyword / module / action / log_type / target_type
    """
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        module = (request.args.get('module') or '').strip()
        action = (request.args.get('action') or '').strip()
        log_type = (request.args.get('log_type') or '').strip()
        target_type = (request.args.get('target_type') or '').strip()

        query = OperationLog.query
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(
                OperationLog.username.like(like),
                OperationLog.action.like(like),
                OperationLog.detail.like(like),
            ))
        if module:
            query = query.filter(OperationLog.module == module)
        if action:
            query = query.filter(OperationLog.action == action)
        if log_type:
            query = query.filter(OperationLog.log_type == log_type)
        if target_type:
            query = query.filter(OperationLog.target_type == target_type)

        query = query.order_by(OperationLog.id.desc())
        items, total, page, size = paginate(query, page, size)
        return success({
            'list': [item.to_dict() for item in items],
            'total': total,
            'page': page,
            'size': size,
            'pages': (total + size - 1) // size if size else 0,
        })
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/logins')
@admin_required(capability=CAP_LOG_VIEW)
def login_logs():
    """登录日志（成功与失败）。参数：success（0/1）、keyword。"""
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        success_flag = request.args.get('success')

        query = LoginLog.query
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(
                LoginLog.student_id.like(like),
                LoginLog.ip.like(like),
                LoginLog.message.like(like),
            ))
        if success_flag in ('0', '1'):
            query = query.filter(LoginLog.success.is_(success_flag == '1'))
        query = query.order_by(LoginLog.id.desc())
        items, total, page, size = paginate(query, page, size)
        return success({
            'list': [item.to_dict() for item in items],
            'total': total,
            'page': page,
            'size': size,
            'pages': (total + size - 1) // size if size else 0,
        })
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/errors')
@admin_required(capability=CAP_LOG_VIEW)
def error_logs():
    """异常日志（读取 app/logs/error.log 尾部）。

    参数：lines（默认 200，最大 1000）
    """
    try:
        lines = get_int('lines', 200, minimum=1, maximum=1000, source='args')
        root = current_app.config.get('LOG_DIR')
        path = os.path.join(root, 'error.log')
        if not os.path.exists(path):
            return success({'path': path, 'lines': [], 'exists': False})
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            content = handle.readlines()
        return success({'path': path, 'exists': True, 'lines': [row.rstrip('\n') for row in content[-lines:]]})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/summary')
@admin_required(capability=CAP_LOG_VIEW)
def logs_summary():
    """日志概览：各类日志总量与今日量。"""
    from datetime import datetime

    from ..utils.constants import LOG_TYPE_ERROR, LOG_TYPE_LOGIN, LOG_TYPE_OPERATION

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return success({
        'operation_total': OperationLog.query.count(),
        'operation_today': OperationLog.query.filter(OperationLog.created_at >= today).count(),
        'login_total': LoginLog.query.count(),
        'login_today': LoginLog.query.filter(LoginLog.created_at >= today).count(),
        'login_failed_today': LoginLog.query.filter(
            LoginLog.created_at >= today, LoginLog.success.is_(False)
        ).count(),
        'types': [LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, LOG_TYPE_ERROR],
    })


__all__ = ['bp']
