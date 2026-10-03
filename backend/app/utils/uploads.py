# -*- coding: utf-8 -*-
"""文件上传工具（本地磁盘存储）。

**目录结构（按用户归属分类）**：

    uploads/
    └── <学号>/                     ← 一级：用户归属，管理员在硬盘上就能认出是谁的
        └── <YYYYMMDD>/             ← 二级：上传日期，避免单目录文件过多
            └── <uuid>.<ext>        ← 文件名用 uuid 重写，杜绝中文名与路径穿越

例如：`uploads/20210001/20261002/9f3c1a2b....png`

这样组织的原因（需求明确要求）：
- 只按日期分目录时，硬盘上无法区分文件属于哪个用户；
- 按用户分目录后，删除用户可以直接整目录删除，不会误删他人文件；
- 日期作为二级目录，既保留时间维度，又避免单个用户目录文件过多。

**数据库只存相对路径**：`upload_files.path = "20210001/20261002/xxx.png"`，
加上 `url = "/api/v1/files/20210001/20261002/xxx.png"` 供前端直接引用。
换存储根目录（甚至换机器）时数据库不用改。

**清理**：`delete_media_by_paths()` / `delete_user_upload_dir()` 负责删除磁盘文件；
删帖与删用户时必须调用，否则会留下孤儿文件。

扩展点：未来接对象存储（OSS/MinIO）时，只需替换落盘与删除两个函数，
相对路径规则、URL 规则与表结构都不用动。
"""

import os
import re
import shutil
import uuid
from datetime import datetime

from flask import current_app, send_from_directory

from .response import CODE_UPLOAD_FAILED, CODE_UPLOAD_TOO_LARGE, CODE_UPLOAD_TYPE_ERROR, error

#: 目录名白名单：字母、数字、下划线、中日韩文字、连字符
_SAFE_SEGMENT = re.compile(r'^[\w\u4e00-\u9fff-]{1,64}$', re.UNICODE)
#: 兜底用户目录前缀（理论上不会用到：本平台用户都有学号）
FALLBACK_USER_DIR = 'u'


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
def _upload_root():
    """上传根目录（不存在则创建）。"""
    root = current_app.config['UPLOAD_FOLDER']
    os.makedirs(root, exist_ok=True)
    return root


def allowed_file(filename):
    if '.' not in (filename or ''):
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', set())


def media_type_of(ext, mime=None):
    """判断媒体类型：image / video / audio。

    后缀优先，但 **mime 优先于后缀中的歧义项**：
    `webm` 既可能是视频也可能是语音（浏览器录音默认 audio/webm），
    单看后缀无法区分，因此 mime 明确是 audio/* 时按语音处理；
    反之 video/webm 仍是视频。
    """
    ext = (ext or '').lower()
    mime = (mime or '').lower()
    if mime.startswith('audio/'):
        return 'audio'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('image/'):
        return 'image'
    if ext in current_app.config.get('VIDEO_EXTENSIONS', set()):
        return 'video'
    if ext in current_app.config.get('AUDIO_EXTENSIONS', set()):
        return 'audio'
    return 'image'


#: 兼容旧调用名（内部与脚本可能引用）
_media_type_of = media_type_of


def _size_limit(media_type):
    """按类型取大小上限（字节）。图片 10MB / 视频 50MB / 语音 5MB，均可在后台配置。"""
    from .config_service import get_config_int

    limits = {
        'video': ('upload_max_mb_video', 50),
        'audio': ('upload_max_mb_audio', 5),
        'image': ('upload_max_mb_image', 10),
    }
    key, default = limits.get(media_type, limits['image'])
    return get_config_int(key, default) * 1024 * 1024


# ---------------------------------------------------------------------------
# 路径与目录名
# ---------------------------------------------------------------------------
def safe_segment(value, fallback='unknown'):
    """把任意值转成安全的单级目录名。

    过滤掉路径分隔符、`..`、控制字符等，避免路径穿越；
    目录名非法时回落到 fallback（而不是报错中断上传）。
    """
    text = str(value or '').strip()
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', text).strip('. ')
    if not text:
        return fallback
    if not _SAFE_SEGMENT.match(text):
        # 含不支持的字符：只保留字母数字与下划线
        cleaned = re.sub(r'[^\w\u4e00-\u9fff-]', '_', text)[:64]
        return cleaned or fallback
    return text[:64]


def user_dir_name(user=None, user_id=None):
    """用户目录名 —— 优先学号，拿不到时回落到 `u<id>`。

    :param user: User 实例（推荐传，就能用上学号）
    :param user_id: 只有 ID 时的兜底
    """
    student_id = getattr(user, 'student_id', None)
    if student_id:
        return safe_segment(student_id, fallback=f'{FALLBACK_USER_DIR}{getattr(user, "id", "")}')
    uid = getattr(user, 'id', None) or user_id
    return f'{FALLBACK_USER_DIR}{uid}' if uid else 'anonymous'


def user_upload_dir(user=None, user_id=None):
    """返回某用户的绝对上传目录（不创建）。"""
    return os.path.join(_upload_root(), user_dir_name(user, user_id))


