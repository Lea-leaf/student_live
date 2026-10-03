# -*- coding: utf-8 -*-
"""私信模块（v1.2：会话列表 / 收发 / 已读回执 / 未读红点）。

接口一览（前缀 /api/v1/messages）：
    GET    /conversations          会话列表（最后一条 + 未读数）
    GET    /with/{user_id}         与某人的消息记录（拉取即把对方发来的未读标记为已读）
    POST   /with/{user_id}         发送私信（文字 / 图片 / 语音）
    POST   /read/{message_id}      已读回执（仅接收方）
    POST   /read-all               全部已读
    GET    /unread-count           未读红点数量

实时化预留：表结构已按会话分组（conversation_key），后续接 WebSocket
只需在发送成功后 publish 事件，本文件接口形状不用变。
"""

import json
from datetime import datetime, timedelta

from flask import Blueprint, request

from ...extensions import db
from ...models import Message, User
from ...models.base import paginate
from ...utils.auth import current_user, token_required
from ...utils.constants import MESSAGE_TYPES, NOTIFY_MESSAGE
from ...utils.helpers import current_page_args
from ...utils.logger import write_operation_log
from ...utils.notification_service import send
from ...utils.response import CODE_FORBIDDEN, CODE_MESSAGE_RECALL_EXPIRED, error, paginated, success
from ...utils.uploads import attach_upload_owners, sanitize_media_list
from ...utils.validators import ValidationError, as_error, clean_text, get_json

bp = Blueprint('messages', __name__, url_prefix='/messages')

#: 撤回时间窗口：发送后 5 分钟内
RECALL_WINDOW_SECONDS = 5 * 60


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _display_name(user):
    return getattr(user, 'nickname', None) or getattr(user, 'username', None) \
        or getattr(user, 'student_id', '同学')


def _as_int(value, field):
    if value in (None, '', 'null', 'undefined'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'{field} 必须是整数') from None


def _visible_messages(user_id):
    """当前用户能看到的私信（软删除只影响自己的那一侧）。"""
    return Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == user_id, Message.sender_deleted.is_(False)),
            db.and_(Message.receiver_id == user_id, Message.receiver_deleted.is_(False)),
        )
    )


def _conversation_query(me_id, other_id):
    """会话消息查询：优先 conversation_key，同时兼容历史空键数据。"""
    key = Message.make_conversation_key(me_id, other_id)
    return _visible_messages(me_id).filter(
        db.or_(
            Message.conversation_key == key,
            db.and_(
                db.or_(
                    db.and_(Message.sender_id == me_id, Message.receiver_id == other_id),
                    db.and_(Message.sender_id == other_id, Message.receiver_id == me_id),
                )
            ),
        )
    )


def _summary(message):
    text = (message.content or '').strip()
    if text:
        return text[:40]
    types = [item.get('type') for item in message.media_list() if isinstance(item, dict)]
    if not types:
        return '[消息]'
    return {'audio': '[语音]', 'image': '[图片]', 'video': '[视频]'}.get(types[0], '[消息]')


def _infer_msg_type(media, explicit=None):
    """消息类型：前端可显式传，但更推荐由媒体类型自动推断。"""
    if explicit:
        return explicit
    types = {item.get('type') for item in media or [] if isinstance(item, dict)}
    if 'audio' in types:
        return 'voice'
    if 'video' in types:
        return 'video'
    if 'image' in types:
        return 'image'
    return 'text'


def _mark_conversation_read(me_id, other_id):
    """把 other 发给我的未读消息全部标记为已读，返回条数（已读回执数据来源）。"""
    rows = Message.query.filter_by(
        sender_id=other_id, receiver_id=me_id, is_read=False).all()
    if not rows:
        return 0
    now = datetime.now()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.session.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# 会话列表
