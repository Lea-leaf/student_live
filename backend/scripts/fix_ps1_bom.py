# -*- coding: utf-8 -*-
"""给 PowerShell 脚本补上 UTF-8 BOM。

背景（本项目踩过的坑）：
    Windows 自带的 PowerShell 5.1 读取「UTF-8 无 BOM」的 .ps1 文件时，
    会按系统 ANSI 代码页（中文 Windows 是 GBK）解码，
    中文注释被拆成乱码字节，脚本直接报
        "表达式或语句中包含意外的标记 }" / "字符串缺少终止符"
    而无法运行。加 BOM 后 5.1 与 7.x 都能正确识别。

什么时候需要跑：
    用编辑器把 .ps1 另存为「UTF-8」时常常会丢掉 BOM，
    改完脚本执行一次本工具即可修复。

用法（在 backend 目录下）：
    python scripts/fix_ps1_bom.py            # 修复仓库内所有 .ps1
    python scripts/fix_ps1_bom.py --check    # 只检查不修改（CI 用）
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

BOM = b'\xef\xbb\xbf'

#: 需要保证 BOM 的脚本所在目录（项目根目录）
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def find_ps1(root):
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过依赖/构建目录，避免无谓遍历
        dirnames[:] = [d for d in dirnames
                       if d not in ('.venv', 'node_modules', 'dist', '.git', '__pycache__')]
        for name in filenames:
            if name.lower().endswith('.ps1'):
                yield os.path.join(dirpath, name)


def main():
    parser = argparse.ArgumentParser(description='检查/修复 PowerShell 脚本的 UTF-8 BOM')
    parser.add_argument('--check', action='store_true', help='只检查，不修改文件')
    args = parser.parse_args()

    checked = 0
    fixed = 0
    bad = []

    for path in find_ps1(ROOT):
        checked += 1
        with open(path, 'rb') as handle:
            raw = handle.read()

        if raw.startswith(BOM):
            continue

        bad.append(path)
        if args.check:
            continue

        with open(path, 'wb') as handle:
            handle.write(BOM + raw)
        fixed += 1
        print(f'[已修复] {path}')

    print(f'\n检查了 {checked} 个 .ps1 文件。')
    if bad and args.check:
        print(f'以下 {len(bad)} 个文件缺少 BOM（会导致 PowerShell 5.1 无法运行）：')
        for path in bad:
            print(f'  - {path}')
        return 1
    if fixed:
        print(f'已为 {fixed} 个文件补上 BOM。')
    else:
        print('全部文件都已带 BOM，无需处理。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
