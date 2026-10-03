# -*- coding: utf-8 -*-
"""媒体引用维护工具（脚本共用）。

**为什么需要这个模块**

媒体地址在数据库里存了**两处**，任何布局变更都必须同时更新：

1. `upload_files` 表：`path`（相对路径）与 `url`（访问地址）
2. `posts.media` 列：JSON 数组，每项含 `url` / `path` / `name` / `type` / `size`

早期只改第 1 处的迁移脚本导致帖子详情页图片 404（`posts.media` 仍是旧地址）。
现在把「判断旧布局 / 重写引用」的逻辑集中在这里，
`migrate_upload_layout.py` 与 `fix_media_references.py` 共用一份，不会再走偏。
"""

import json
import os
import re

#: 旧布局：`20261002/xxx.png`（两级，首级 8 位日期）
LEGACY_RE = re.compile(r'^\d{8}/[^/]+$')


def is_legacy_path(rel_path):
    """判断相对路径是否为旧的「只有日期」布局。"""
    return bool(LEGACY_RE.match((rel_path or '').replace('\\', '/')))


def to_relative(value, api_prefix='/api/v1'):
    """把 url 或 path 统一转成相对路径。"""
    text = (value or '').replace('\\', '/').lstrip('/')
    marker = f'{api_prefix.strip("/")}/files/'
    if text.startswith(marker):
        return text[len(marker):]
    if text.startswith('files/'):
        return text[len('files/'):]
    return text


def build_url(rel_path, api_prefix='/api/v1'):
    return f'{api_prefix}/files/{rel_path}'


def rewrite_media_json(post, api_prefix='/api/v1', move_files=True, upload_root=None,
                       owner_dir=None):
    """把某条帖子 `media` 里的旧地址改写成新布局。

    这是**幂等**的：已是新布局的条目原样保留。

    :param post: Post 实例
    :param api_prefix: 接口前缀（默认 /api/v1）
    :param move_files: 文件若还在旧位置，是否顺带搬迁
    :param upload_root: 上传根目录（move_files 为真时必需）
    :param owner_dir: 归属目录名（默认取帖子作者的学号；拿不到用 _unknown）
    :return: (是否发生修改, 改写的条目数, 搬迁的文件数)
    """
    from .uploads import safe_segment

    if not post.media:
        return False, 0, 0
    try:
        media = json.loads(post.media)
    except (TypeError, ValueError):
        return False, 0, 0
    if not isinstance(media, list):
        return False, 0, 0

    if owner_dir is None:
        student_id = post.author.student_id if post.author else None
        owner_dir = safe_segment(student_id) if student_id else '_unknown'

    changed = False
    rewritten = 0
    moved = 0

    for item in media:
        if not isinstance(item, dict):
            continue
        rel = to_relative(item.get('url') or item.get('path') or '', api_prefix)
        if not rel or not is_legacy_path(rel):
            continue

        day, _, filename = rel.partition('/')
        new_rel = f'{owner_dir}/{day}/{filename}'

        if move_files and upload_root:
            src = os.path.join(upload_root, *rel.split('/'))
            dst = os.path.join(upload_root, *new_rel.split('/'))
            if os.path.isfile(src) and not os.path.isfile(dst):
                import shutil

                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.move(src, dst)
                    moved += 1
                except OSError:
                    pass

        item['path'] = new_rel
        item['url'] = build_url(new_rel, api_prefix)
        changed = True
        rewritten += 1

    if changed:
        post.media = json.dumps(media, ensure_ascii=False)
    return changed, rewritten, moved


def cleanup_legacy_days(upload_root):
    """删除空的旧日期目录（只删空目录）。"""
    removed = 0
    if not upload_root or not os.path.isdir(upload_root):
        return 0
    for name in sorted(os.listdir(upload_root)):
        day_dir = os.path.join(upload_root, name)
        if os.path.isdir(day_dir) and re.fullmatch(r'\d{8}', name):
            try:
                os.rmdir(day_dir)
                removed += 1
            except OSError:
                pass
    return removed


__all__ = [
    'LEGACY_RE',
    'is_legacy_path',
    'to_relative',
    'build_url',
    'rewrite_media_json',
    'cleanup_legacy_days',
]
