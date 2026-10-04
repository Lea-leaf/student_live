# -*- coding: utf-8 -*-
"""互动功能接口测试：评论 / 点赞 / 私信 / 互动通知。

覆盖 README v1.2 的待实现项：
- 评论发表 + 楼中楼回复（root_id / parent_id / reply_to_user_id）
- 评论带图与语音（复用 /common/upload 与 media 结构）
- 评论点赞 / 帖子点赞（唯一约束 + 计数回写 + 通知）
- 私信会话列表 / 收发 / 已读回执 / 未读红点
- 被评论、被回复 @、被点赞时写入互动通知
"""

import io
import os
from datetime import datetime, timedelta

import pytest

from tests.conftest import auth_header

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)

WAV_MIN = (
    b'RIFF' + (36).to_bytes(4, 'little') + b'WAVE'
    + b'fmt ' + (16).to_bytes(4, 'little') + (1).to_bytes(2, 'little')
    + (1).to_bytes(2, 'little') + (8000).to_bytes(4, 'little')
    + (16000).to_bytes(4, 'little') + (2).to_bytes(2, 'little')
    + (16).to_bytes(2, 'little') + b'data' + (0).to_bytes(4, 'little')
)


@pytest.fixture()
def upload_root(app, tmp_path):
    """把上传根目录指向临时目录，避免污染真实 uploads/。"""
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


def _upload(client, token, filename, content, mime):
    return client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(content), filename)},
        headers=auth_header(token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]


def _create_comment(client, token, post_id, content='', **extra):
    payload = {'content': content}
    payload.update(extra)
    response = client.post(f'/api/v1/comments/posts/{post_id}/comments',
                           json=payload, headers=auth_header(token))
    body = response.get_json()
    assert body['code'] == 0, body
    return body['data']


# ---------------------------------------------------------------------------
# 评论：发表 / 楼中楼
# ---------------------------------------------------------------------------
def test_comment_tree_create_and_list(client, student, student2, student_token, student2_token, sample_post):
    """顶级评论 + 两层回复：parent_id / root_id / reply_to_user_id 全部正确。"""
    top = _create_comment(client, student2_token, sample_post, '顶级评论')
    assert top['parent_id'] is None
    assert top['root_id'] == top['id']
    top_id = top['id']

    # student 回复 student2 的顶级评论（默认 reply_to = 父评论作者 student2）
    reply = _create_comment(client, student_token, sample_post, '一级回复',
                            parent_id=top_id)
    assert reply['parent_id'] == top_id
    assert reply['root_id'] == top_id
    assert reply['reply_to']['id'] == student2

    # student2 再回复 student 的回复（楼中楼第三层）
    nested = _create_comment(client, student2_token, sample_post, '楼中楼回复',
                             parent_id=reply['id'])
    assert nested['parent_id'] == reply['id']
    assert nested['root_id'] == top_id
    assert nested['reply_to']['id'] == student

    # 游客也能读评论列表；顶级评论带整棵子树
    listing = client.get(f'/api/v1/comments/posts/{sample_post}/comments').get_json()
    assert listing['code'] == 0, listing
    data = listing['data']
    assert data['total'] == 1
    assert data['total_all'] == 3
    root = data['list'][0]
    assert root['id'] == top_id
    assert [item['id'] for item in root['replies']] == [reply['id'], nested['id']]
    assert all(item['liked'] is False for item in root['replies'])

    # 帖子详情里的评论计数应回写为 3
    detail = client.get(f'/api/v1/lost_found/posts/{sample_post}',
                        headers=auth_header(student_token)).get_json()
    assert detail['data']['comment_count'] == 3


def test_comment_reply_to_user_and_media(client, app, student2_token, sample_post, upload_root):
    """评论可带图片与语音；媒体结构、归属记录、文件访问链路都要正确。"""
    image = _upload(client, student2_token, '评论图.png', PNG_1PX, 'image/png')
    voice = _upload(client, student2_token, '评论语音.wav', WAV_MIN, 'audio/wav')

    comment = _create_comment(client, student2_token, sample_post, '',
                              media=[image, voice])
    assert [item['type'] for item in comment['media']] == ['image', 'audio']

    with app.app_context():
        from app.models import Comment, UploadFile

        rows = UploadFile.query.filter_by(owner_type='comment',
                                          owner_id=comment['id']).all()
        assert {row.media_type for row in rows} == {'image', 'audio'}
        # P1 回归：纯媒体评论以空字符串入库，兼容数据库的 NOT NULL
        assert Comment.query.get(comment['id']).content == ''

    assert client.get(image['url']).status_code == 200
    assert client.get(voice['url']).status_code == 200


