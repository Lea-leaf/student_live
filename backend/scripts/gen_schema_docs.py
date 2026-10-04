# -*- coding: utf-8 -*-
"""从 SQLAlchemy 模型生成「建表 SQL」与「ER 图（Mermaid）」。

为什么要脚本生成：表结构是模型定义的唯一权威来源，
手写 SQL 容易和代码漂移。改动模型后重新执行本脚本即可同步文档。

用法（在 backend 目录下）：
    python scripts/gen_schema_docs.py

输出：
    docs/schema_mysql.sql      MySQL 建表语句（部署用）
    docs/schema_sqlite.sql     SQLite 建表语句（开发用）
    docs/ER.md                 ER 图（Mermaid erDiagram）
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402
from sqlalchemy.dialects import mysql, sqlite  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'docs'))

#: 表注释（SQLite 不支持 COMMENT，写进文档里补充说明）
TABLE_COMMENTS = {
    'users': '用户（普通用户 / 内容审核员 / 管理员）',
    'posts': '帖子（所有模块统一存储，type 区分模块；含审核指派字段）',
    'post_audit_logs': '审核流水（指派 / 认领 / 退回 / 通过 / 拒绝）',
    'modules': '功能模块定义（可后台启停 / 排序 / 新增）',
    'comments': '帖子评论',
    'messages': '站内私信',
    'favorites': '收藏',
    'post_likes': '帖子点赞',
    'comment_likes': '评论点赞',
    'reports': '举报',
    'notifications': '站内通知',
    'operation_logs': '操作日志',
    'login_logs': '登录日志',
    'system_configs': '系统配置（键值对）',
    'upload_files': '上传文件记录',
    'admin_module_access': '管理员-模块授权（RBAC 预留，未启用）',
}


def render(dialect, engine_kind):
    """按指定方言渲染所有表的建表语句与索引。

    MySQL 方言的两个小修正（SQLAlchemy 生成顺序对 MySQL 不友好）：
    1. AUTO_INCREMENT 必须写在 COMMENT 之前；
    2. BOOL 统一成 TINYINT(1)，兼容 MySQL 5.7。
    """
    import re

    lines = []
    for table in db.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        comment = TABLE_COMMENTS.get(table.name)
        if engine_kind == 'mysql':
            ddl = re.sub(
                r"COMMENT ('(?:[^']|'')*')\s+AUTO_INCREMENT",
                r'AUTO_INCREMENT COMMENT \1',
                ddl,
            )
            ddl = re.sub(r'\bBOOL\b', 'TINYINT(1)', ddl)
            ddl = ddl.rstrip(')').rstrip() + (
                f"\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='{comment}';"
                if comment else '\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;'
            )
        else:
            ddl = ddl.rstrip() + ';'
            if comment:
                ddl = f'-- {comment}\n{ddl}'
        lines.append(ddl)
        for index in table.indexes:
            lines.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ';')
    return '\n\n'.join(lines)


def er_diagram():
    """生成 Mermaid ER 图。"""
    lines = ['erDiagram']
    for table in db.metadata.sorted_tables:
        pk = [c.name for c in table.columns if c.primary_key]
        lines.append(f'    %% {TABLE_COMMENTS.get(table.name, table.name)}')
        lines.append(f'    {table.name} {{')
        for column in table.columns:
            col_type = str(column.type).split('(')[0].replace(' ', '_')
            marks = []
            if column.name in pk:
                marks.append('PK')
            for fk in table.foreign_keys:
                if fk.parent.name == column.name:
                    marks.append('FK')
            suffix = (' ' + ' '.join(marks)) if marks else ''
            nullable = 'null' if column.nullable else 'not_null'
            lines.append(f'        {col_type} {column.name} {nullable}{suffix}')
        lines.append('    }')

    # 关系（依据外键自动推导）
    lines.append('')
    lines.append('    %% 关系')
    for table in db.metadata.sorted_tables:
        for fk in table.foreign_keys:
            target = fk.column.table.name
            lines.append(
                f'    {target} ||--o{{ {table.name} : "{fk.parent.name} → {fk.column.name}"'
            )
    return '\n'.join(lines)


def main():
    app = create_app('development')
    os.makedirs(DOCS_DIR, exist_ok=True)

    with app.app_context():
        header_mysql = (
            '-- ============================================================================\n'
            '-- 校园生活平台 - MySQL 建表脚本（部署环境）\n'
            '-- 由 backend/scripts/gen_schema_docs.py 依据 SQLAlchemy 模型自动生成\n'
            '-- 数据库：school_life，字符集：utf8mb4\n'
            '-- 执行：mysql -uroot -p < docs/schema_mysql.sql\n'
            '-- ============================================================================\n\n'
            'CREATE DATABASE IF NOT EXISTS `school_life` DEFAULT CHARACTER SET utf8mb4 '
            'COLLATE utf8mb4_general_ci;\n'
            'USE `school_life`;\n\n'
            'SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS = 0;\n\n'
        )
        header_sqlite = (
            '-- ============================================================================\n'
            '-- 校园生活平台 - SQLite 建表脚本（开发环境，与 flask db upgrade 等价）\n'
            '-- 由 backend/scripts/gen_schema_docs.py 自动生成\n'
            '-- ============================================================================\n\n'
        )
        footer = '\n\nSET FOREIGN_KEY_CHECKS = 1;\n'

        mysql_sql = header_mysql + render(mysql.dialect(), 'mysql') + footer
        sqlite_sql = header_sqlite + render(sqlite.dialect(), 'sqlite') + '\n'

        with open(os.path.join(DOCS_DIR, 'schema_mysql.sql'), 'w', encoding='utf-8') as handle:
            handle.write(mysql_sql)
        with open(os.path.join(DOCS_DIR, 'schema_sqlite.sql'), 'w', encoding='utf-8') as handle:
            handle.write(sqlite_sql)

        er = (
            '# 数据库 ER 图\n\n'
            '> 本文件由 `backend/scripts/gen_schema_docs.py` 从模型自动生成，改模型后重新执行即可同步。\n'
            '> 在支持 Mermaid 的编辑器（VS Code / Typora / Gitee / GitHub）中可直接渲染。\n\n'
            '```mermaid\n' + er_diagram() + '\n```\n\n'
            '## 表清单\n\n'
            '| 表名 | 说明 | 字段数 |\n|---|---|---|\n'
        )
        for table in db.metadata.sorted_tables:
            er += f'| `{table.name}` | {TABLE_COMMENTS.get(table.name, "")} | {len(table.columns)} |\n'
        with open(os.path.join(DOCS_DIR, 'ER.md'), 'w', encoding='utf-8') as handle:
            handle.write(er)

    print('已生成：')
    print('  docs/schema_mysql.sql')
    print('  docs/schema_sqlite.sql')
    print('  docs/ER.md')


if __name__ == '__main__':
    main()
