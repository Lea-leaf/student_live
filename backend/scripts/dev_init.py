# -*- coding: utf-8 -*-
"""开发辅助脚本：建表 + 初始化模块/配置 + 生成演示数据。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe scripts\\dev_init.py --reset

等价于依次执行：
    flask init-db
    flask seed [--reset]
"""

import argparse
import os
import sys

# 让脚本可以直接运行（把 backend 目录加入模块搜索路径）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Module, default_modules  # noqa: E402
from app.utils.config_service import init_default_configs  # noqa: E402
from app.utils.seed import run_seed  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='初始化校园生活平台开发数据库')
    parser.add_argument('--reset', action='store_true', help='清空业务数据后重新生成演示数据')
    parser.add_argument('--drop', action='store_true', help='先删除所有表（危险，会丢失全部数据）')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        if args.drop:
            db.drop_all()
            print('[1/4] 已删除全部数据表')

        db.create_all()
        print(f'[2/4] 数据表就绪，共 {len(db.metadata.tables)} 张：' +
              ', '.join(sorted(db.metadata.tables.keys())))

        created = 0
        for item in default_modules():
            if not Module.query.filter_by(code=item['code']).first():
                db.session.add(Module(**item))
                created += 1
        db.session.commit()
        print(f'[3/4] 模块初始化完成（新增 {created} 个）')

        print(f'[4/4] 系统配置新增 {init_default_configs()} 项')
        result = run_seed(reset=args.reset)
        print('演示数据生成完成：', result)
        print('\n默认账号：admin / admin123（管理员），20210001 / 123456（学生）')


if __name__ == '__main__':
    main()
