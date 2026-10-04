# -*- coding: utf-8 -*-
"""数据一致性自检：孤儿指针 + 孤儿文件。

用法（在 backend 目录下）：
    python scripts/check_orphans.py              # 检查并打印报告
    python scripts/check_orphans.py --clean      # 检查后删除孤儿文件（磁盘上无人引用的文件）
    python scripts/check_orphans.py --adopt      # 只报告，不动（默认行为）

「孤儿指针」= 表里的外键指向了已不存在的记录（页面会显示空白或报错）。
「孤儿文件」= 磁盘上有文件，但 upload_files 表里没有任何记录引用它（白占空间）。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.utils.cleanup import (  # noqa: E402
    check_orphans,
    clean_unused_uploads,
    media_orphan_files,
    unattached_upload_files,
)


def human_size(num):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num < 1024:
            return f'{num:.1f} {unit}'
        num /= 1024
    return f'{num:.1f} TB'


def main():
    parser = argparse.ArgumentParser(description='数据一致性自检')
    parser.add_argument('--clean', action='store_true',
                        help='删除孤儿文件，并清理超过保留时间的未提交上传（记录 + 磁盘文件）')
    parser.add_argument('--unattached-hours', type=int, default=24,
                        help='未提交上传的保留小时数，默认 24（配合 --clean 使用）')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        print('=' * 72)
        print('1. 孤儿指针检查（外键是否指向不存在的记录）')
        print('=' * 72)
        problems = check_orphans()
        if not problems:
            print('  ✓ 未发现孤儿指针')
        else:
            for item in problems:
                print(f'  ✗ {item["type"]}：{item["count"]} 条，例如 ID {item["sample"]}')

        print()
        print('=' * 72)
        print('2. 孤儿文件检查（磁盘上有文件但数据库无记录）')
        print('=' * 72)
        orphans = media_orphan_files()
        total = sum(item['size'] for item in orphans)
        if not orphans:
            print('  ✓ 未发现孤儿文件')
        else:
            print(f'  发现 {len(orphans)} 个，合计 {human_size(total)}：')
            for item in orphans[:30]:
                print(f'    {item["path"]}  ({human_size(item["size"])})')
            if len(orphans) > 30:
                print(f'    ...（还有 {len(orphans) - 30} 个）')

            if args.clean:
                root = app.config['UPLOAD_FOLDER']
                removed = 0
                for item in orphans:
                    target = os.path.join(root, *item['path'].split('/'))
                    try:
                        os.remove(target)
                        removed += 1
                    except OSError as exc:
                        print(f'    删除失败 {item["path"]}：{exc}')
                print(f'\n  已删除 {removed} 个孤儿文件，释放 {human_size(total)}')
            else:
                print('\n  提示：加 --clean 可删除这些文件。')

        print()
        print('=' * 72)
        print()
        print('=' * 72)
        print('3. 未提交上传检查（upload_files 无归属且超过保留时间）')
        print('=' * 72)
        unattached = unattached_upload_files(hours=args.unattached_hours)
        unattached_bytes = sum(int(item.size or 0) for item in unattached)
        if not unattached:
            print('  \u2713 未发现超过保留时间的未提交上传')
        else:
            print(f'  发现 {len(unattached)} 条，合计 {human_size(unattached_bytes)}，'
                  f'保留时间 {args.unattached_hours} 小时：')
            for item in unattached[:20]:
                print(f'    {item.path}  ({human_size(item.size or 0)})')
            if len(unattached) > 20:
                print(f'    ...（还有 {len(unattached) - 20} 条）')
            if args.clean:
                stats = clean_unused_uploads(hours=args.unattached_hours)
                print(f'\n  已清理未提交上传 {stats["records"]} 条，删除磁盘文件 {stats["removed_files"]} 个，'
                      f'释放 {human_size(stats["bytes"])}')
            else:
                print('\n  提示：加 --clean 可清理这些未提交上传。')
        orphans_remaining = 0 if args.clean else len(orphans)
        healthy = not problems and orphans_remaining == 0
        print('结论：' + ('数据一致，无孤儿 ✓' if healthy else '存在问题，见上方报告'))
        print('=' * 72)
        return 0 if healthy else 1


if __name__ == '__main__':
    sys.exit(main())
