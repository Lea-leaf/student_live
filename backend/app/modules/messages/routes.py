# -*- coding: utf-8 -*-
"""私信模块（v1.2 实现）。

需求待定项：私信是否实时 → 默认先普通接口，预留 WebSocket。
表结构已按会话分组（conversation_key）设计，后续接实时推送不用改表。
"""

from flask import Blueprint

from ...utils.auth import token_required
from ...utils.response import error, success

bp = Blueprint('messages', __name__, url_prefix='/messages')

FEATURE_CODE = 7002
FEATURE_MSG = '私信功能将在 v1.2 版本开放（预留 WebSocket 实时通道）'


@bp.get('/conversations')
@token_required
def conversations():
    """会话列表。"""
    return success({'list': [], 'total': 0})


@bp.get('/with/<int:user_id>')
@token_required
def messages_with(user_id):
    """与某用户的私信记录。"""
    return success({'list': [], 'total': 0})


@bp.post('/with/<int:user_id>')
@token_required
def send_message(user_id):
    """发送私信。"""
    return error(FEATURE_MSG, FEATURE_CODE, http_status=501)


@bp.post('/read/<int:message_id>')
@token_required
def mark_read(message_id):
    """标记已读。"""
    return error(FEATURE_MSG, FEATURE_CODE, http_status=501)


__all__ = ['bp']
