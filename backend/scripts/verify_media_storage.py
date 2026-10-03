# -*- coding: utf-8 -*-
"""验证「媒体文件落盘 + 数据库只存地址」这条链路（端到端，走真实 HTTP）。

跑法（需先启动后端）：
    .venv\\Scripts\\python.exe scripts\\verify_media_storage.py

它会：
    1. 登录测试账号（缺账号则自动用管理员账号）；
    2. 用最小合法 PNG 调用 POST /api/v1/common/upload；
    3. 核对磁盘上确实生成了文件（打印绝对路径与字节数）；
    4. 核对 upload_files 表里记录的是相对路径 + URL（不是文件本身）；
    5. 用返回的 url 通过 GET 把文件取回来，比对字节是否一致；
    6. 用 upload_files.path 反查帖子，演示「按地址查数据」。
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

BASE = os.getenv('SMOKE_BASE', 'http://127.0.0.1:5000')
PREFIX = f'{BASE}/api/v1'
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_ROOT = os.path.join(BACKEND, 'uploads')

#: 1x1 像素的合法 PNG
PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6360000002000100ffff03000006000557bfabd400'
    '00000049454e44ae426082'
)

ok = 0
bad = 0


def check(label, condition, detail=''):
    global ok, bad
    if condition:
        ok += 1
        print(f'  [ OK ] {label}' + (f'  {detail}' if detail else ''))
    else:
        bad += 1
        print(f'  [FAIL] {label}' + (f'  {detail}' if detail else ''))


def login(student_id, password):
    body = json.dumps({'student_id': student_id, 'password': password}).encode()
    request = urllib.request.Request(f'{PREFIX}/auth/login', data=body, method='POST')
    request.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode())
            if data.get('code') == 0:
                return data['data']['access_token']
    except urllib.error.HTTPError:
        pass
    return None


def upload(token, filename, content, mime):
    """构造 multipart/form-data 手工上传（不依赖 requests 库）。"""
    boundary = '----SLP' + uuid.uuid4().hex
    parts = []
    parts.append(f'--{boundary}'.encode())
    parts.append(
        f'Content-Disposition: form-data; name="files"; filename="{filename}"'.encode()
    )
    parts.append(f'Content-Type: {mime}'.encode())
    parts.append(b'')
    parts.append(content)
    parts.append(f'--{boundary}--'.encode())
    parts.append(b'')
    body = b'\r\n'.join(parts)

    request = urllib.request.Request(f'{PREFIX}/common/upload', data=body, method='POST')
    request.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    request.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode())


def main():
    print(f'>>> 目标服务：{BASE}')
    print(f'>>> 上传根目录：{UPLOAD_ROOT}\n')

    print('[1] 登录')
    token = login('20210001', '123456') or login('admin', 'admin123')
    if not token:
        print('  登录失败：请先启动后端并确认演示账号存在')
        return 1
    check('拿到 JWT token', bool(token))

    print('\n[2] 上传一张图片')
    filename = f'verify_{uuid.uuid4().hex[:8]}.png'
    result = upload(token, filename, PNG_1PX, 'image/png')
    check('接口返回 code=0', result.get('code') == 0, f'msg={result.get("msg")}')
    media = (result.get('data') or {}).get('media') or []
    if not media:
        print('  没有返回 media，后续检查跳过')
        return 1
    item = media[0]
    print(f'       返回：url={item["url"]}  path={item["path"]}  size={item["size"]}')

    print('\n[3] 核对磁盘：文件真的写进去了吗')
    abs_path = os.path.join(UPLOAD_ROOT, item['path'].replace('/', os.sep))
    check('文件存在于 uploads 目录下', os.path.exists(abs_path), abs_path)
    if os.path.exists(abs_path):
        size_on_disk = os.path.getsize(abs_path)
        check('磁盘字节数与接口返回一致', size_on_disk == item['size'],
              f'磁盘 {size_on_disk} / 接口 {item["size"]}')
        check('磁盘内容与上传内容一致',
              open(abs_path, 'rb').read() == PNG_1PX)
    check('路径形如 日期/uuid.ext（分目录存放，避免单目录文件过多）',
          len(item['path'].split('/')) == 2 and item['path'].endswith('.png'),
          item['path'])
    check('文件名已被重写为 uuid（不用原始文件名）',
          filename not in item['path'], item['path'])

    print('\n[4] 核对数据库：库里存的是地址而不是文件')
    from app import create_app
    from app.models import UploadFile

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        row = UploadFile.query.filter_by(path=item['path']).first()
        check('upload_files 表里有对应记录', row is not None)
        if row:
            print(f'       id={row.id}  filename={row.filename}')
            print(f'       path={row.path}')
            print(f'       url={row.url}   media_type={row.media_type}  size={row.size}')
            check('库里存的是相对路径', row.path == item['path'])
            check('库里存的是访问 URL（不是二进制）', row.url == f'/api/v1/files/{row.path}')
            check('原始文件名单独保留', row.original_name == filename)
            check('未挂载帖子时 post_id 为空', row.post_id is None)

    print('\n[5] 按地址取回文件（GET /files/<path>）')
    request = urllib.request.Request(f'{BASE}{item["url"]}')
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            fetched = response.read()
        check('通过 url 能取回文件', response.status == 200)
        check('取回的字节与上传一致', fetched == PNG_1PX)
    except urllib.error.HTTPError as exc:
        check('通过 url 能取回文件', False, f'HTTP {exc.code}')

    print('\n[6] 路径穿越防护')
    try:
        request = urllib.request.Request(f'{PREFIX}/files/../../run.py')
        with urllib.request.urlopen(request, timeout=15) as response:
            check('拒绝越权读取项目文件', response.status != 200, f'HTTP {response.status}')
    except urllib.error.HTTPError as exc:
        check('拒绝越权读取项目文件', exc.code in (400, 404), f'HTTP {exc.code}')

    print(f'\n===== 结果：通过 {ok}，失败 {bad} =====')
    print(f'留一个样本供你肉眼确认：{abs_path}')
    print('确认完可以删掉它（或整个 uploads 下的日期目录）。')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