def test_comment_create_rejects_others_media(client, app, student_token, student2_token,
                                             sample_post, upload_root):
    """不能引用别人上传的媒体文件。"""
    image = _upload(client, student_token, '别人的图.png', PNG_1PX, 'image/png')
    response = client.post(
        f'/api/v1/comments/posts/{sample_post}/comments',
        json={'content': '盗图评论', 'media': [image]},
        headers=auth_header(student2_token),
    ).get_json()
    assert response['code'] != 0


def test_comment_recall_removes_whole_subtree(client, app, student2_token, student_token,
                                               sample_post):
    """用户撤回顶级评论时，楼中楼子回复一起物理删除，计数回写为 0。"""
    from app.models import Comment, Post

    top = _create_comment(client, student2_token, sample_post, '会被撤回的顶级评论')
    reply = _create_comment(client, student_token, sample_post, '子回复',
                            parent_id=top['id'])
    _create_comment(client, student2_token, sample_post, '孙子回复',
                    parent_id=reply['id'])

    response = client.delete(f'/api/v1/comments/{top["id"]}',
                             headers=auth_header(student2_token)).get_json()
    assert response['code'] == 0, response
    assert response['data']['removed'] == 3
    assert '撤回' in response['msg']

    listing = client.get(f'/api/v1/comments/posts/{sample_post}/comments').get_json()
    assert listing['data']['total'] == 0
    assert listing['data']['total_all'] == 0

    with app.app_context():
        assert Post.query.get(sample_post).comment_count == 0
        assert Comment.query.filter_by(post_id=sample_post).count() == 0


# ---------------------------------------------------------------------------
# 评论点赞 / 帖子点赞
# ---------------------------------------------------------------------------
def test_comment_like_toggle_and_notification(client, student_token, student2_token,
                                              sample_post):
    """评论点赞：幂等切换、计数、列表 liked 状态、作者收到通知。"""
    comment = _create_comment(client, student_token, sample_post, '求个赞')

    liked = client.post(f'/api/v1/likes/comments/{comment["id"]}',
                        headers=auth_header(student2_token)).get_json()
    assert liked['code'] == 0
    assert liked['data']['liked'] is True
    assert liked['data']['like_count'] == 1

    listing = client.get(f'/api/v1/comments/posts/{sample_post}/comments',
                         headers=auth_header(student2_token)).get_json()
    assert listing['data']['list'][0]['liked'] is True
    assert listing['data']['list'][0]['like_count'] == 1

    notices = client.get('/api/v1/notifications',
                         headers=auth_header(student_token)).get_json()
    assert any(item['type'] == 'like' for item in notices['data']['list'])

    unliked = client.post(f'/api/v1/likes/comments/{comment["id"]}',
                          headers=auth_header(student2_token)).get_json()
    assert unliked['data']['liked'] is False
    assert unliked['data']['like_count'] == 0


def test_post_like_toggle_and_notification(client, app, student_token, student2_token,
                                           sample_post):
    """帖子点赞：独立于收藏计数，作者收到点赞通知。"""
    liked = client.post(f'/api/v1/likes/posts/{sample_post}',
                        headers=auth_header(student2_token)).get_json()
    assert liked['code'] == 0
    assert liked['data']['liked'] is True
    assert liked['data']['like_count'] == 1

    state = client.get(f'/api/v1/likes/posts/{sample_post}',
                       headers=auth_header(student2_token)).get_json()
    assert state['data']['liked'] is True
    assert state['data']['like_count'] == 1

    with app.app_context():
        from app.models import Post

        assert Post.query.get(sample_post).like_count == 1
        assert Post.query.get(sample_post).favorite_count == 0, '点赞不能影响收藏计数'

    notices = client.get('/api/v1/notifications',
                         headers=auth_header(student_token)).get_json()
    assert any(item['type'] == 'like' and '点赞' in item['title']
               for item in notices['data']['list'])

    unliked = client.post(f'/api/v1/likes/posts/{sample_post}',
                          headers=auth_header(student2_token)).get_json()
    assert unliked['data']['liked'] is False
    assert unliked['data']['like_count'] == 0


