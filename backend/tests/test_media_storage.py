# -*- coding: utf-8 -*-
"""媒体存储与级联删除测试。

对应需求：
- 媒体文件按「用户(学号)/日期/文件」分目录存放，硬盘上能看出数据归属；
- 数据库只存相对路径与访问 URL；
- 删除用户时级联清理其帖子、评论、收藏、媒体记录与**磁盘目录**；
- 不留下孤儿指针。
"""

import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from tests.conftest import auth_header, login

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)


@pytest.fixture()
def upload_root(app, tmp_path):
    """把上传根目录指向临时目录，避免测试污染真实 uploads/。"""
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


def _fake_png(filename='测试图片.png'):
    return FileStorage(stream=io.BytesIO(PNG_1PX), filename=filename, content_type='image/png')


# ---------------------------------------------------------------------------
# 目录结构
# ---------------------------------------------------------------------------
def test_media_stored_under_student_dir(app, student, upload_root):
    """文件落到 uploads/<学号>/<日期>/<uuid>.png，库里只存相对路径。"""
    from app.models import UploadFile, User
    from app.utils.uploads import save_media

    with app.app_context():
        user = User.query.get(student)
        media, err = save_media(_fake_png(), user=user)
        assert err is None, err
        parts = media['path'].split('/')
        assert parts[0] == '20210001', f'第一级应为学号，实际 {media["path"]}'
        assert len(parts) == 3, f'应为 学号/日期/文件 三级，实际 {media["path"]}'
        assert len(parts[1]) == 8 and parts[1].isdigit(), '第二级应为 8 位日期'
        assert parts[2].endswith('.png')

        # 磁盘确实存在
        abs_path = os.path.join(str(upload_root), *parts)
        assert os.path.isfile(abs_path)
        assert os.path.getsize(abs_path) == len(PNG_1PX)

        # 数据库只存地址
        row = UploadFile.query.filter_by(path=media['path']).first()
        assert row is not None
        assert row.url == f'/api/v1/files/{media["path"]}'
        assert row.original_name == '测试图片.png'
        assert row.user_id == user.id


def test_media_path_isolated_per_user(app, student, student2, upload_root):
    """不同用户落在不同一级目录，互不混淆。"""
    from app.models import User
    from app.utils.uploads import save_media

    with app.app_context():
        u1 = User.query.get(student)
        u2 = User.query.get(student2)
        m1, _ = save_media(_fake_png('a.png'), user=u1)
        m2, _ = save_media(_fake_png('b.png'), user=u2)
        assert m1['path'].split('/')[0] == '20210001'
        assert m2['path'].split('/')[0] == '20210002'
        assert os.path.isdir(upload_root / '20210001')
        assert os.path.isdir(upload_root / '20210002')


def test_upload_via_api_uses_user_dir(client, app, student_token, upload_root):
    """走 HTTP 上传接口，同样落到学号目录（端到端）。"""
    response = client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(PNG_1PX), '照片.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    )
    body = response.get_json()
    assert body['code'] == 0, body
    media = body['data']['media'][0]
    assert media['path'].startswith('20210001/')
    assert os.path.isfile(os.path.join(str(upload_root), *media['path'].split('/')))

    # 再通过 url 取回
    fetch = client.get(media['url'])
    assert fetch.status_code == 200
    assert fetch.data == PNG_1PX


def test_safe_segment_blocks_traversal(app, upload_root):
    """目录名必须过滤路径分隔符与 ..，防路径穿越。"""
    from app.utils.uploads import safe_segment

    with app.app_context():
        assert safe_segment('20210001') == '20210001'
        assert '/' not in safe_segment('../../etc')
        assert '\\' not in safe_segment('..\\..\\windows')
        assert safe_segment('..') == 'unknown' or '..' not in safe_segment('..')
        assert safe_segment('') == 'unknown'


def test_file_access_rejects_traversal(client, upload_root):
    """上传目录外的东西读不到。"""
    response = client.get('/api/v1/files/../../run.py')
    assert response.status_code in (400, 404)


