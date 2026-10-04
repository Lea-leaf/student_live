# -*- coding: utf-8 -*-
"""清理 media JSON 里的多余键（数据卫生）。

背景：`save_media()` 返回值带一个 `user_dir` 调试字段，早期前端把它原样回传，
导致 `posts.media` 的键比 `comments.media` / `messages.media` 多一个，
统一渲染组件时需要额外兼容。

本脚本把 posts / comments / messages 三处 media 数组统一裁剪为：
    id, url, path, name, type, size, mime

用法（在 backend 目录下）：
    python scripts/fix_media_keys.py --check   # 只预演，不修改
    python scripts/fix_media_keys.py           # 执行清理
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Comment, Message, Post  # noqa: E402
from app.utils.uploads import CANONICAL_MEDIA_KEYS, canonical_media_list  # noqa: E402


def _clean_rows(model):
    """返回 (有变化的行数, 移除的键数量, 非法 JSON 行数)。"""
    changed_rows = 0
    removed_keys = 0
    invalid_rows = 0
    for row in model.query.filter(model.media.isnot(None)).order_by(model.id.asc()).all():
        try:
            items = json.loads(row.media) if row.media else []
        except (TypeError, ValueError):
            invalid_rows += 1
            continue
        if not isinstance(items, list):
            invalid_rows += 1
            continue

        canonical = canonical_media_list(items)
        # 统计被丢掉的键（只统计 dict 项）
        for item in items:
            if isinstance(item, dict):
                removed_keys += len([key for key in item if key not in CANONICAL_MEDIA_KEYS])

        if canonical != items:
            changed_rows += 1
            row.media = json.dumps(canonical, ensure_ascii=False) if canonical else None
    return changed_rows, removed_keys, invalid_rows


def main():
    parser = argparse.ArgumentParser(description='裁剪 media JSON 里的多余键')
    parser.add_argument('--check', '--dry-run', dest='check', action='store_true',
                        help='只预演，不修改')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        print('=' * 72)
        print('media JSON 键清理（只保留：%s）' % ', '.join(CANONICAL_MEDIA_KEYS))
        print('模式：' + ('预演（不修改）' if args.check else '执行清理'))
        print('=' * 72)

        total_changed = 0
        total_removed_keys = 0
        total_invalid = 0
        for model in (Post, Comment, Message):
            changed, removed_keys, invalid = _clean_rows(model) if not args.check else _check_rows(model)
            total_changed += changed
            total_removed_keys += removed_keys
            total_invalid += invalid
            print(f'{model.__tablename__}: 需清理 {changed} 行，多余键 {removed_keys} 个'
                  + (f'，无法解析 {invalid} 行' if invalid else ''))

        if not args.check:
            db.session.commit()
            print('\\n已提交修改。')
        print('-' * 72)
        print(f'合计：{total_changed} 行，{total_removed_keys} 个多余键' + (f'，{total_invalid} 行 JSON 异常' if total_invalid else ''))
        if args.check:
            print('这是预演结果；确认无误后去掉 --check 再执行一次。')
        return 0


def _check_rows(model):
    """预演：只统计，不写库。"""
    changed_rows = 0
    removed_keys = 0
    invalid_rows = 0
    for row in model.query.filter(model.media.isnot(None)).order_by(model.id.asc()).all():
        try:
            items = json.loads(row.media) if row.media else []
        except (TypeError, ValueError):
            invalid_rows += 1
            continue
        if not isinstance(items, list):
            invalid_rows += 1
            continue
        canonical = canonical_media_list(items)
        for item in items:
            if isinstance(item, dict):
                removed_keys += len([key for key in item if key not in CANONICAL_MEDIA_KEYS])
        if canonical != items:
            changed_rows += 1
    return changed_rows, removed_keys, invalid_rows


if __name__ == '__main__':
    sys.exit(main())