def build_relative_path(user=None, user_id=None, ext='jpg', when=None):
    """构造相对路径：`<学号>/<YYYYMMDD>/<uuid>.<ext>`。"""
    day = (when or datetime.now()).strftime('%Y%m%d')
    filename = f'{uuid.uuid4().hex}.{ext}'
    rel_dir = f'{user_dir_name(user, user_id)}/{day}'
    return rel_dir, filename, f'{rel_dir}/{filename}'


def _abs_path_of(rel_path):
    """相对路径 → 绝对路径，并确保仍在 uploads 根目录内（防穿越）。"""
    rel_path = (rel_path or '').replace('\\', '/').lstrip('/')
    if not rel_path or '..' in rel_path.split('/'):
        return None
    root = os.path.abspath(_upload_root())
    target = os.path.abspath(os.path.join(root, *rel_path.split('/')))
    if target != root and not target.startswith(root + os.sep):
        return None
    return target


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------
def save_media(file_storage, user=None, user_id=None, post_id=None):
    """保存单个上传文件到 `uploads/<学号>/<日期>/<uuid>.<ext>`。

    :param file_storage: werkzeug FileStorage
    :param user: User 实例（用于确定用户目录；推荐传）
    :param user_id: 仅用户 ID（拿不到学号时的兜底）
    :return: (media_dict, error_response)
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
    media_type = _media_type_of(ext, file_storage.mimetype)

    # 读取到内存以便精确控制大小（同时也避免超限文件落盘）
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    limit = _size_limit(media_type)
    if size > limit:
        return None, error(
            f'文件超过大小限制（{limit // 1024 // 1024}MB）', CODE_UPLOAD_TOO_LARGE
        )

    rel_dir, filename, rel_path = build_relative_path(user, user_id, ext)
    abs_dir = os.path.join(_upload_root(), *rel_dir.split('/'))
    os.makedirs(abs_dir, exist_ok=True)
    file_storage.save(os.path.join(abs_dir, filename))

    prefix = current_app.config.get('API_PREFIX', '/api/v1')
    url = f'{prefix}/files/{rel_path}'
    record = UploadFile(
        user_id=getattr(user, 'id', None) or user_id,
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
        'user_dir': user_dir_name(user, user_id),
    }, None


def save_media_list(files, user=None, user_id=None, post_id=None):
    """批量保存，返回 (media_list, errors)。"""
    media, errors = [], []
    for item in files or []:
        saved, err = save_media(item, user=user, user_id=user_id, post_id=post_id)
        if err:
            errors.append(err[0].get_json().get('msg'))
        elif saved:
            media.append(saved)
    return media, errors


def _relative_from_media_item(item):
    """从已上传文件的 [{url,path}] 结构中提取相对路径（供二次校验用）。"""
    prefix = current_app.config.get('API_PREFIX', '/api/v1').rstrip('/') + '/files/'
    url = str(item.get('url') or '').replace('\\', '/').lstrip('/')
    path = str(item.get('path') or '').replace('\\', '/').lstrip('/')
    if path:
        return path
    if url.startswith(prefix):
        return url[len(prefix):]
    if url.startswith('files/'):
        return url[len('files/'):]
    return ''


def sanitize_media_list(items, user=None, allowed_types=('image', 'video', 'audio'), max_count=9):
    """校验业务提交的 media 数组，只允许引用当前用户真正上传过的文件。

    :param items: [{id,url,path,type,...}]，通常来自 /common/upload 的返回
    :param user: 当前用户；非空时必须与上传记录归属一致，防止盗用他人文件
    :return: (规整后的 media 列表, 错误信息)，错误信息为 None 表示通过
    """
    from ..models import UploadFile

    if items in (None, '', []):
        return [], None
    if not isinstance(items, list):
        return None, '媒体列表格式不正确'
    if len(items) > max_count:
        return None, f'最多只能上传 {max_count} 个媒体文件'

    allowed = set(allowed_types or ())
    cleaned = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            return None, '媒体列表格式不正确'

        record = None
        raw_id = item.get('id')
        if raw_id not in (None, '', 0):
            try:
                record = UploadFile.query.get(int(raw_id))
            except (TypeError, ValueError):
                record = None
        if record is None:
            rel_path = _relative_from_media_item(item)
            if rel_path:
                record = UploadFile.query.filter_by(path=rel_path).first()
        if record is None:
            return None, '媒体文件不存在，请重新上传后再提交'

        user_id = getattr(user, 'id', None)
        if user_id and record.user_id not in (None, user_id):
            return None, '不能引用他人上传的媒体文件'

        item_type = (record.media_type or item.get('type') or '').lower()
        if item_type not in allowed:
            return None, f'不支持 {item_type or "未知"} 类型的媒体'
        if record.id in seen:
            continue
        seen.add(record.id)
        cleaned.append({
            'id': record.id,
            'url': record.url,
            'path': record.path,
            'name': record.original_name,
            'type': item_type,
            'size': record.size,
            'mime': record.mime,
        })
    return cleaned, None


def attach_upload_owners(media, owner_type, owner_id):
    """把 media 里的上传记录挂到评论 / 私信等业务对象上（防止被当成孤儿文件）。"""
    from ..models import UploadFile

    count = 0
    for item in media or []:
        if not isinstance(item, dict):
            continue
        record = None
        raw_id = item.get('id')
        if raw_id not in (None, '', 0):
            try:
                record = UploadFile.query.get(int(raw_id))
            except (TypeError, ValueError):
                record = None
        if record is None:
            rel_path = _relative_from_media_item(item)
            if rel_path:
                record = UploadFile.query.filter_by(path=rel_path).first()
        if record is None:
            continue
        record.attach_to(owner_type, owner_id)
        if owner_type == 'post':
            record.post_id = owner_id
        count += 1
    return count


# ---------------------------------------------------------------------------
# 访问
# ---------------------------------------------------------------------------
def send_upload_file(rel_path):
    """安全地回传上传目录里的文件（阻止路径穿越）。"""
    abs_path = _abs_path_of(rel_path)
    if abs_path is None:
        return error('非法路径', CODE_UPLOAD_FAILED, http_status=400)
    if not os.path.isfile(abs_path):
        return error('文件不存在', CODE_UPLOAD_FAILED, http_status=404)
    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))


# ---------------------------------------------------------------------------
# 删除（防孤儿文件）
# ---------------------------------------------------------------------------
def delete_media_by_paths(rel_paths):
    """按相对路径删除磁盘文件，并顺带清理空目录。

    :return: 实际删除的文件数
    """
    removed = 0
    touched_dirs = set()
    for rel_path in rel_paths or []:
        abs_path = _abs_path_of(rel_path)
        if not abs_path or not os.path.isfile(abs_path):
            continue
        try:
            os.remove(abs_path)
            removed += 1
            touched_dirs.add(os.path.dirname(abs_path))
        except OSError as exc:
            if current_app:
                current_app.logger.warning('删除文件失败 %s：%s', abs_path, exc)

    # 自下而上清理空目录（只删空目录，不递归删非空目录）
    root = os.path.abspath(_upload_root())
    for directory in sorted(touched_dirs, key=len, reverse=True):
        current = directory
        while current != root and current.startswith(root + os.sep):
            try:
                os.rmdir(current)  # 非空会抛 OSError，正好跳过
            except OSError:
                break
            current = os.path.dirname(current)
    return removed


def delete_user_upload_dir(user=None, user_id=None, student_id=None):
    """整目录删除某用户的上传文件（删用户时调用）。

    目录名优先取学号（与落盘规则一致）：`student_id` > `user.student_id` > `u<id>`。

    :return: (删除的文件数, 目录路径)
    """
    if student_id:
        dir_name = safe_segment(student_id, fallback=f'{FALLBACK_USER_DIR}{getattr(user, "id", "") or user_id}')
    else:
        dir_name = user_dir_name(user, user_id)

    root = os.path.abspath(_upload_root())
    target = os.path.abspath(os.path.join(root, dir_name))

    # 安全检查：只允许删除 uploads 根目录下的子目录，绝不接受根目录本身
    if target == root or not target.startswith(root + os.sep):
        if current_app:
            current_app.logger.error('拒绝删除非法目录：%s', target)
        return 0, target

    if not os.path.isdir(target):
        return 0, target

    count = sum(len(files) for _, _, files in os.walk(target))
    try:
        shutil.rmtree(target)
    except OSError as exc:
        if current_app:
            current_app.logger.warning('删除用户上传目录失败 %s：%s', target, exc)
        return 0, target
    return count, target


def media_stats(directory=None):
    """统计上传目录的用量（管理端展示用）。"""
    root = _upload_root()
    target = os.path.abspath(directory) if directory else os.path.abspath(root)
    if target != os.path.abspath(root) and not target.startswith(os.path.abspath(root) + os.sep):
        return {'files': 0, 'bytes': 0, 'dirs': []}

    total_files, total_bytes = 0, 0
    per_user = []
    if os.path.isdir(target):
        for name in sorted(os.listdir(target)):
            sub = os.path.join(target, name)
            if not os.path.isdir(sub):
                continue
            files = size = 0
            for dirpath, _dirnames, filenames in os.walk(sub):
                for filename in filenames:
                    files += 1
                    try:
                        size += os.path.getsize(os.path.join(dirpath, filename))
                    except OSError:
                        pass
            per_user.append({'dir': name, 'files': files, 'bytes': size})
            total_files += files
            total_bytes += size
    return {'files': total_files, 'bytes': total_bytes, 'dirs': per_user}


__all__ = [
    'allowed_file',
    'safe_segment',
    'user_dir_name',
    'user_upload_dir',
    'build_relative_path',
    'save_media',
    'save_media_list',
    'sanitize_media_list',
    'attach_upload_owners',
    'send_upload_file',
    'delete_media_by_paths',
    'delete_user_upload_dir',
    'media_stats',
]
