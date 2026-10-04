# -*- coding: utf-8 -*-
"""媒体清理测试：未提交上传 + 磁盘孤儿文件。"""

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


@pytest.fixture()
def upload_root(app, tmp_path):
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


def test_admin_media_clean_removes_unattached_and_orphan(
        client, app, admin_token, student_token, upload_root):
    from app.extensions import db
    from app.models import UploadFile

    uploaded = client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(PNG_1PX), '未提交的图.png', 'image/png')},
        headers=auth_header(student_token),
        content_type='multipart/form-data',
    ).get_json()['data']['media'][0]

    # 把上传记录改成 30 小时前，模拟传了但一直没提交
    with app.app_context():
        row = UploadFile.query.get(uploaded['id'])
        row.created_at = datetime.now() - timedelta(hours=30)
        db.session.commit()

    # 再手动造一个没有数据库记录的孤儿文件
    orphan_dir = os.path.join(str(upload_root), '20210001', '20260101')
    os.makedirs(orphan_dir, exist_ok=True)
    orphan_path = os.path.join(orphan_dir, 'orphan.png')
    with open(orphan_path, 'wb') as file_obj:
        file_obj.write(PNG_1PX)

    stats = client.get('/api/v1/admin/dashboard/media',
                       headers=auth_header(admin_token)).get_json()
    assert stats['code'] == 0
    assert stats['data']['unattached_count'] == 1
    assert stats['data']['orphan_count'] >= 1

    cleaned = client.post('/api/v1/admin/dashboard/media/clean',
                          json={'hours': 24},
                          headers=auth_header(admin_token)).get_json()
    assert cleaned['code'] == 0, cleaned
    assert cleaned['data']['unattached']['records'] == 1
    assert cleaned['data']['orphan_removed'] >= 1

    with app.app_context():
        assert UploadFile.query.get(uploaded['id']) is None
    assert not os.path.exists(os.path.join(str(upload_root), *uploaded['path'].split('/')))
    assert not os.path.exists(orphan_path)


__all__ = []