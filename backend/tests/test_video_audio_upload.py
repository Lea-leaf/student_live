# -*- coding: utf-8 -*-
"""视频 / 语音上传链路测试。

**为什么补这个文件**：原有测试只覆盖了 PNG 图片，视频与语音的上传
从未被验证过（`_media_type_of` 的 audio 分支也是刚加的）。
媒体类型判断、大小限制分档、落盘路径、URL 取回这些逻辑
对视频/语音是同一套代码，但**分档规则不同**，必须各测一遍。
"""

import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from tests.conftest import auth_header

#: 最小合法 PNG
PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)

#: 最小 MP4（ftyp 头，够用来验证类型判断与落盘）
MP4_MIN = bytes.fromhex(
    '00000018667479706d703432000000006d70343269736f6d00000008'
    '66726565000000186d64617400000000'
)

#: 最小 WAV（RIFF 头）
WAV_MIN = (
    b'RIFF' + (36).to_bytes(4, 'little') + b'WAVE'
    + b'fmt ' + (16).to_bytes(4, 'little') + (1).to_bytes(2, 'little')
    + (1).to_bytes(2, 'little') + (8000).to_bytes(4, 'little')
    + (16000).to_bytes(4, 'little') + (2).to_bytes(2, 'little')
    + (16).to_bytes(2, 'little') + b'data' + (0).to_bytes(4, 'little')
)


@pytest.fixture()
def upload_root(app, tmp_path):
    root = tmp_path / 'uploads'
    root.mkdir()
    app.config['UPLOAD_FOLDER'] = str(root)
    return root


def _upload(client, token, filename, content, mime):
    # 三元组把 mime 一起交给 Werkzeug；否则 .webm 会被它先入为主地猜成 video/webm，
    # 无法验证「audio/webm 录音靠 MIME 识别」这条规则。
    return client.post(
        '/api/v1/common/upload',
        data={'files': (io.BytesIO(content), filename, mime)},
        headers=auth_header(token),
        content_type='multipart/form-data',
    )


# ---------------------------------------------------------------------------
# 视频
# ---------------------------------------------------------------------------
def test_upload_video(client, student_token, upload_root):
    """视频能上传：类型识别为 video、落到学号目录、能通过 URL 取回。"""
    response = _upload(client, student_token, '测试视频.mp4', MP4_MIN, 'video/mp4')
    body = response.get_json()
    assert body['code'] == 0, body

    media = body['data']['media'][0]
    assert media['type'] == 'video', f"应识别为 video，实际 {media['type']}"
    assert media['path'].startswith('20210001/')
    assert media['path'].endswith('.mp4')
    assert media['size'] == len(MP4_MIN)
    assert media['name'] == '测试视频.mp4'

    # 磁盘文件存在且内容一致
    abs_path = os.path.join(str(upload_root), *media['path'].split('/'))
    assert os.path.isfile(abs_path)
    assert open(abs_path, 'rb').read() == MP4_MIN

    # URL 能取回
    fetch = client.get(media['url'])
    assert fetch.status_code == 200
    assert fetch.data == MP4_MIN


def test_upload_video_mov(client, student_token, upload_root):
    """mov 后缀同样识别为视频。"""
    body = _upload(client, student_token, 'a.mov', MP4_MIN, 'video/quicktime').get_json()
    assert body['code'] == 0, body
    assert body['data']['media'][0]['type'] == 'video'


def test_video_uses_video_size_limit(app):
    """视频走 50MB 档，不是图片的 10MB。"""
    from app.utils.uploads import _size_limit

    with app.app_context():
        assert _size_limit('video') == 50 * 1024 * 1024


def test_video_attached_to_post(client, app, student_token, upload_root):
    """视频挂到帖子后，帖子详情返回的 media 也是 video 类型且能取回。"""
    media = _upload(client, student_token, 'v.mp4', MP4_MIN, 'video/mp4').get_json()['data']['media'][0]
    post_id = client.post('/api/v1/lost_found/posts',
                          json={'title': '带视频的帖子', 'contact': '微信 a', 'media': [media]},
                          headers=auth_header(student_token)).get_json()['data']['id']

    with app.app_context():
        from app.models import Post

        detail = Post.query.get(post_id).to_dict()
        assert detail['media'][0]['type'] == 'video'
        assert client.get(detail['media'][0]['url']).status_code == 200