# ---------------------------------------------------------------------------
@bp.get('/conversations')
@token_required
def conversations():
    """会话列表：按最后一条消息倒序，带对方信息与未读数。"""
    try:
        me = current_user()
        page, size = current_page_args()
        messages = _visible_messages(me.id).order_by(Message.id.desc()).all()

        entries = {}
        for message in messages:
            other_id = message.receiver_id if message.sender_id == me.id else message.sender_id
            if not other_id or other_id == me.id:
                continue
            entry = entries.get(other_id)
            if entry is None:
                entry = {'user_id': other_id, 'last_message': message, 'unread': 0}
                entries[other_id] = entry
            if message.receiver_id == me.id and not message.is_read:
                entry['unread'] += 1

        user_map = {}
        if entries:
            user_map = {
                user.id: user
                for user in User.query.filter(User.id.in_(list(entries.keys()))).all()
            }

        rows = []
        for other_id, entry in entries.items():
            user = user_map.get(other_id)
            if user is None:
                continue
            rows.append({
                'user_id': other_id,
                'user': user.to_brief(),
                'last_message': entry['last_message'].to_dict(),
                'unread': entry['unread'],
            })
        rows.sort(key=lambda item: item['last_message']['id'], reverse=True)

        total = len(rows)
        unread = sum(item['unread'] for item in rows)
        unread_conversations = sum(1 for item in rows if item['unread'])
        start = (page - 1) * size
        return paginated(rows[start:start + size], total, page, size,
                         extra={'unread': unread, 'unread_conversations': unread_conversations})
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 消息记录
# ---------------------------------------------------------------------------
@bp.get('/with/<int:user_id>')
@token_required
def messages_with(user_id):
    """与某用户的聊天记录。

    拉取即视为阅读：对方发来的未读消息会在这里统一标记已读，
    返回的 `read_count` 可用于前端提示，发送方刷新会话即可看到「已读」。
    """
    try:
        me = current_user()
        target = User.query.get(user_id)
        if target is None:
            raise ValidationError('用户不存在', 3002)
        if target.id == me.id:
            raise ValidationError('不能给自己发私信')

        page, size = current_page_args()
        query = _conversation_query(me.id, user_id).order_by(Message.id.desc())
        items, total, page, size = paginate(query, page, size)
        read_count = _mark_conversation_read(me.id, user_id)

        # 翻页时每页内部按时间正序返回，前端聊天窗口可直接从上往下渲染
        data = [item.to_dict() for item in reversed(items)]
        return paginated(data, total, page, size, extra={
            'user': target.to_brief(),
            'read_count': read_count,
            'conversation_key': Message.make_conversation_key(me.id, user_id),
        })
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 发送
# ---------------------------------------------------------------------------
@bp.post('/with/<int:user_id>')
@token_required
def send_message(user_id):
    """发送私信（文字 / 图片 / 语音）。

    JSON 方式：先调 /common/upload 拿 media，再提交 media 数组；
    multipart 方式：直接带 files 字段一起提交。
    """
    from ...utils.uploads import save_media_list

    try:
        me = current_user()
        target = User.query.get(user_id)
        if target is None:
            raise ValidationError('用户不存在', 3002)
        if target.id == me.id:
            raise ValidationError('不能给自己发私信')
        if target.is_banned:
            return error('对方账号已被封禁，暂时无法发送私信', CODE_FORBIDDEN)

        is_multipart = bool(request.content_type and 'multipart/form-data' in request.content_type)
        if is_multipart:
            data = request.form.to_dict()
            files = request.files.getlist('files') or request.files.getlist('file')
        else:
            data = get_json()
            files = []

        content = clean_text(data.get('content'), 2000, '私信内容')
        post_id = _as_int(data.get('post_id'), 'post_id')

        if files:
            saved, errors = save_media_list(files, user=me)
            if errors and not saved:
                return error('；'.join(errors), 6001)
            media, media_error = sanitize_media_list(saved, user=me)
        else:
            media, media_error = sanitize_media_list(data.get('media') or [], user=me)
        if media_error:
            raise ValidationError(media_error)
        if not content and not media:
            raise ValidationError('消息内容不能为空')

        explicit_type = str(data.get('msg_type') or '').strip().lower()
        if explicit_type == 'audio':
            explicit_type = 'voice'
        if explicit_type and explicit_type not in MESSAGE_TYPES:
            raise ValidationError('msg_type 取值非法')
        msg_type = _infer_msg_type(media, explicit_type)

        message = Message(
            sender_id=me.id,
            receiver_id=target.id,
            content=content or '',
            msg_type=msg_type,
            media=json.dumps(media, ensure_ascii=False) if media else None,
            is_read=False,
            conversation_key=Message.make_conversation_key(me.id, target.id),
            post_id=post_id,
        )
        db.session.add(message)
        db.session.flush()
        attach_upload_owners(media, 'message', message.id)
        db.session.commit()

        write_operation_log('send_message', module='messages', target_type='message',
                            target_id=message.id, detail={'receiver_id': target.id})
        send(
            target.id,
            '你收到一条新私信',
            f'{_display_name(me)}：{_summary(message)}',
            notify_type=NOTIFY_MESSAGE,
            ref_id=message.id,
            link={'route': 'messages', 'user_id': me.id},
        )
        return success(message.to_dict(), msg='发送成功')
    except ValidationError as exc:
        return as_error(exc)


