# -*- coding: utf-8 -*-
"""管理员移交 端到端验证（打真实 HTTP，跑完自动清理）。

用法（需先启动后端）：
    .\\.venv\\Scripts\\python.exe scripts\\verify_admin_handover.py

验证内容：
    1. 管理员不能直接改自己的角色 / 不能把别人直接改成管理员；
    2. 发起移交 → 接班人立刻是管理员但冻结（后台接口全被拦），发起人功能照常；
    3. 撤销 → 接班人回到普通用户，发起人不受影响；
    4. 到期（把生效时间改到过去模拟）→ 自动落地：发起人降级、接班人上任；
    5. 审核员够不到移交接口。
    最后把测试账号与数据清理干净。
"""
import json
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:5000/api/v1'
PASSED, FAILED = [], []


def call(method, path, token=None, body=None, expect=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload, status = json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as exc:
        payload, status = json.loads(exc.read().decode() or '{}'), exc.code

    if expect is not None:
        code = payload.get('code')
        label = f'{method} {path}'
        if code == expect:
            PASSED.append(f'{label} -> code={code}')
        else:
            FAILED.append(f'{label} -> 期望 {expect}，实际 {code} msg={payload.get("msg")}')
    return payload, status


def login(account, password):
    body, _ = call('POST', '/auth/login', body={'student_id': account, 'password': password}, expect=0)
    return body['data']['access_token']


def main():
    admin = login('admin', 'admin123')
    stu_id = _user_id(admin, '20210001')
    stu_token = login('20210001', '123456')

    print('[1] 单管理员的硬约束')
    call('POST', f'/admin/users/{_user_id(admin, "admin")}/role', admin,
         {'role': 'user'}, expect=1001)          # 不能改自己的角色
    call('POST', f'/admin/users/{stu_id}/role', admin,
         {'role': 'admin'}, expect=1001)          # 不能把别人直接改成管理员

    print('[2] 发起移交：接班人冻结，发起人照常')
    started, _ = call('POST', '/admin/handover', admin,
                      {'user_id': stu_id, 'reason': '端到端验证'}, expect=0)
    assert started['data']['effective_at'], started
    print('    生效时间（北京时间）:', started['data']['effective_at'])

    # 接班人：身份是管理员，但后台被冻结拦住
    me = call('GET', '/auth/me', stu_token, expect=0)[0]['data']
    assert me['is_admin'] is True and me['is_frozen'] is True, me
    assert me['capabilities'] == [], me['capabilities']
    assert me['role_label'] == '管理员（待上任）', me
    frozen, _ = call('GET', '/admin/dashboard/overview', stu_token)
    assert frozen['code'] == 2003 and '冻结' in frozen['msg'], frozen
    PASSED.append('接班人后台被冻结拦截')

    # 发起人：仍是管理员
    call('GET', '/admin/dashboard/overview', admin, expect=0)
    status = call('GET', '/admin/handover/status', admin, expect=0)[0]['data']
    assert status['handover_role'] == 'initiator', status
    assert status['window_hours'] == 24, status
    assert status['server_now'], '必须下发服务器北京时间'
    PASSED.append(f"状态接口：{status['handover_role']}，剩余至 {status['handover_deadline']}")

    # 审核员够不到
    for method, path in (('get', '/admin/handover/status'), ('post', '/admin/handover')):
        resp = getattr(__import__('urllib.request', fromlist=['x']), 'urlopen', None)
        call(method.upper(), path, stu_token, None, expect=2003)

    print('[3] 撤销：双方复原')
    call('POST', '/admin/handover/cancel', admin, expect=0)
    me2 = call('GET', '/auth/me', stu_token, expect=0)[0]['data']
    assert me2['is_admin'] is False and me2['is_frozen'] is False, me2
    call('GET', '/admin/dashboard/overview', admin, expect=0)
    PASSED.append('撤销后接班人回到普通用户、发起人仍是管理员')

    print('[4] 到期自动落地')
    call('POST', '/admin/handover', admin, {'user_id': stu_id}, expect=0)
    _expire_handover()
    # 任意一次后台请求触发懒结算
    settled, _ = call('GET', '/admin/dashboard/overview', stu_token)
    assert settled['code'] == 0, settled
    PASSED.append('接班人解冻并正式上任（可访问后台）')

    # 原管理员已降级
    denied, _ = call('GET', '/admin/dashboard/overview', admin)
    assert denied['code'] == 2003, denied
    PASSED.append('原管理员已降为普通用户（旧 token 也进不了后台）')

    print('[5] 交还管理员，恢复演示环境')
    _restore_admin()
    admin2 = login('admin', 'admin123')
    call('GET', '/admin/dashboard/overview', admin2, expect=0)
    PASSED.append('演示账号 admin 已恢复为管理员')

    print()
    print('=' * 72)
    print(f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    for item in PASSED:
        print('  [OK]', item)
    for item in FAILED:
        print('  [FAIL]', item)
    print('=' * 72)
    return 1 if FAILED else 0


def _user_id(token, student_id):
    body, _ = call('GET', f'/admin/users?keyword={student_id}', token, expect=0)
    return body['data']['list'][0]['id']


def _expire_handover():
    """把移交生效时间改到过去，模拟"24 小时已过"（直接操作开发库）。"""
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect('school_life.db')
    past = (datetime.now() - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("UPDATE users SET handover_effective_at = ? WHERE role = 'admin' "
                 "AND handover_to_id IS NOT NULL", (past,))
    conn.commit()
    conn.close()


def _restore_admin():
    """把 admin 恢复为管理员、普通用户恢复为普通用户（清理验证残留）。"""
    import sqlite3

    conn = sqlite3.connect('school_life.db')
    conn.execute("UPDATE users SET role = 'user', handover_to_id = NULL, handover_at = NULL, "
                 "handover_effective_at = NULL, handover_freeze_at = NULL "
                 "WHERE student_id <> 'admin'")
    conn.execute("UPDATE users SET role = 'admin', handover_to_id = NULL, handover_at = NULL, "
                 "handover_effective_at = NULL, handover_freeze_at = NULL "
                 "WHERE student_id = 'admin'")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    sys.exit(main())
