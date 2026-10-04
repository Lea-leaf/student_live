# -*- coding: utf-8 -*-
"""恢复演示环境：撤销残留的管理员移交，并把 admin 恢复为唯一管理员。

用于端到端验证脚本被中途打断后清理现场（正常情况下脚本自己会清理）。
"""
import sqlite3

conn = sqlite3.connect('school_life.db')

# 1) 撤销进行中的移交：接班人退回普通用户并解冻
conn.execute(
    "UPDATE users SET role = 'user', handover_to_id = NULL, handover_at = NULL, "
    "handover_effective_at = NULL, handover_freeze_at = NULL "
    "WHERE student_id <> 'admin'"
)
# 2) admin 恢复为管理员并清空移交信息
conn.execute(
    "UPDATE users SET role = 'admin', handover_to_id = NULL, handover_at = NULL, "
    "handover_effective_at = NULL, handover_freeze_at = NULL "
    "WHERE student_id = 'admin'"
)
conn.commit()

print('清理后角色分布：')
for row in conn.execute('SELECT role, COUNT(*) FROM users GROUP BY role'):
    print('  ', row)
print('残留移交记录：', conn.execute(
    'SELECT COUNT(*) FROM users WHERE handover_to_id IS NOT NULL '
    'OR handover_freeze_at IS NOT NULL'
).fetchone()[0])
conn.close()
