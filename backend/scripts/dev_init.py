# -*- coding: utf-8 -*-
"""开发辅助脚本：建表 + 初始化模块/配置 + 生成演示数据。

用法（在 backend 目录下）：
    python scripts/dev_init.py            # 幂等：已有数据则跳过种子，不会重复插入
    python scripts/dev_init.py --seed     # 强制重新生成演示数据（业务表原样保留时可能冲突，建议配 --reset）
    python scripts/dev_init.py --reset    # 先清空业务数据，再重新生成
    python scripts/dev_init.py --drop     # 先删除所有表（危险）

等价于依次执行：
    flask init-db
    flask seed [--reset]

设计要点：默认路径必须「可重复执行且不报错」，
因为它会被 start-dev.ps1 在每次启动时调用。
"""

import argparse
import os
import sys

# 让脚本可以直接运行（把 backend 目录加入模块搜索路径）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Module, User, default_modules  # noqa: E402
from app.utils.config_service import init_default_configs  # noqa: E402
from app.utils.seed import run_seed  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='初始化校园生活平台开发数据库')
    parser.add_argument('--reset', action='store_true', help='清空业务数据后重新生成演示数据')
    parser.add_argument('--drop', action='store_true', help='先删除所有表（危险，会丢失全部数据）')
    parser.add_argument('--seed', dest='seed', action='store_true', default=None,
                        help='强制生成演示数据（默认：库为空时才生成）')
    parser.add_argument('--no-seed', dest='seed', action='store_false',
                        help='只建表与初始化模块/配置，不生成演示数据')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        if args.drop:
            db.drop_all()
            print('[1/5] 已删除全部数据表')

        db.create_all()
        print(f'[2/5] 数据表就绪，共 {len(db.metadata.tables)} 张：' +
              ', '.join(sorted(db.metadata.tables.keys())))

        # ---- 模块：缺失才补，不覆盖管理员在后台改过的排序/启停状态 ----
        created = 0
        for item in default_modules():
            if not Module.query.filter_by(code=item['code']).first():
                db.session.add(Module(**item))
                created += 1
        db.session.commit()
        print(f'[3/5] 模块初始化完成（新增 {created} 个，已存在的不覆盖）')

        # ---- 系统配置：只补缺失键，不覆盖管理员改过的值 ----
        print(f'[4/5] 系统配置补齐 {init_default_configs()} 项（已存在的不覆盖）')

        # ---- 演示数据 ----
        # 默认策略：库为空才生成，保证脚本可重复执行而不报错。
        # --reset 的语义是"清空重建"，因此隐含 --seed（除非显式 --no-seed）。
        if args.seed is not None:
            should_seed = args.seed
        elif args.reset:
            should_seed = True
        else:
            should_seed = User.query.count() == 0

        if should_seed:
            result = run_seed(reset=args.reset)
            if result.get('skipped'):
                print(f'[5/5] 演示数据未生成：{result.get("reason")}')
            else:
                print('[5/5] 演示数据生成完成：', result)
        else:
            print('[5/5] 已存在用户数据，跳过演示数据生成（如需清空重建：--reset）')

        print('\n完成。默认账号：admin / admin123（管理员），20210001 / 123456（学生）')


if __name__ == '__main__':
    main()
