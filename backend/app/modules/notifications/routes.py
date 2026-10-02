# -*- coding: utf-8 -*-
"""通知模块。

通知来源：审核结果、评论、私信、系统公告。
统一由 `utils/notification_service.py` 写入，本模块只提供查询与已读操作。
"""

from flask import Blueprint

from ...extensions import db
from ...models import Notification
from ...models.base import paginate
from ...utils.auth import token_required
from ...utils.helpers import current_page_args
from ...utils.notification_service import mark_read as mark_read_service
from ...utils.notification_service import unread_count
from ...utils.response import error, paginated, success
from ...utils.validators import ValidationError, as_error

bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@bp.get('')
@token_required
def list_notifications():
    """我的通知列表。参数：is_read=0/1、type、page、size。"""
    from flask import request

    from ...utils.auth import current_user

    try:
        page, size = current_page_args()
        query = Notification.query.filter_by(user_id=current_user().id)
        is_read = request.args.get('is_read')
        if is_read in ('0', '1'):
            query = query.filter_by(is_read=is_read == '1')
        notify_type = request.args.get('type')
        if notify_type:
            query = query.filter_by(type=notify_type)
        query = query.order_by(Notification.id.desc())
        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size,
                         extra={'unread': unread_count(current_user().id)})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/unread-count')
@token_required
def get_unread_count():
    """未读数量（前端小红点轮询接口）。"""
    from ...utils.auth import current_user

    return success({'unread': unread_count(current_user().id)})


@bp.post('/read/<int:notification_id>')
@token_required
def read_one(notification_id):
    """标记单条已读。"""
    from ...utils.auth import current_user

    user = current_user()
    row = Notification.query.filter_by(id=notification_id, user_id=user.id).first()
    if row is None:
        return error('通知不存在', 5002)
    count = mark_read_service(user.id, notification_id=notification_id)
    return success({'updated': count}, msg='已标记为已读')


@bp.post('/read-all')
@token_required
def read_all():
    """全部标记已读。"""
    from ...utils.auth import current_user

    count = mark_read_service(current_user().id, all_read=True)
    return success({'updated': count}, msg='已全部标记为已读')


@bp.delete('/<int:notification_id>')
@token_required
def delete_notification(notification_id):
    """删除一条通知。"""
    from ...utils.auth import current_user

    row = Notification.query.filter_by(id=notification_id, user_id=current_user().id).first()
    if row is None:
        return error('通知不存在', 5002)
    db.session.delete(row)
    db.session.commit()
    return success(msg='已删除')


__all__ = ['bp']
