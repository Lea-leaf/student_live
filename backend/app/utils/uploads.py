# -*- coding: utf-8 -*-
"""文件上传工具（本地磁盘存储）。

需求：图片/视频由客户端本地上传，存服务器。
实现要点：
- 按 `uploads/YYYYMMDD/` 分目录，避免单目录文件过多；
- 文件名用 uuid 重写，杜绝中文名/路径穿越问题；
- 记录到 upload_files 表，便于后续做「未引用文件清理」；
- 大小与类型限制来自配置（可在 system_configs 中由管理员调整）。

扩展点：未来接对象存储（OSS/MinIO）时，只需替换 `_persist()` 的实现，
       URL 规则与表结构都不用动。
"""

import os
import uuid
from datetime import datetime

from flask import current_app, send_from_directory

from .response import CODE_UPLOAD_FAILED, CODE_UPLOAD_TOO_LARGE, CODE_UPLOAD_TYPE_ERROR, error


def _upload_root():
    root = current_app.config['UPLOAD_FOLDER']
    os.makedirs(root, exist_ok=True)
    return root


def allowed_file(filename):
    if '.' not in (filename or ''):
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', set())


def _media_type_of(ext):
    if ext in current_app.config.get('VIDEO_EXTENSIONS', set()):
        return 'video'
    return 'image'


def _size_limit(media_type):
    """按类型取大小上限（字节）。"""
    from .config_service import get_config_int

    key = 'upload_max_mb_video' if media_type == 'video' else 'upload_max_mb_image'
    default = 50 if media_type == 'video' else 10
    mb = get_config_int(key, default)
    return mb * 1024 * 1024


def save_media(file_storage, user_id=None, post_id=None):
    """保存单个上传文件。

    :param file_storage: werkzeug FileStorage
    :return: dict(media 项) 或抛 (error_response)
    """
    from ..extensions import db
    from ..models import UploadFile

    if file_storage is None or not getattr(file_storage, 'filename', ''):
        return None, error('未选择文件', CODE_UPLOAD_FAILED)

    original_name = file_storage.filename
    if not allowed_file(original_name):
        return None, error(
            f'不支持的文件类型，允许：{", ".join(sorted(current_app.config.get("ALLOWED_EXTENSIONS", [])))}',
            CODE_UPLOAD_TYPE_ERROR,
        )

    ext = original_name.rsplit('.', 1)[1].lower()
    media_type = _media_type_of(ext)

    # 读取到内存以便精确控制大小（同时也避免超限文件落盘）
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    limit = _size_limit(media_type)
    if size > limit:
        return None, error(
            f'文件超过大小限制（{limit // 1024 // 1024}MB）', CODE_UPLOAD_TOO_LARGE
        )

    day = datetime.now().strftime('%Y%m%d')
    filename = f'{uuid.uuid4().hex}.{ext}'
    rel_dir = day
    rel_path = f'{rel_dir}/{filename}'
    abs_dir = os.path.join(_upload_root(), rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, filename)
    file_storage.save(abs_path)

    url = f'/api/v1/files/{rel_path}'
    record = UploadFile(
        user_id=user_id,
        filename=filename,
        original_name=original_name[:255],
        path=rel_path,
        url=url,
        mime=file_storage.mimetype,
        media_type=media_type,
        size=size,
        post_id=post_id,
    )
    db.session.add(record)
    db.session.commit()

    return {
        'id': record.id,
        'url': url,
        'path': rel_path,
        'name': original_name,
        'type': media_type,
        'size': size,
        'mime': file_storage.mimetype,
    }, None


def save_media_list(files, user_id=None, post_id=None):
    """批量保存，返回 (media_list, errors)。"""
    media, errors = [], []
    for item in files or []:
        saved, err = save_media(item, user_id=user_id, post_id=post_id)
        if err:
            errors.append(err[0].get_json().get('msg'))
        elif saved:
            media.append(saved)
    return media, errors


def send_upload_file(rel_path):
    """安全地回传上传目录里的文件（阻止路径穿越）。"""
    rel_path = (rel_path or '').replace('\\', '/').lstrip('/')
    if '..' in rel_path.split('/'):
        return error('非法路径', CODE_UPLOAD_FAILED, http_status=400)
    root = _upload_root()
    directory, _, filename = rel_path.rpartition('/')
    target_dir = os.path.join(root, directory) if directory else root
    if not os.path.abspath(target_dir).startswith(os.path.abspath(root)):
        return error('非法路径', CODE_UPLOAD_FAILED, http_status=400)
    if not os.path.exists(os.path.join(target_dir, filename)):
        return error('文件不存在', CODE_UPLOAD_FAILED, http_status=404)
    return send_from_directory(target_dir, filename)


__all__ = ['allowed_file', 'save_media', 'save_media_list', 'send_upload_file']
