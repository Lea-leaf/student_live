# -*- coding: utf-8 -*-
"""日志工具：滚动文件日志 + 数据库业务日志。

两类日志：
1. 文件日志（app/logs/*.log）：给开发和排障看，按大小滚动；
2. 业务日志（operation_logs / login_logs 表）：给管理后台看。
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import current_app, request

_configured = False


def setup_logging(app):
    """初始化文件日志（幂等）。"""
    global _configured
    log_dir = app.config.get('LOG_DIR')
    if not log_dir:
        return
    os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, str(app.config.get('LOG_LEVEL', 'INFO')).upper(), logging.INFO)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    handlers = {
        'app.log': logging.INFO,
        'error.log': logging.ERROR,
    }
    for filename, handler_level in handlers.items():
        path = os.path.join(log_dir, filename)
        # 避免重复添加处理器（flask run 的 reloader 会二次进入工厂）
        already = any(
            isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '') == os.path.abspath(path)
            for h in app.logger.handlers
        )
        if already:
            continue
        handler = RotatingFileHandler(
            path,
            maxBytes=app.config.get('LOG_MAX_BYTES', 5 * 1024 * 1024),
            backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
            encoding='utf-8',
        )
        handler.setLevel(handler_level)
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)

    app.logger.setLevel(level)
    if not _configured:
        app.logger.info('日志系统初始化完成，目录：%s', log_dir)
        _configured = True


def client_ip():
    """取真实客户端 IP（兼容 Nginx 反代）。"""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def user_agent():
    return (request.headers.get('User-Agent') or '')[:255]


# ---------------------------------------------------------------------------
# 业务日志写入
# ---------------------------------------------------------------------------
def write_operation_log(action, module=None, target_type=None, target_id=None,
                        detail=None, user=None, log_type=None, duration_ms=None,
                        commit=True):
    """写操作日志。任何异常都不能影响主流程，因此整体 try 包裹。

    :param action: 动作名，如 create / update / audit / ban / login
    """
    import json

    from ..extensions import db
    from ..models import OperationLog
    from ..utils.auth import current_user
    from ..utils.constants import LOG_TYPE_OPERATION

    try:
        user = user or current_user()
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, ensure_ascii=False)
        log = OperationLog(
            user_id=getattr(user, 'id', None),
            username=getattr(user, 'student_id', None) or getattr(user, 'username', None),
            log_type=log_type or LOG_TYPE_OPERATION,
            module=module,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip=client_ip(),
            user_agent=user_agent(),
            duration_ms=duration_ms,
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        return log
    except Exception as exc:  # noqa: BLE001 - 日志失败不影响业务
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        if current_app:
            current_app.logger.warning('写操作日志失败：%s', exc)
        return None


def write_login_log(student_id, success, message=None, user=None, commit=True):
    """写登录日志（成功/失败都记）。"""
    from ..extensions import db
    from ..models import LoginLog

    try:
        log = LoginLog(
            user_id=getattr(user, 'id', None),
            student_id=student_id,
            success=bool(success),
            message=message,
            ip=client_ip(),
            user_agent=user_agent(),
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        return log
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        if current_app:
            current_app.logger.warning('写登录日志失败：%s', exc)
        return None


__all__ = ['setup_logging', 'client_ip', 'user_agent', 'write_operation_log', 'write_login_log']
