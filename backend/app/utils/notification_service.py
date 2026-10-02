# -*- coding: utf-8 -*-
"""通知服务：所有模块产生通知都走这里，方便统一加「站内信/邮件/短信」通道。

当前实现为站内通知表写入；扩展点：
- `send()` 里追加邮件/短信发送即可，不影响调用方；
- 未来接 WebSocket 实时推送，只需在 commit 后 publish 一个事件。
"""

import json

from flask import current_app

from ..extensions import db
from ..utils.constants import NOTIFY_SYSTEM


def send(user_id, title, content=None, notify_type=NOTIFY_SYSTEM, ref_id=None, link=None, commit=True):
    """给单个用户发通知。

    :param link: dict，例如 {'route': 'post-detail', 'post_id': 1}
    """
    from ..models import Notification

    if not user_id:
        return None
    try:
        notification = Notification(
            user_id=user_id,
            type=notify_type,
            title=title,
            content=content,
            ref_id=ref_id,
            link=json.dumps(link, ensure_ascii=False) if isinstance(link, (dict, list)) else link,
        )
        db.session.add(notification)
        if commit:
            db.session.commit()
        return notification
    except Exception as exc:  # noqa: BLE001 - 通知失败不影响主业务
        db.session.rollback()
        if current_app:
            current_app.logger.warning('发送通知失败：%s', exc)
        return None


def send_many(user_ids, title, content=None, notify_type=NOTIFY_SYSTEM, ref_id=None, link=None):
    """群发通知（例如系统维护公告）。"""
    from ..models import Notification

    created = 0
    for uid in set(user_ids or []):
        if send(uid, title, content, notify_type, ref_id, link, commit=False):
            created += 1
    if created:
        db.session.commit()
    return created


def unread_count(user_id):
    """未读数量（前端顶部小红点）。"""
    from ..models import Notification

    if not user_id:
        return 0
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()


def mark_read(user_id, notification_id=None, all_read=False):
    """标记已读。"""
    from datetime import datetime

    from ..models import Notification

    query = Notification.query.filter_by(user_id=user_id, is_read=False)
    if not all_read:
        query = query.filter_by(id=notification_id)
    rows = query.all()
    now = datetime.now()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.session.commit()
    return len(rows)


__all__ = ['send', 'send_many', 'unread_count', 'mark_read']