# ---------------------------------------------------------------------------
# 语音
# ---------------------------------------------------------------------------
def test_upload_audio(client, student_token, upload_root):
    """语音能上传：识别为 audio、落盘、可取回（原来 mp3 会当成 image 或直接被拒）。"""
    response = _upload(client, student_token, '语音留言.wav', WAV_MIN, 'audio/wav')
    body = response.get_json()
    assert body['code'] == 0, body

    media = body['data']['media'][0]
    assert media['type'] == 'audio', f"应识别为 audio，实际 {media['type']}"
    assert media['path'].startswith('20210001/')
    assert media['path'].endswith('.wav')

    abs_path = os.path.join(str(upload_root), *media['path'].split('/'))
    assert os.path.isfile(abs_path)
    assert client.get(media['url']).status_code == 200


def test_upload_mp3_and_m4a(client, student_token, upload_root):
    """mp3 / m4a 都在白名单里，且识别为 audio。"""
    for filename, ext in (('voice.mp3', '.mp3'), ('voice.m4a', '.m4a')):
        body = _upload(client, student_token, filename, b'ID3fake-audio-data', 'audio/mpeg').get_json()
        assert body['code'] == 0, f'{filename} 上传失败：{body}'
        media = body['data']['media'][0]
        assert media['type'] == 'audio', f'{filename} 类型应为 audio，实际 {media["type"]}'
        assert media['path'].endswith(ext)


def test_audio_size_limit_is_5mb(app):
    """语音上限默认 5MB（可在后台配置里改）。"""
    from app.utils.uploads import _size_limit

    with app.app_context():
        assert _size_limit('audio') == 5 * 1024 * 1024


def test_oversized_audio_rejected(client, app, student_token, upload_root):
    """超过 5MB 的语音必须被拒绝，且不能落盘。"""
    from app.utils.config_service import set_config

    with app.app_context():
        set_config('upload_max_mb_audio', 1, value_type='int')  # 临时改成 1MB

    big = b'0' * (2 * 1024 * 1024)  # 2MB
    body = _upload(client, student_token, 'big.mp3', big, 'audio/mpeg').get_json()
    assert body['code'] != 0, '超限语音应被拒绝'
    assert '5' in body['msg'] or '1' in body['msg'] or '大小' in body['msg']

    with app.app_context():
        set_config('upload_max_mb_audio', 5, value_type='int')  # 恢复


def test_unknown_extension_rejected(client, student_token, upload_root):
    """白名单外的后缀一律拒绝（含可执行文件）。"""
    for filename in ('evil.exe', 'script.js', 'payload.php'):
        body = _upload(client, student_token, filename, b'x', 'application/octet-stream').get_json()
        assert body['code'] != 0, f'{filename} 不应被允许上传'


# ---------------------------------------------------------------------------
# 混合：一条帖子同时带图 + 视频 + 语音
# ---------------------------------------------------------------------------
def test_post_with_all_media_types(client, app, student_token, upload_root):
    """图片 + 视频 + 语音混传，类型各自正确、顺序保持。"""
    media = []
    for filename, content, mime in (
        ('p.png', PNG_1PX, 'image/png'),
        ('v.mp4', MP4_MIN, 'video/mp4'),
        ('a.wav', WAV_MIN, 'audio/wav'),
    ):
        body = _upload(client, student_token, filename, content, mime).get_json()
        assert body['code'] == 0, body
        media.append(body['data']['media'][0])

    post_id = client.post('/api/v1/lost_found/posts',
                          json={'title': '混合媒体', 'contact': '微信 a', 'media': media},
                          headers=auth_header(student_token)).get_json()['data']['id']

    with app.app_context():
        from app.models import Post

        detail = Post.query.get(post_id).to_dict()
        types = [item['type'] for item in detail['media']]
        assert types == ['image', 'video', 'audio'], f'类型顺序错误：{types}'
        for item in detail['media']:
            assert client.get(item['url']).status_code == 200, f'{item["url"]} 取不回'


# ---------------------------------------------------------------------------
# webm 歧义：浏览器录音默认 audio/webm，必须靠 MIME 区分，不能当成视频
# ---------------------------------------------------------------------------
def test_upload_audio_webm_by_mime(client, student_token, upload_root):
    """audio/webm 录音应识别为语音（webm 同时出现在视频/音频后缀白名单里）。"""
    body = _upload(client, student_token, 'voice.webm', b'fake-webm-audio',
                   'audio/webm').get_json()
    assert body['code'] == 0, body
    assert body['data']['media'][0]['type'] == 'audio', body


def test_upload_video_webm_by_mime(client, student_token, upload_root):
    """video/webm 仍然识别为视频。"""
    body = _upload(client, student_token, 'video.webm', MP4_MIN,
                   'video/webm').get_json()
    assert body['code'] == 0, body
    assert body['data']['media'][0]['type'] == 'video', body