# ---------------------------------------------------------------------------
# 互动通知：被评论 / 被回复 @
# ---------------------------------------------------------------------------
def test_comment_notifies_author_and_mention(client, student_token, student2_token,
                                             admin_token, admin, sample_post):
    """评论通知帖子作者；@管理员 时管理员收到「提到我」通知。"""
    response = client.post(
        f'/api/v1/comments/posts/{sample_post}/comments',
        json={'content': '@管理员 你也来看看这条评论'},
        headers=auth_header(student2_token),
    ).get_json()
    assert response['code'] == 0, response

    author_notices = client.get('/api/v1/notifications',
                                headers=auth_header(student_token)).get_json()
    assert any(item['type'] == 'comment'
               for item in author_notices['data']['list'])

    admin_notices = client.get('/api/v1/notifications',
                               headers=auth_header(admin_token)).get_json()
    assert any(item['type'] == 'mention'
               for item in admin_notices['data']['list'])


# ---------------------------------------------------------------------------
# 私信
# ---------------------------------------------------------------------------
def test_message_send_receive_read_receipt_and_unread(client, app, student, student2,
                                                      student_token, student2_token):
    """私信全链路：未读红点  会话列表  拉取即已读  发送方看到已读回执。"""
    # 空消息 / 给自己发消息：都应被拒绝
    empty = client.post(f'/api/v1/messages/with/{student2}', json={'content': ''},
                        headers=auth_header(student_token)).get_json()
    assert empty['code'] != 0
    self_send = client.post(f'/api/v1/messages/with/{student}', json={'content': 'hi'},
                            headers=auth_header(student_token)).get_json()
    assert self_send['code'] != 0

    sent = client.post(f'/api/v1/messages/with/{student2}', json={'content': '你好呀'},
                       headers=auth_header(student_token)).get_json()
    assert sent['code'] == 0, sent
    message = sent['data']
    assert message['sender_id'] == student
    assert message['receiver_id'] == student2
    assert message['is_read'] is False

    # 接收方未读红点
    unread = client.get('/api/v1/messages/unread-count',
                        headers=auth_header(student2_token)).get_json()
    assert unread['data']['unread'] == 1
    assert unread['data']['unread_conversations'] == 1

    # 会话列表：带对方信息、最后一条消息、未读数
    conversations = client.get('/api/v1/messages/conversations',
                               headers=auth_header(student2_token)).get_json()
    assert conversations['data']['total'] == 1
    row = conversations['data']['list'][0]
    assert row['user']['id'] == student
    assert row['last_message']['content'] == '你好呀'
    assert row['unread'] == 1

    # 拉取聊天记录  对方消息自动标记已读
    fetched = client.get(f'/api/v1/messages/with/{student}',
                         headers=auth_header(student2_token)).get_json()
    assert fetched['data']['read_count'] == 1
    assert fetched['data']['list'][0]['is_read'] is True

    unread_after = client.get('/api/v1/messages/unread-count',
                              headers=auth_header(student2_token)).get_json()
    assert unread_after['data']['unread'] == 0

    # 发送方再拉会话：能看到已读回执
    sender_view = client.get(f'/api/v1/messages/with/{student2}',
                             headers=auth_header(student_token)).get_json()
    assert sender_view['data']['list'][0]['is_read'] is True
    assert sender_view['data']['list'][0]['read_at']

    # 只有接收方能通过显式接口标记已读
    forbidden = client.post(f'/api/v1/messages/read/{message["id"]}',
                            headers=auth_header(student_token))
    assert forbidden.status_code == 403
    read_ok = client.post(f'/api/v1/messages/read/{message["id"]}',
                          headers=auth_header(student2_token)).get_json()
    assert read_ok['code'] == 0

    # 接收方收到私信通知
    notices = client.get('/api/v1/notifications',
                         headers=auth_header(student2_token)).get_json()
    assert any(item['type'] == 'message' for item in notices['data']['list'])