# ---------------------------------------------------------------------------
# 删帖 / 删评论
# ---------------------------------------------------------------------------
def test_purge_post_removes_files_and_relations(client, app, admin_token, student_token, upload_root):
    """回收站彻底删除：磁盘文件、媒体记录、评论、收藏一起清掉。"""
    from app.extensions import db
    from app.models import Comment, Favorite, Post, UploadFile
    from app.utils.uploads import save_media

    # 造一条带媒体、评论、收藏的帖子
    created = client.post('/api/v1/lost_found/posts',
                          json={'title': '待彻底删除', 'contact': '微信 a'},
                          headers=auth_header(student_token)).get_json()
    post_id = created['data']['id']
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    with app.app_context():
        from app.models import User
        user = User.query.get(2)
        media, _ = save_media(_fake_png(), user=user, post_id=post_id)
        db.session.add(Comment(post_id=post_id, user_id=user.id, content='评论'))
        db.session.add(Favorite(user_id=user.id, post_id=post_id))
        db.session.commit()
        rel_path = media['path']
        abs_path = os.path.join(str(upload_root), *rel_path.split('/'))
        assert os.path.isfile(abs_path)

    # 软删除 → 彻底删除
    client.delete(f'/api/v1/admin/posts/{post_id}', headers=auth_header(admin_token))
    purged = client.delete(f'/api/v1/admin/trash/{post_id}', headers=auth_header(admin_token)).get_json()
    assert purged['code'] == 0, purged
    assert purged['data']['media_files'] == 1
    assert purged['data']['comments'] == 1
    assert purged['data']['favorites'] == 1

    with app.app_context():
        assert Post.query.get(post_id) is None
        assert UploadFile.query.filter_by(post_id=post_id).count() == 0
        assert Comment.query.filter_by(post_id=post_id).count() == 0
        assert Favorite.query.filter_by(post_id=post_id).count() == 0
        assert not os.path.exists(abs_path), '磁盘文件应被删除'
        from app.utils.cleanup import check_orphans
        assert check_orphans() == []


def test_user_can_recall_own_comment(client, app, student, student_token, sample_post):
    """用户可在 5 分钟内撤回自己的评论：数据库物理删除，计数回写。"""
    from app.extensions import db
    from app.models import Comment, Post

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='我自己的评论')
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id
        post = Post.query.get(sample_post)
        post.comment_count = 1
        db.session.commit()

    response = client.delete(f'/api/v1/comments/{comment_id}', headers=auth_header(student_token))
    body = response.get_json()
    assert body['code'] == 0, body
    assert '撤回' in body['msg']

    with app.app_context():
        assert Comment.query.get(comment_id) is None
        assert Post.query.get(sample_post).comment_count == 0
        listing = client.get(f'/api/v1/comments/posts/{sample_post}/comments').get_json()
        assert listing['data']['total'] == 0


def test_user_cannot_delete_others_comment(client, app, student, student2, student_token,
                                           sample_post):
    """student2 发的评论，student（第三方）不能删。"""
    from app.extensions import db
    from app.models import Comment

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student2, content='别人的评论')
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id

    # 第三方（student）尝试删除 student2 的评论 → 拒绝
    response = client.delete(f'/api/v1/comments/{comment_id}',
                             headers=auth_header(student_token))
    assert response.status_code == 403
    assert response.get_json()['code'] == 2003

    # 评论仍未被删
    with app.app_context():
        assert Comment.query.get(comment_id).is_deleted is False

    # 作者本人在 5 分钟内可以撤回（物理删除）
    own = client.delete(f'/api/v1/comments/{comment_id}',
                        headers=auth_header(login(client, '20210002', '123456')))
    assert own.get_json()['code'] == 0
    with app.app_context():
        assert Comment.query.get(comment_id) is None


def test_admin_can_delete_any_comment(client, app, student, admin_token, sample_post):
    """管理员可删任意评论，并可彻底删除。"""
    from app.extensions import db
    from app.models import Comment

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='违规内容')
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id

    listing = client.get('/api/v1/admin/comments', headers=auth_header(admin_token)).get_json()
    assert listing['code'] == 0
    assert listing['data']['total'] == 1
    assert listing['data']['list'][0]['post']['id'] == sample_post

    # v1.2 起管理员删除默认就是物理删除，不再需要 ?purge=1
    purged = client.delete(f'/api/v1/admin/comments/{comment_id}',
                           headers=auth_header(admin_token)).get_json()
    assert purged['code'] == 0
    with app.app_context():
        import json as _json

        from app.models import Comment, OperationLog

        assert Comment.query.get(comment_id) is None
        # 操作日志里保留被删评论的数据库信息快照
        log = OperationLog.query.filter_by(action='delete_comment',
                                           target_id=comment_id).first()
        assert log is not None
        detail = _json.loads(log.detail)
        assert detail['content'] == '违规内容'
        assert detail['post_id'] == sample_post


