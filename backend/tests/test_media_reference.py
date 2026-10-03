# -*- coding: utf-8 -*-
"""媒体地址一致性回归测试。

**这个文件是为了一个真实踩过的坑而写的**：
    媒体地址在数据库里存了**两处** —— `upload_files.path/url` 和 `posts.media`（JSON）。
    当初做「日期/文件」→「学号/日期/文件」布局迁移时，只改了 `upload_files`，
    忘了 `posts.media`，结果帖子详情页加载图片报 404
    （`/api/v1/files/20261002/xxx.png` 这种旧地址）。

因此这里断言：**创建帖子后，`posts.media` 里的 url/path 必须与 `upload_files` 记录一致，
且符合「学号/日期/文件」三级结构。**
"""

import io
import os
import re

import pytest
from werkzeug.datastructures import FileStorage

from tests.conftest import auth_header

PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)

#: 期望的相对路径：<学号>/<8位日期>/<uuid>.png
NEW_LAYOUT = re.compile(r'^[^/]+/\d{8}/[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp|mp4|mov)$')
#: 旧的「只有日期」布局
LEGACY_LAYOUT = re.compile(r'^\d{8}/[^/]+$')


@pytest.fixture()
def upload_root(app, tmp_path):
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


def _png(filename='图片.png'):
    return FileStorage(stream=io.BytesIO(PNG_1PX), filename=filename, content_type='image/png')


def test_upload_returns_consistent_path_and_url(client, student_token, upload_root):
    """上传接口返回的 path/url 必须自洽，且是新布局。"""
    response = client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(PNG_1PX), 'a.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    )
    media = response.get_json()['data']['media'][0]
    assert NEW_LAYOUT.match(media['path']), f'路径不是新布局：{media["path"]}'
    assert media['url'] == f'/api/v1/files/{media["path"]}', (
        f'url 与 path 不一致：url={media["url"]} path={media["path"]}'
    )
    assert not LEGACY_LAYOUT.match(media['path'])
    # 文件真的能取回
    assert client.get(media['url']).status_code == 200


def test_post_media_matches_upload_record(client, app, student_token, upload_root):
    """核心回归：落库的帖子 media 必须与 upload_files 记录完全一致。

    这是当初 404 的直接成因（posts.media 残留旧地址）。
    """
    from app.models import Post, UploadFile

    # 1) 上传
    media = client.post(
        '/api/v1/lost_found/posts/upload',
        data={'files': (io.BytesIO(PNG_1PX), 'b.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]

    # 2) 发布帖子时带上 media（前端就是这么提交的）
    created = client.post(
        '/api/v1/lost_found/posts',
        json={'title': '带图帖子', 'contact': '微信 a', 'media': [media]},
        headers=auth_header(student_token),
    ).get_json()
    assert created['code'] == 0, created
    post_id = created['data']['id']

    # 3) 帖子 media 与 upload_files 必须一致
    with app.app_context():
        post = Post.query.get(post_id)
        post_media = post.to_dict()['media']
        assert len(post_media) == 1
        item = post_media[0]

        assert NEW_LAYOUT.match(item['path']), f'帖子 media 路径不是新布局：{item["path"]}'
        assert not LEGACY_LAYOUT.match(item['path']), (
            f'帖子 media 残留旧布局地址：{item["path"]}（这正是当初 404 的原因）'
        )
        assert item['url'] == f'/api/v1/files/{item["path"]}'

        record = UploadFile.query.filter_by(id=item['id']).first()
        assert record is not None
        assert record.path == item['path'], 'posts.media 与 upload_files.path 不一致'
        assert record.url == item['url'], 'posts.media 与 upload_files.url 不一致'

    # 4) 前端拿到的 url 必须真能取到文件
    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student_token)).get_json()
    for item in detail['data']['media']:
        assert client.get(item['url']).status_code == 200, f'图片 404：{item["url"]}'


def test_all_post_media_urls_are_reachable(client, app, student_token, admin_token, upload_root):
    """全局扫描：任何帖子里的 media url 都必须能取到文件（防回归的总闸）。"""
    from app.models import Post

    media = client.post(
        '/api/v1/lost_found/posts/upload',
        data={'files': (io.BytesIO(PNG_1PX), 'c.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]
    post_id = client.post('/api/v1/lost_found/posts',
                          json={'title': '扫描用', 'contact': '微信 a', 'media': [media]},
                          headers=auth_header(student_token)).get_json()['data']['id']
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    with app.app_context():
        stale = []
        for post in Post.query.filter(Post.is_deleted.is_(False)).all():
            for item in post.to_dict()['media']:
                if LEGACY_LAYOUT.match(item.get('path', '')):
                    stale.append((post.id, item.get('path')))
        assert stale == [], f'发现残留旧布局地址：{stale}'

    # 列表接口返回的媒体地址也要能取到
    listing = client.get('/api/v1/lost_found/posts?page=1&size=50').get_json()
    for row in listing['data']['list']:
        for item in row.get('media') or []:
            assert client.get(item['url']).status_code == 200, f'列表图片 404：{item["url"]}'


def test_media_json_survives_edit(client, app, student_token, upload_root):
    """编辑帖子时若不带 media，原有媒体不应丢失或变形。"""
    from app.models import Post

    media = client.post(
        '/api/v1/lost_found/posts/upload',
        data={'files': (io.BytesIO(PNG_1PX), 'd.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]
    post_id = client.post('/api/v1/lost_found/posts',
                          json={'title': '原标题', 'contact': '微信 a', 'media': [media]},
                          headers=auth_header(student_token)).get_json()['data']['id']

    client.put(f'/api/v1/lost_found/posts/{post_id}',
               json={'title': '改后标题'}, headers=auth_header(student_token))

    with app.app_context():
        post = Post.query.get(post_id)
        assert post.title == '改后标题'
        items = post.to_dict()['media']
        assert len(items) == 1, '编辑不应导致媒体丢失'
        assert items[0]['url'] == media['url']
        assert client.get(items[0]['url']).status_code == 200


def test_file_url_has_no_doubled_prefix(client, student_token, upload_root):
    """上传返回的 url 不能出现 /api/v1/api/v1（前端曾因此 404）。"""
    media = client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(PNG_1PX), 'e.png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]
    assert '/api/v1/api/v1' not in media['url'], f'前缀重复：{media["url"]}'