def test_message_with_voice_media(client, app, student, student2, student_token,
                                  student2_token, upload_root):
    """私信支持语音：类型自动识别为 voice，上传记录挂到 message。"""
    voice = _upload(client, student_token, '私信语音.wav', WAV_MIN, 'audio/wav')
    sent = client.post(f'/api/v1/messages/with/{student2}',
                       json={'content': '', 'media': [voice]},
                       headers=auth_header(student_token)).get_json()
    assert sent['code'] == 0, sent
    assert sent['data']['msg_type'] == 'voice'
    assert sent['data']['media'][0]['type'] == 'audio'

    with app.app_context():
        from app.models import Message, UploadFile

        row = UploadFile.query.filter_by(owner_type='message',
                                         owner_id=sent['data']['id']).first()
        assert row is not None
        assert row.media_type == 'audio'
        # P1 回归：纯媒体私信以空字符串入库，兼容数据库的 NOT NULL
        assert Message.query.get(sent['data']['id']).content == ''


def test_message_forbids_others_media(client, student, student_token, student2_token, upload_root):
    """私信不能引用他人上传的媒体。"""
    image = _upload(client, student_token, '私信图.png', PNG_1PX, 'image/png')
    sent = client.post(f'/api/v1/messages/with/{student}',
                       json={'content': '盗图', 'media': [image]},
                       headers=auth_header(student2_token)).get_json()
    assert sent['code'] != 0


__all__ = []

def test_purge_comment_removes_media_and_likes(client, app, admin_token, student_token,
                                               student2_token, sample_post, upload_root):
    """管理员彻底删除评论：子树、点赞、上传记录与磁盘文件一起清掉。"""
    image = _upload(client, student2_token, '要被删的评论图.png', PNG_1PX, 'image/png')
    comment = _create_comment(client, student2_token, sample_post, '违规带图评论',
                              media=[image])

    # 楼中楼子回复也要一起物理删除（验证自引用外键不会被拦住）
    reply = _create_comment(client, student_token, sample_post, '违规评论的子回复',
                            parent_id=comment['id'])
    liked = client.post(f'/api/v1/likes/comments/{comment["id"]}',
                        headers=auth_header(student_token)).get_json()
    assert liked['code'] == 0
    liked_reply = client.post(f'/api/v1/likes/comments/{reply["id"]}',
                              headers=auth_header(student2_token)).get_json()
    assert liked_reply['code'] == 0

    purged = client.delete(f'/api/v1/comments/{comment["id"]}?purge=1',
                           headers=auth_header(admin_token)).get_json()
    assert purged['code'] == 0, purged
    assert purged['data']['removed'] >= 2
    assert purged['data']['removed_files'] == 1

    with app.app_context():
        from app.models import Comment, CommentLike, UploadFile

        assert Comment.query.get(comment['id']) is None
        assert Comment.query.get(reply['id']) is None
        assert CommentLike.query.filter_by(comment_id=comment['id']).count() == 0
        assert CommentLike.query.filter_by(comment_id=reply['id']).count() == 0
        assert UploadFile.query.filter_by(owner_type='comment',
                                          owner_id=comment['id']).count() == 0



# ---------------------------------------------------------------------------
# 私信撤回 / 单侧删除
# ---------------------------------------------------------------------------
def test_message_recall_within_window_removes_row_and_media(
        client, app, student, student2, student_token, student2_token, upload_root):
    """5 分钟内撤回：数据库物理删除，媒体记录 / 文件一起清掉，双方会话都不再显示。"""
    voice = _upload(client, student_token, '要撤回的语音.wav', WAV_MIN, 'audio/wav')
    sent = client.post(f'/api/v1/messages/with/{student2}',
                       json={'content': '', 'media': [voice]},
                       headers=auth_header(student_token)).get_json()
    assert sent['code'] == 0, sent
    message_id = sent['data']['id']

    recalled = client.post(f'/api/v1/messages/{message_id}/recall',
                           headers=auth_header(student_token)).get_json()
    assert recalled['code'] == 0, recalled
    assert recalled['data']['removed_files'] == 1

    with app.app_context():
        from app.models import Message, UploadFile

        assert Message.query.get(message_id) is None
        assert UploadFile.query.filter_by(owner_type='message',
                                          owner_id=message_id).count() == 0

    # 双方会话都已看不到
    for token, other_id in ((student_token, student2), (student2_token, student)):
        listing = client.get(f'/api/v1/messages/with/{other_id}',
                             headers=auth_header(token)).get_json()
        assert listing['data']['total'] == 0


