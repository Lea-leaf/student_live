# -*- coding: utf-8 -*-
"""把旧的「日期/文件」上传布局迁移到新的「学号/日期/文件」布局。

背景：
    早期版本把上传文件存成 `uploads/YYYYMMDD/uuid.ext`，硬盘上无法区分归属。
    新布局为 `uploads/<学号>/<YYYYMMDD>/uuid.ext`，本脚本负责搬迁历史文件，
    并同步更新 `upload_files.path` 与 `upload_files.url`。

搬迁依据：
    1. 若 `upload_files` 表里有该文件的记录 → 用它挂载的帖子或上传者的学号；
    2. 若没有记录（历史遗留文件）→ 进入 `uploads/_unknown/<日期>/`，
       避免误挂到别人名下；管理员可人工确认后再处理。

用法（在 backend 目录下）：
    python scripts/migrate_upload_layout.py --check      # 只预演，不改动任何文件
    python scripts/migrate_upload_layout.py             # 执行迁移
    python scripts/migrate_upload_layout.py --dry-run   # 同 --check
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Post, UploadFile, User  # noqa: E402
from app.utils.uploads import safe_segment  # noqa: E402

UNKNOWN_DIR = '_unknown'


def is_legacy_path(rel_path):
    """旧布局形如 `20261002/abc.png`（两级且首级是 8 位日期）。"""
    parts = rel_path.replace('\\', '/').split('/')
    return len(parts) == 2 and len(parts[0]) == 8 and parts[0].isdigit()


def resolve_owner_dir(record):
    """决定文件应归到哪个用户目录下。"""
    if record:
        # 优先看挂载的帖子作者，其次看上传者
        if record.post_id:
            post = Post.query.get(record.post_id)
            if post and post.author and post.author.student_id:
                return safe_segment(post.author.student_id)
        if record.user_id:
            user = User.query.get(record.user_id)
            if user and user.student_id:
                return safe_segment(user.student_id)
    return UNKNOWN_DIR


def main():
    parser = argparse.ArgumentParser(description='迁移上传目录布局到「学号/日期/文件」')
    parser.add_argument('--check', '--dry-run', dest='check', action='store_true',
                        help='只预演，不修改文件与数据库')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        root = app.config['UPLOAD_FOLDER']
        if not os.path.isdir(root):
            print(f'上传目录不存在：{root}')
            return 0

        print(f'上传根目录：{root}')
        print('模式：' + ('预演（不修改）' if args.check else '执行迁移'))
        print('-' * 72)

        moved_files = 0
        moved_records = 0
        skipped = []
        unknown_files = []

        # 遍历旧布局的日期目录
        for day in sorted(os.listdir(root)):
            day_dir = os.path.join(root, day)
            if not os.path.isdir(day_dir) or not (len(day) == 8 and day.isdigit()):
                continue

            for filename in sorted(os.listdir(day_dir)):
                src = os.path.join(day_dir, filename)
                if not os.path.isfile(src):
                    continue

                old_rel = f'{day}/{filename}'
                record = UploadFile.query.filter_by(path=old_rel).first()
                owner = resolve_owner_dir(record)
                new_rel = f'{owner}/{day}/{filename}'
                dst_dir = os.path.join(root, owner, day)
                dst = os.path.join(dst_dir, filename)

                flag = '未知归属' if owner == UNKNOWN_DIR else owner
                print(f'{old_rel}  ->  {new_rel}   [{flag}]')

                if owner == UNKNOWN_DIR:
                    unknown_files.append(old_rel)

                if args.check:
                    moved_files += 1
                    continue

                os.makedirs(dst_dir, exist_ok=True)
                try:
                    shutil.move(src, dst)
                except OSError as exc:
                    skipped.append((old_rel, str(exc)))
                    print(f'    移动失败：{exc}')
                    continue
                moved_files += 1

                if record:
                    record.path = new_rel
                    record.url = f"{app.config.get('API_PREFIX', '/api/v1')}/files/{new_rel}"
                    moved_records += 1

            # 旧日期目录空了就删掉
            if not args.check:
                try:
                    os.rmdir(day_dir)
                except OSError:
                    pass

        if not args.check:
            db.session.commit()

        # ------------------------------------------------------------------
        # 关键补充步骤：同步 posts.media
        # 媒体地址在数据库里存了两处（upload_files 表 + posts.media JSON），
        # 早期版本只改了前者，导致帖子详情页图片 404。这里统一补齐。
        # ------------------------------------------------------------------
        fixed_posts = 0
        fixed_items = 0
        if not args.check:
            from app.utils.media_refs import rewrite_media_json

            for post in Post.query.order_by(Post.id.asc()).all():
                if not post.media:
                    continue
                changed, rewritten, _moved = rewrite_media_json(
                    post, api_prefix=app.config.get('API_PREFIX', '/api/v1'),
                    move_files=False,  # 文件已在上面搬过
                )
                if changed:
                    fixed_posts += 1
                    fixed_items += rewritten
            db.session.commit()

        print('-' * 72)
        print(f'待/已搬迁文件：{moved_files}')
        print(f'更新 upload_files 记录：{moved_records}')
        print(f'同步 posts.media：{fixed_items} 条（涉及 {fixed_posts} 个帖子）')
        if unknown_files:
            print(f'归属不明（放入 {UNKNOWN_DIR}/，需人工确认）：{len(unknown_files)} 个')
        if skipped:
            print(f'失败：{len(skipped)} 个')
        if args.check and moved_files:
            print('\n这是预演结果。确认无误后去掉 --check 再执行一次。')
        return 0


if __name__ == '__main__':
    sys.exit(main())
