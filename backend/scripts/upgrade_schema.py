# -*- coding: utf-8 -*-
"""结构升级脚本（幂等，可重复执行）。

**为什么需要它**

项目的表结构一直用 `db.create_all()` 建，而 `create_all()` **只会新建缺失的表，
不会给已存在的表加列**。所以「评论/私信加媒体字段、帖子加点赞数」这类改动
必须靠本脚本落地，否则旧库升级后会报 `no such column`。

做法：加列 / 加表前先用 Inspector 检查，存在就跳过。
**只做加法，绝不 DROP 或重建**，因此对已有数据（帖子、图片、评论）零风险。

用法（在 backend 目录下）：
    python scripts/upgrade_schema.py --check   # 只报告将要做什么
    python scripts/upgrade_schema.py           # 执行升级

本次升级内容（对应「结构收口」）：
    1. posts       + like_count                    点赞数（与收藏分开）
    2. comments    + media / root_id / reply_to_user_id / like_count / reply_count
    3. messages    + media / msg_type / sender_deleted / receiver_deleted
    4. upload_files+ owner_type / owner_id         通用关联（评论/私信的媒体不再算孤儿）
    5. post_likes / comment_likes                  两张点赞表
    6. 回填：comments.root_id（顶级评论指向自己）、upload_files.owner_*（按 post_id 推导）

后续升级（对应「审核员与审核指派」，见 docs/USER_FIELDS.md）：
    7. posts       + assignee_id / assigned_by / assigned_at / assignment_expires_at
    8. post_audit_logs                             审核流水表（指派/认领/退回/通过/拒绝）
    9. 两个索引：ix_posts_audit_assignee、ix_post_audit_logs_post_action
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import inspect  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

#: 需要新增的列：{表名: [(列名, 建列 SQL 片段)]}
NEW_COLUMNS = {
    'posts': [
        ('like_count', 'INTEGER NOT NULL DEFAULT 0'),
        # ---- 审核指派（管理员指定审核员；审核员可自助认领）----
        ('assignee_id', 'INTEGER'),
        ('assigned_by', 'INTEGER'),
        ('assigned_at', 'DATETIME'),
        ('assignment_expires_at', 'DATETIME'),
    ],
    'users': [
        # ---- 管理员移交（系统只允许一个管理员，换人走两阶段流程）----
        ('handover_to_id', 'INTEGER'),
        ('handover_at', 'DATETIME'),
        ('handover_effective_at', 'DATETIME'),
        ('handover_freeze_at', 'DATETIME'),
        #: 冻结前的原角色：冻结期按它授权（审核员继续审核），撤销时按它恢复
        ('handover_prev_role', 'VARCHAR(32)'),
    ],
    'comments': [
        ('media', 'TEXT'),
        ('root_id', 'INTEGER'),
        ('reply_to_user_id', 'INTEGER'),
        ('like_count', 'INTEGER NOT NULL DEFAULT 0'),
        ('reply_count', 'INTEGER NOT NULL DEFAULT 0'),
    ],
    'messages': [
        ('media', 'TEXT'),
        ('msg_type', "VARCHAR(16) NOT NULL DEFAULT 'text'"),
        ('sender_deleted', 'BOOLEAN NOT NULL DEFAULT 0'),
        ('receiver_deleted', 'BOOLEAN NOT NULL DEFAULT 0'),
    ],
    'upload_files': [
        ('owner_type', 'VARCHAR(16)'),
        ('owner_id', 'INTEGER'),
    ],
}

#: 需要新增的表（由 db.create_all() 建，这里只负责报告与计数）
NEW_TABLES = ('post_likes', 'comment_likes', 'post_audit_logs')

#: 需要新增的索引：[表名, 索引名, 列]
NEW_INDEXES = [
    ('comments', 'ix_comments_root_id', 'root_id'),
    ('comments', 'ix_comments_parent_id', 'parent_id'),
    ('comments', 'ix_comments_reply_to_user_id', 'reply_to_user_id'),
    ('messages', 'ix_messages_msg_type', 'msg_type'),
    ('upload_files', 'ix_upload_files_owner_type', 'owner_type'),
    ('upload_files', 'ix_upload_files_owner_id', 'owner_id'),
    ('upload_files', 'ix_upload_owner', 'owner_type, owner_id'),
    # ---- 审核指派 ----
    # 注意：posts.assignee_id / assignment_expires_at 与 post_audit_logs 的单列索引
    # 由模型里的 index=True 在 db.create_all() 时自动建立，这里只列模型未声明的复合索引。
    ('posts', 'ix_posts_audit_assignee', 'audit_status, assignee_id'),
    ('post_audit_logs', 'ix_post_audit_logs_post_action', 'post_id, action'),
]

def table_names():
    return set(inspect(db.engine).get_table_names())


def column_names(table):
    return {col['name'] for col in inspect(db.engine).get_columns(table)}


def index_names(table):
    return {idx['name'] for idx in inspect(db.engine).get_indexes(table)}


def main():
    parser = argparse.ArgumentParser(description='结构升级（幂等，只加不删）')
    parser.add_argument('--check', '--dry-run', dest='check', action='store_true',
                        help='只报告，不执行')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        print(f"数据库：{db.engine.url.render_as_string(hide_password=True)}")
        print('模式：' + ('检查（不修改）' if args.check else '执行升级'))
        print('-' * 72)

        existing_tables = table_names()
        added_columns = 0
        added_indexes = 0
        added_tables = 0

        # ---- 1. 补列 ----
        print('[1] 补齐缺失的列')
        for table, columns in NEW_COLUMNS.items():
            if table not in existing_tables:
                print(f'    {table}: 表不存在，将由 db.create_all 新建，跳过')
                continue
            current = column_names(table)
            for name, ddl in columns:
                if name in current:
                    print(f'    {table}.{name}: 已存在，跳过')
                    continue
                sql = f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'
                print(f'    {table}.{name}: 新增  <- {ddl}')
                if not args.check:
                    db.session.execute(db.text(sql))
                    db.session.commit()
                added_columns += 1

        # ---- 2. 建缺失的表（点赞表、审核流水表）----
        print('[2] 新建缺失的表（点赞表 / 审核流水表）')
        expected = set(NEW_TABLES)
        missing = expected - existing_tables
        if missing:
            for name in sorted(missing):
                print(f'    {name}: 将新建')
            if not args.check:
                db.create_all()  # 只建缺失的表，已存在的表不受影响
            added_tables = len(missing)
        else:
            print('    ' + ' / '.join(sorted(expected)) + ': 已存在，跳过')

        # ---- 3. 补索引 ----
        print('[3] 补齐缺失的索引')
        existing_tables = table_names()
        for table, index_name, columns in NEW_INDEXES:
            if table not in existing_tables:
                continue
            if index_name in index_names(table):
                print(f'    {index_name}: 已存在，跳过')
                continue
            sql = f'CREATE INDEX {index_name} ON {table} ({columns})'
            print(f'    {index_name}: 新增  <- ({columns})')
            if not args.check:
                try:
                    db.session.execute(db.text(sql))
                    db.session.commit()
                    added_indexes += 1
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    print(f'      跳过（{exc}）')
            else:
                added_indexes += 1

        # ---- 4. 回填历史数据 ----
        # 注意：这里**不能**用 ORM 查询。模型已经声明了新列，而列可能刚刚才加上，
        # 在 --check 模式下（没执行 ALTER）ORM 会拼出引用不存在列的 SQL 而报错。
        # 因此统一用原生 SQL，且用 try 兜底，保证预检永远不炸。
        print('[4] 回填历史数据')
        backfills = [
            ('comments.root_id（顶级评论指向自己）',
             'UPDATE comments SET root_id = id WHERE parent_id IS NULL AND root_id IS NULL',
             'SELECT COUNT(*) FROM comments WHERE parent_id IS NULL AND root_id IS NULL'),
            ('upload_files.owner_*（按 post_id 推导）',
             "UPDATE upload_files SET owner_type = 'post', owner_id = post_id "
             'WHERE post_id IS NOT NULL AND owner_type IS NULL',
             'SELECT COUNT(*) FROM upload_files WHERE post_id IS NOT NULL AND owner_type IS NULL'),
        ]
        for label, update_sql, count_sql in backfills:
            if args.check:
                try:
                    pending = db.session.execute(db.text(count_sql)).scalar() or 0
                    print(f'    {label}：待回填 {pending} 条')
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    print(f'    {label}：列尚未创建，执行升级后再回填（{type(exc).__name__}）')
                continue
            try:
                result = db.session.execute(db.text(update_sql))
                db.session.commit()
                print(f'    {label}：回填 {result.rowcount} 条')
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                print(f'    {label}：跳过（{exc}）')

        print('-' * 72)
        print(f'新增列：{added_columns}　新增表：{added_tables}　新增索引：{added_indexes}')
        if args.check:
            print('\n这是检查结果。确认后去掉 --check 再执行。')
        else:
            print('\n升级完成。业务数据未受影响（只做加法）。')
        return 0


if __name__ == '__main__':
    sys.exit(main())
