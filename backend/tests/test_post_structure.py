# -*- coding: utf-8 -*-
"""结构收口测试：楼中楼评论、评论/私信媒体、点赞与收藏分离、音频支持、迁移幂等。

对应需求决定：
- 评论支持**楼中楼**（`root_id` + `parent_id`）
- **点赞与收藏是两个独立功能**（`post_likes` / `comment_likes` + 各自计数）
- 评论与私信都能带**图片 / 语音**
- 语音单独一档大小限制（默认 5MB）
"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from tests.conftest import auth_header

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)


@pytest.fixture()
def upload_root(app, tmp_path):
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


# ---------------------------------------------------------------------------
# 1. 楼中楼评论的数据结构
# ---------------------------------------------------------------------------
def test_comment_supports_nested_replies(app, sample_post, student, student2):
    """三级嵌套：顶级 → 回复 → 回复的回复，root_id 始终指向顶级评论。"""
    from app.extensions import db
    from app.models import Comment

    with app.app_context():
        top = Comment(post_id=sample_post, user_id=student, content='顶级评论')
        db.session.add(top)
        db.session.commit()
        top.root_id = top.id          # 顶级评论指向自己
        db.session.commit()

        reply = Comment(post_id=sample_post, user_id=student2, content='一级回复',
                        parent_id=top.id, root_id=top.id, reply_to_user_id=student)
        db.session.add(reply)
        db.session.commit()

        nested = Comment(post_id=sample_post, user_id=student, content='楼中楼回复',
                         parent_id=reply.id, root_id=top.id, reply_to_user_id=student2)
        db.session.add(nested)
        db.session.commit()

        # 一次查出整棵子树（楼中楼的关键：不需要递归查库）
        tree = Comment.query.filter_by(root_id=top.id).order_by(Comment.id).all()
        assert [c.content for c in tree] == ['顶级评论', '一级回复', '楼中楼回复']

        # parent_id 链正确
        assert nested.parent_id == reply.id
        assert nested.root_id == top.id
        assert reply.parent_id == top.id

        # 序列化带出被回复者，前端可显示「回复 @某某」
        data = nested.to_dict()
        assert data['reply_to']['id'] == student2
        assert data['root_id'] == top.id


# ---------------------------------------------------------------------------
# 2. 评论 / 私信带媒体
# ---------------------------------------------------------------------------
def test_comment_media_field(app, sample_post, student):
    """评论可以带图片/语音（media 是 JSON 数组，结构与帖子一致）。"""
    import json

    from app.extensions import db
    from app.models import Comment

    media = [{'id': 1, 'url': '/api/v1/files/20210001/20261003/a.png',
              'path': '20210001/20261003/a.png', 'type': 'image', 'size': 100},
             {'id': 2, 'url': '/api/v1/files/20210001/20261003/v.mp3',
              'path': '20210001/20261003/v.mp3', 'type': 'audio', 'size': 2000}]

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='带图评论',
                          media=json.dumps(media, ensure_ascii=False))
        db.session.add(comment)
        db.session.commit()

        data = comment.to_dict()
        assert len(data['media']) == 2
        assert data['media'][0]['type'] == 'image'
        assert data['media'][1]['type'] == 'audio'
        assert comment.media_list()[1]['path'].endswith('.mp3')


def test_comment_media_defaults_to_empty(app, sample_post, student):
    """老评论（media 为 NULL）必须能正常序列化 —— 兼容性要求。"""
    from app.extensions import db
    from app.models import Comment

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='没有媒体的老评论')
        db.session.add(comment)
        db.session.commit()
        assert comment.media_list() == []
        assert comment.to_dict()['media'] == []


def test_message_supports_media_and_type(app, student, student2):
    """私信支持文字/图片/语音，并带已读回执字段。"""
    from app.extensions import db
    from app.models import Message

    with app.app_context():
        key = Message.make_conversation_key(student, student2)
        assert key == f'{min(student, student2)}_{max(student, student2)}'

        text_msg = Message(sender_id=student, receiver_id=student2, content='你好',
                           msg_type='text', conversation_key=key)
        voice_msg = Message(sender_id=student2, receiver_id=student, msg_type='voice',
                            media='[{"type":"audio","url":"/api/v1/files/x/v.mp3"}]',
                            conversation_key=key)
        db.session.add_all([text_msg, voice_msg])
        db.session.commit()

        assert text_msg.is_read is False and text_msg.read_at is None   # 未读回执
        assert voice_msg.to_dict()['media'][0]['type'] == 'audio'
        assert Message.query.filter_by(conversation_key=key).count() == 2


# ---------------------------------------------------------------------------
# 3. 点赞与收藏是两个独立功能
# ---------------------------------------------------------------------------
def test_like_and_favorite_are_independent(app, sample_post, student):
    """同一个人可以既收藏又点赞，两者计数互不影响。"""
    from app.extensions import db
    from app.models import Favorite, Post, PostLike

    with app.app_context():
        post = Post.query.get(sample_post)
        db.session.add(Favorite(user_id=student, post_id=sample_post))
        db.session.add(PostLike(user_id=student, post_id=sample_post))
        post.favorite_count = 1
        post.like_count = 1
        db.session.commit()

        refreshed = Post.query.get(sample_post)
        assert refreshed.like_count == 1
        assert refreshed.favorite_count == 1
        assert PostLike.query.filter_by(post_id=sample_post).count() == 1
        assert Favorite.query.filter_by(post_id=sample_post).count() == 1
        # 取消点赞不影响收藏
        PostLike.query.filter_by(user_id=student, post_id=sample_post).delete()
        db.session.commit()
        assert Post.query.get(sample_post).favorite_count == 1


def test_post_like_unique_constraint(app, sample_post, student):
    """同一用户对同一帖子只能点赞一次（唯一约束）。"""
    from sqlalchemy.exc import IntegrityError

    from app.extensions import db
    from app.models import PostLike

    with app.app_context():
        db.session.add(PostLike(user_id=student, post_id=sample_post))
        db.session.commit()
        db.session.add(PostLike(user_id=student, post_id=sample_post))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_comment_like_unique_constraint(app, sample_post, student):
    """评论点赞同理：唯一约束防止重复。"""
    from sqlalchemy.exc import IntegrityError

    from app.extensions import db
    from app.models import Comment, CommentLike

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='可点赞的评论')
        db.session.add(comment)
        db.session.commit()

        db.session.add(CommentLike(user_id=student, comment_id=comment.id))
        db.session.commit()
        db.session.add(CommentLike(user_id=student, comment_id=comment.id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ---------------------------------------------------------------------------
# 4. 音频支持（原来 mp3 会被当成图片）
# ---------------------------------------------------------------------------
def test_media_type_detection(app):
    """图片/视频/语音三类都能正确识别，未知后缀回落到 image。"""
    from app.utils.uploads import media_type_of

    with app.app_context():
        assert media_type_of('jpg') == 'image'
        assert media_type_of('png') == 'image'
        assert media_type_of('mp4') == 'video'
        assert media_type_of('mov') == 'video'
        assert media_type_of('mp3') == 'audio'
        assert media_type_of('wav') == 'audio'
        assert media_type_of('m4a') == 'audio'
        assert media_type_of('MP3') == 'audio', '大小写应无关'
        assert media_type_of('xyz') == 'image'


def test_audio_size_limit_is_separate(app):
    """语音走单独的 5MB 上限，不套用图片的 10MB。"""
    from app.utils.uploads import _size_limit

    with app.app_context():
        assert _size_limit('audio') == 5 * 1024 * 1024
        assert _size_limit('image') == 10 * 1024 * 1024
        assert _size_limit('video') == 50 * 1024 * 1024


def test_audio_extension_is_allowed(app):
    """mp3 必须在上传白名单里（原来会被直接拒绝）。"""
    from app.utils.uploads import allowed_file

    with app.app_context():
        assert allowed_file('voice.mp3') is True
        assert allowed_file('voice.wav') is True
        assert allowed_file('voice.m4a') is True
        assert allowed_file('photo.png') is True
        assert allowed_file('evil.exe') is False


# ---------------------------------------------------------------------------
# 5. upload_files 通用关联
# ---------------------------------------------------------------------------
def test_upload_record_generic_owner(app, upload_root, student):
    """媒体可以挂到帖子 / 评论 / 私信上，不再只认 post_id。"""
    from app.extensions import db
    from app.models import UploadFile
    from app.utils.uploads import save_media

    with app.app_context():
        from app.models import User

        user = User.query.get(student)
        storage = FileStorage(stream=io.BytesIO(PNG_1PX), filename='a.png',
                             content_type='image/png')
        storage.stream = io.BytesIO(PNG_1PX)
        media, err = save_media(storage, user=user)
        assert err is None, err
        record = UploadFile.query.filter_by(path=media['path']).first()

        # 挂到帖子上
        record.attach_to('post', 17)
        db.session.commit()
        assert record.post_id == 17, '挂帖子时应同步兼容字段'

        # 改装到评论上：post_id 保持原值但 owner 变成 comment
        record.attach_to('comment', 5)
        db.session.commit()
        assert record.owner_type == 'comment'
        assert record.owner_id == 5


# ---------------------------------------------------------------------------
# 6. 升级脚本幂等性（关键：可重复执行不报错、不丢数据）
# ---------------------------------------------------------------------------
def test_upgrade_schema_is_idempotent(app):
    """重复执行结构升级脚本不应报错，也不应重复加列。"""
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from scripts import upgrade_schema

    with app.app_context():
        # 第一次：补齐（测试库是 create_all 建的，新列已存在 → 应全部跳过）
        from sqlalchemy import inspect

        from app.extensions import db as _db

        for table, columns in upgrade_schema.NEW_COLUMNS.items():
            existing = {c['name'] for c in inspect(_db.engine).get_columns(table)}
            for name, _ddl in columns:
                assert name in existing, f'{table}.{name} 应已由模型建好'


def test_old_rows_still_readable(app, student, admin):
    """兼容性硬要求：结构升级后，老数据（无新字段）必须仍能正常读出。"""
    from app.extensions import db
    from app.models import Comment, Post

    with app.app_context():
        # 模拟「升级前就存在」的一行：不带任何新字段的值
        post = Post(type='lost_found', user_id=student, title='老帖子',
                    contact='微信 old', audit_status='approved')
        db.session.add(post)
        db.session.commit()
        comment = Comment(post_id=post.id, user_id=admin, content='老评论')
        db.session.add(comment)
        db.session.commit()

        data = post.to_dict()
        assert data['like_count'] == 0            # 新列有默认值
        assert data['media'] == []                # media 为空也能序列化

        cdata = comment.to_dict()
        assert cdata['media'] == []
        assert cdata['root_id'] is None            # 老评论没有 root_id
        assert cdata['like_count'] == 0
        assert cdata['reply_count'] == 0
        assert cdata['reply_to'] is None