# ---------------------------------------------------------------------------
# 删用户（级联）
# ---------------------------------------------------------------------------
def test_purge_user_cascades_and_removes_upload_dir(client, app, admin_token, student_token,
                                                    student, student2, upload_root):
    """彻底删除用户：帖子/评论/收藏/媒体记录全清，磁盘学号目录整个删掉，无孤儿指针。"""
    from app.extensions import db
    from app.models import Comment, Favorite, Post, UploadFile, User
    from app.utils.cleanup import check_orphans
    from app.utils.uploads import save_media

    # 目标用户发帖 + 上传媒体；另一个用户在他帖子上评论、收藏
    created = client.post('/api/v1/lost_found/posts',
                          json={'title': '待删用户的帖子', 'contact': '微信 target'},
                          headers=auth_header(student_token)).get_json()
    post_id = created['data']['id']

    with app.app_context():
        target = User.query.get(student)
        other = User.query.get(student2)
        media, _ = save_media(_fake_png(), user=target, post_id=post_id)
        db.session.add(Comment(post_id=post_id, user_id=other.id, content='路人评论'))
        db.session.add(Favorite(user_id=other.id, post_id=post_id))
        db.session.commit()
        rel_path = media['path']
        abs_path = os.path.join(str(upload_root), *rel_path.split('/'))
        assert os.path.isfile(abs_path)
        assert os.path.isdir(upload_root / '20210001')

    # 二次确认：学号不匹配要拒绝
    wrong = client.delete(f'/api/v1/admin/users/{student}',
                          json={'confirm_student_id': '99999999'},
                          headers=auth_header(admin_token)).get_json()
    assert wrong['code'] != 0
    with app.app_context():
        assert User.query.get(student) is not None, '确认失败时不应删除'

    # 正确学号 → 彻底删除
    result = client.delete(f'/api/v1/admin/users/{student}',
                           json={'confirm_student_id': '20210001'},
                           headers=auth_header(admin_token)).get_json()
    assert result['code'] == 0, result
    stats = result['data']
    assert stats['posts'] == 1
    assert stats['media_rows'] >= 1
    assert stats['media_files'] >= 1
    assert not os.path.isdir(upload_root / '20210001'), '用户上传目录应被整个删除'

    with app.app_context():
        assert User.query.get(student) is None
        assert Post.query.get(post_id) is None
        assert UploadFile.query.filter_by(user_id=student).count() == 0
        # 他人在该帖下的评论也应被清理，不留指向已删帖子的孤儿
        assert Comment.query.filter_by(post_id=post_id).count() == 0
        assert Favorite.query.filter_by(post_id=post_id).count() == 0
        # 磁盘目录整个消失
        assert not os.path.isdir(upload_root / '20210001')
        # 别人的目录不受影响
        assert check_orphans() == []


def test_cannot_delete_self_or_without_confirm(client, admin_token, admin):
    """不能删自己；缺少二次确认字段也拒绝。"""
    response = client.delete(f'/api/v1/admin/users/{admin}',
                             json={'confirm_student_id': 'admin'},
                             headers=auth_header(admin_token)).get_json()
    assert response['code'] != 0

    response = client.delete('/api/v1/admin/users/2', json={},
                             headers=auth_header(admin_token)).get_json()
    assert response['code'] != 0


def test_normal_user_cannot_delete_user(client, student_token, student2):
    """普通用户无权删除账号。"""
    response = client.delete(f'/api/v1/admin/users/{student2}',
                             json={'confirm_student_id': '20210002'},
                             headers=auth_header(student_token))
    assert response.status_code == 403


def test_user_media_endpoint(client, app, admin_token, student, upload_root):
    """管理员可查看某用户的媒体清单与磁盘占用。"""
    from app.models import User
    from app.utils.uploads import save_media

    with app.app_context():
        user = User.query.get(student)
        save_media(_fake_png(), user=user)

    body = client.get(f'/api/v1/admin/users/{student}/media',
                      headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    assert body['data']['db_record_count'] == 1
    assert body['data']['files_on_disk'] == 1
    assert body['data']['bytes_on_disk'] == len(PNG_1PX)
    assert body['data']['upload_dir'].endswith('20210001')


def test_dashboard_media_stats(client, admin_token, upload_root):
    """管理端媒体用量统计可访问。"""
    body = client.get('/api/v1/admin/dashboard/media', headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    for key in ('root_files', 'root_bytes', 'users', 'orphan_count'):
        assert key in body['data']