# ---------------------------------------------------------------------------
# 撤回 / 单侧删除
# ---------------------------------------------------------------------------
@bp.post('/<int:message_id>/recall')
@token_required
def recall_message(message_id):
    """撤回自己发送的私信：5 分钟内、仅发送方、**数据库层面物理删除**。

    撤回后双方会话里都不再显示，媒体文件与对应的私信通知一并清理。
    """
    from ...utils.cleanup import purge_message

    me = current_user()
    message = Message.query.get(message_id)
    if message is None:
        return error('消息不存在或已被撤回', 1002)
    if message.sender_id != me.id:
        return error('只能撤回自己发送的消息', CODE_FORBIDDEN, http_status=403)

    elapsed = (datetime.now() - message.created_at).total_seconds()
    if elapsed > RECALL_WINDOW_SECONDS:
        return error('超过 5 分钟的消息不能撤回', CODE_MESSAGE_RECALL_EXPIRED)

    stats = purge_message(message)
    write_operation_log('recall_message', module='messages', target_type='message',
                        target_id=message_id, detail=stats)
    return success(stats, msg='已撤回')


@bp.delete('/<int:message_id>')
@token_required
def delete_message(message_id):
    """删除自己私信里的某条消息（单侧隐藏，对方仍然看得到）。

    - 我是发送方：置 `sender_deleted=True`；
    - 我是接收方：置 `receiver_deleted=True`；
    - 双方都删除后，消息自动做数据库物理删除并清理媒体 / 通知。
    """
    from ...utils.cleanup import purge_message

    me = current_user()
    message = Message.query.get(message_id)
    if message is None:
        return error('消息不存在或已删除', 1002)

    if message.sender_id == me.id:
        message.sender_deleted = True
        side = 'sender'
    elif message.receiver_id == me.id:
        message.receiver_deleted = True
        side = 'receiver'
    else:
        return error('无权删除该消息', CODE_FORBIDDEN, http_status=403)

    if message.sender_deleted and message.receiver_deleted:
        stats = purge_message(message)
        return success({
            'message_id': message_id,
            'deleted_for': side,
            'purged': True,
            'removed_files': stats['removed_files'],
        }, msg='消息已删除')

    db.session.commit()
    return success({'message_id': message_id, 'deleted_for': side, 'purged': False},
                   msg='消息已删除')


# ---------------------------------------------------------------------------
# 已读回执 / 未读红点
# ---------------------------------------------------------------------------
@bp.post('/read/<int:message_id>')
@token_required
def mark_read(message_id):
    """标记单条私信已读（只有接收方能标记，发送方据此显示已读回执）。"""
    me = current_user()
    message = Message.query.get(message_id)
    if message is None:
        return error('消息不存在', 1002)
    if message.receiver_id != me.id:
        return error('只能标记发给自己的私信', CODE_FORBIDDEN, http_status=403)

    if not message.is_read:
        message.is_read = True
        message.read_at = datetime.now()
        db.session.commit()
    return success({
        'message_id': message.id,
        'is_read': True,
        'read_at': message.read_at.strftime('%Y-%m-%d %H:%M:%S') if message.read_at else None,
    }, msg='已读')


@bp.post('/read-all')
@token_required
def read_all():
    """把所有发给我的未读私信标记为已读。"""
    me = current_user()
    count = Message.query.filter_by(receiver_id=me.id, is_read=False,
                                    receiver_deleted=False).update(
        {'is_read': True, 'read_at': datetime.now()}, synchronize_session=False)
    db.session.commit()
    return success({'updated': count}, msg='已全部标记为已读')


@bp.get('/unread-count')
@token_required
def unread_count():
    """未读红点：未读消息总数 + 有未读消息的会话数。"""
    me = current_user()
    query = Message.query.filter_by(receiver_id=me.id, is_read=False,
                                    receiver_deleted=False)
    unread = query.count()
    conversations = db.session.query(Message.sender_id).filter_by(
        receiver_id=me.id, is_read=False, receiver_deleted=False
    ).distinct().count()
    return success({'unread': unread, 'unread_conversations': conversations})


__all__ = ['bp']