# -*- coding: utf-8 -*-
"""修复媒体文件引用：把 `posts.media` 里的旧路径改成新的「学号/日期」路径。

**为什么需要它（真实踩坑）**

媒体地址在数据库里存了**两处**：
    1. `upload_files.path` / `upload_files.url`
    2. `posts.media`（JSON 数组，含 url / path / name / type / size）

`migrate_upload_layout.py` 的早期版本只改了第 1 处，导致 `posts.media` 里仍是
`/api/v1/files/20261002/xxx.png` 这类旧地址，帖子详情页加载图片报 **404**。

本脚本专门修第 2 处；判断与重写逻辑在 `app/utils/media_refs.py`，与迁移脚本共用。

用法（在 backend 目录下）：
    python scripts/fix_media_references.py --check    # 只预演
    python scripts/fix_media_references.py            # 执行修复
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Post, UploadFile  # noqa: E402
from app.utils.media_refs import (  # noqa: E402
    build_url,
    cleanup_legacy_days,
    is_legacy_path,
    rewrite_media_json,
    to_relative,
)


def main():
    parser = argparse.ArgumentParser(description='修复 posts.media 里的媒体路径引用')
    parser.add_argument('--check', '--dry-run', dest='check', action='store_true',
                        help='只预演，不修改')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        root = app.config['UPLOAD_FOLDER']
        api_prefix = app.config.get('API_PREFIX', '/api/v1')

        print(f'上传根目录：{root}')
        print('模式：' + ('预演（不修改）' if args.check else '执行修复'))
        print('-' * 72)

        fixed_posts = 0
        fixed_items = 0
        moved_files = 0
        fixed_records = 0

        for post in Post.query.order_by(Post.id.asc()).all():
            if not post.media:
                continue

            if args.check:
                # 预演：只统计，不改数据
                import json

                try:
                    media = json.loads(post.media)
                except (TypeError, ValueError):
                    continue
                stale = [item for item in media
                         if isinstance(item, dict)
                         and is_legacy_path(to_relative(item.get('url') or item.get('path') or '',
                                                        api_prefix))]
                if stale:
                    print(f'帖子 {post.id}：{len(stale)} 条旧地址，例如 {stale[0].get("path")}')
                    fixed_posts += 1
                    fixed_items += len(stale)
                continue

            changed, rewritten, moved = rewrite_media_json(
                post, api_prefix=api_prefix, move_files=True, upload_root=root
            )
            if changed:
                fixed_posts += 1
                fixed_items += rewritten
                moved_files += moved
                print(f'帖子 {post.id}：改写 {rewritten} 条地址')

                # 同步 upload_files（幂等）
                import json

                for item in json.loads(post.media):
                    if not isinstance(item, dict) or not item.get('path'):
                        continue
                    record = UploadFile.query.filter_by(id=item.get('id')).first()
                    if record is None:
                        record = UploadFile.query.filter_by(post_id=post.id).first()
                    if record and (record.path != item['path'] or record.url != item.get('url')):
                        record.path = item['path']
                        record.url = item.get('url') or build_url(item['path'], api_prefix)
                        fixed_records += 1

        if not args.check:
            db.session.commit()
            removed = cleanup_legacy_days(root)
            if removed:
                print(f'清理空日期目录：{removed} 个')

        print('-' * 72)
        print(f'需/已修复的媒体条目：{fixed_items}')
        print(f'涉及帖子：{fixed_posts}')
        print(f'搬迁文件：{moved_files}')
        print(f'同步 upload_files 记录：{fixed_records}')
        if args.check and fixed_items:
            print('\n这是预演结果。确认无误后去掉 --check 再执行一次。')
        if not fixed_items:
            print('\n所有媒体地址都已是新布局，无需修复 ✓')
        return 0


if __name__ == '__main__':
    sys.exit(main())
