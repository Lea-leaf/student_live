# -*- coding: utf-8 -*-
"""验证：接任者原本是**审核员**时，冻结期他还能不能审核（方案 A）。

场景（真实 HTTP）：
    1. 造一个审核员账号；
    2. 管理员把管理员权限移交给这位审核员；
    3. 冻结期检查：
       - 他仍能进审核台、仍能审核帖子（工作不停）；
       - 他拿不到系统配置 / 模块 / 角色 / 回收站；
       - 他发的帖子仍要走审核（is_admin 为假）；
       - 对外身份显示「内容审核员」而不是「管理员」；
    4. 撤销移交 → 他**还原为审核员**（不是普通用户）；
    5. 清理现场。
"""
import json
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:5000/api/v1'
AUD = 'audit900'
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
        (PASSED if code == expect else FAILED).append(
            f'{label} -> code={code}（期望 {expect}）' if code != expect else f'{label} -> {code}'
        )
    return payload, status


def login(a, p):
    payload, _ = call('POST', '/auth/login', body={'student_id': a, 'password': p}, expect=0)
    return payload['data']['access_token']


def main():
    admin = login('admin', 'admin123')

    # 1) 造审核员
    created, _ = call('POST', '/admin/users', admin,
                      {'student_id': AUD, 'password': 'audit123', 'nickname': '交接审核员',
                       'role': 'auditor'}, expect=0)
    aud_id = created['data']['id']
    aud_token = login(AUD, 'audit123')
    call('GET', '/admin/posts/pending', aud_token, expect=0)

    # 拿一个普通用户造待审帖
    stu = call('GET', '/admin/users?keyword=20210001', admin, expect=0)[0]['data']['list'][0]['id']
    stu_token = login('20210001', '123456')
    post, _ = call('POST', '/lost_found/posts', stu_token,
                   {'type': 'lost_found', 'title': '冻结期审核验证帖', 'contact': '微信 fz1'}, expect=0)
    post_id = post['data']['id']

    print('[1] 移交前：审核员能进审核台 ->', call('GET', '/admin/posts/pending', aud_token)[0]['code'])

    print('[2] 发起移交（接任者是审核员）')
    call('POST', '/admin/handover', admin, {'user_id': aud_id, 'reason': '验证审核员交接'}, expect=0)

    me = call('GET', '/auth/me', aud_token, expect=0)[0]['data']
    print('    is_frozen      =', me['is_frozen'])
    print('    is_admin       =', me['is_admin'], '（必须 False）')
    print('    role_label     =', me['role_label'], '（显示原身份）')
    print('    能力            =', me['capabilities'])
    assert me['is_admin'] is False, '冻结中不该是管理员'
    assert me['role_label'] == '内容审核员', me['role_label']
    assert 'post.audit' in me['capabilities'], '审核能力必须保留'
    assert 'config.manage' not in me['capabilities']
    PASSED.append('冻结期身份=内容审核员、保留 post.audit、无 config.manage')

    print('[3] 冻结期：该能用的 / 该不能用的')
    call('GET', '/admin/posts/pending', aud_token, expect=0)          # 审核台：能进
    call('GET', '/admin/dashboard/overview', aud_token, expect=0)     # 概览：能进
    call('GET', '/admin/configs', aud_token, expect=2003)             # 配置：拒绝
    call('GET', '/admin/modules', aud_token, expect=2003)             # 模块：拒绝
    call('GET', '/admin/logs/operations', aud_token, expect=2003)     # 日志：拒绝
    call('GET', '/admin/trash', aud_token, expect=2003)               # 回收站：拒绝
    call('POST', '/admin/handover', aud_token, {}, expect=2003)        # 再移交：拒绝

    print('[4] 冻结期他真的还能审帖')
    audited, _ = call('POST', f'/admin/posts/{post_id}/audit', aud_token,
                      {'audit_status': 'approved', 'remark': '交接期照常审核'}, expect=0)
    assert audited['code'] == 0, audited
    PASSED.append('冻结期成功审核了一条待审帖')

    print('[5] 冻结期他发的帖仍要走审核')
    frozen_post, _ = call('POST', '/lost_found/posts', aud_token,
                          {'type': 'lost_found', 'title': '冻结期我自己发的',
                           'contact': '微信 fz2'}, expect=0)
    assert frozen_post['data']['audit_status'] == 'pending', frozen_post['data']
    PASSED.append('冻结期发帖 audit_status=pending（未免审）')
    frozen_post_id = frozen_post['data']['id']

    print('[6] 撤销 → 还原为审核员（不是普通用户）')
    call('POST', '/admin/handover/cancel', admin, expect=0)
    me2 = call('GET', '/auth/me', aud_token, expect=0)[0]['data']
    print('    role        =', me2['role'])
    print('    role_label  =', me2['role_label'])
    print('    is_frozen   =', me2['is_frozen'])
    assert me2['role'] == 'auditor', me2
    assert me2['is_frozen'] is False
    assert 'post.audit' in me2['capabilities']
    PASSED.append('撤销后角色还原为 auditor（原身份未丢失）')

    print('[7] 清理')
    for pid in (post_id, frozen_post_id):
        call('DELETE', f'/admin/posts/{pid}', admin)
        call('DELETE', f'/admin/trash/{pid}', admin)
    call('DELETE', f'/admin/users/{aud_id}', admin, {'confirm_student_id': AUD})
    left = call('GET', f'/admin/users?keyword={AUD}', admin)[0]['data']['total']
    assert left == 0, f'测试账号未清理干净：{left}'
    PASSED.append('测试账号与帖子已清理')

    print()
    print('=' * 72)
    print(f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    for item in PASSED:
        print('  [OK]', item)
    for item in FAILED:
        print('  [FAIL]', item)
    print('=' * 72)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