def test_message_recall_permission_and_time_window(
        client, app, student, student2, student_token, student2_token):
    """只有发送方能撤回；超过 5 分钟拒绝。"""
    sent = client.post(f'/api/v1/messages/with/{student2}', json={'content': '待撤回'},
                       headers=auth_header(student_token)).get_json()
    message_id = sent['data']['id']

    # 接收方无权撤回
    forbidden = client.post(f'/api/v1/messages/{message_id}/recall',
                            headers=auth_header(student2_token))
    assert forbidden.status_code == 403, forbidden.get_json()

    # 手动把发送时间改成 6 分钟前，模拟超窗口
    with app.app_context():
        from app.extensions import db
        from app.models import Message

        row = Message.query.get(message_id)
        row.created_at = datetime.now() - timedelta(minutes=6)
        db.session.commit()

    expired = client.post(f'/api/v1/messages/{message_id}/recall',
                          headers=auth_header(student_token)).get_json()
    assert expired['code'] == 5003, expired

    with app.app_context():
        from app.models import Message

        assert Message.query.get(message_id) is not None


def test_message_one_sided_delete_then_purge_when_both_sides(
        client, app, student, student2, student_token, student2_token):
    """单侧删除只在自己客户端消失；双方都删除后数据库物理清理。"""
    sent = client.post(f'/api/v1/messages/with/{student2}', json={'content': '会先单侧删除'},
                       headers=auth_header(student_token)).get_json()
    message_id = sent['data']['id']

    # 发送方删除：自己看不到，接收方仍能看到
    sender_deleted = client.delete(f'/api/v1/messages/{message_id}',
                                   headers=auth_header(student_token)).get_json()
    assert sender_deleted['code'] == 0, sender_deleted
    assert sender_deleted['data']['deleted_for'] == 'sender'
    assert sender_deleted['data']['purged'] is False

    sender_view = client.get(f'/api/v1/messages/with/{student2}',
                             headers=auth_header(student_token)).get_json()
    assert sender_view['data']['total'] == 0
    receiver_view = client.get(f'/api/v1/messages/with/{student}',
                               headers=auth_header(student2_token)).get_json()
    assert receiver_view['data']['total'] == 1

    # 接收方也删除：双方 flag 都置位，自动物理删除
    receiver_deleted = client.delete(f'/api/v1/messages/{message_id}',
                                     headers=auth_header(student2_token)).get_json()
    assert receiver_deleted['code'] == 0, receiver_deleted
    assert receiver_deleted['data']['deleted_for'] == 'receiver'
    assert receiver_deleted['data']['purged'] is True

    with app.app_context():
        from app.models import Message

        assert Message.query.get(message_id) is None



def test_comment_recall_window_expires_but_admin_can_still_delete(
        client, app, admin_token, student, student_token, sample_post):
    """用户超过 5 分钟不能撤回自己的评论；管理员仍然可以物理删除。"""
    comment = _create_comment(client, student_token, sample_post, '过期后不能撤回的评论')

    with app.app_context():
        from app.extensions import db
        from app.models import Comment

        row = Comment.query.get(comment['id'])
        row.created_at = datetime.now() - timedelta(minutes=6)
        db.session.commit()

    expired = client.delete(f'/api/v1/comments/{comment["id"]}',
                            headers=auth_header(student_token)).get_json()
    assert expired['code'] == 5003, expired

    with app.app_context():
        from app.models import Comment

        assert Comment.query.get(comment['id']) is not None

    deleted = client.delete(f'/api/v1/admin/comments/{comment["id"]}',
                            headers=auth_header(admin_token)).get_json()
    assert deleted['code'] == 0, deleted

    with app.app_context():
        from app.models import Comment

        assert Comment.query.get(comment['id']) is None
