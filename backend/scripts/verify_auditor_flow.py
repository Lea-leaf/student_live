# -*- coding: utf-8 -*-
"""审核员角色 + 审核指派 的端到端验证（打真实 HTTP 接口）。

用法（需先启动后端）：
    .\\.venv\\Scripts\\python.exe scripts\\verify_auditor_flow.py

会临时创建两个审核员账号与若干帖子，跑完整条链路后**自动清理**：
    - 超级管理员任命审核员 -> 审核员登录 -> 拿到能力清单
    - 越权矩阵：系统配置 / 模块 / 日志 / 回收站 / 改角色 / 重置密码 / 用户明细 全部 403
    - 允许矩阵：概览 / 审核台 / 内容 / 评论 / 举报 / 用户列表 / 封禁普通用户
    - 指派 -> 改派 -> 收回 -> 认领 -> 抢单失败 -> 禁止自审 -> 审核通过 -> 流水完整
"""
import json
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:5000/api/v1'
PASSED = []
FAILED = []


def call(method, path, token=None, body=None, expect=None):
    url = f'{BASE}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
            status = resp.status
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode() or '{}')
        status = exc.code

    label = f'{method} {path}'
    if expect is not None:
        code = payload.get('code')
        if code == expect:
            PASSED.append(f'{label} -> code={code}')
        else:
            FAILED.append(f'{label} -> 期望 code={expect}，实际 code={code} msg={payload.get("msg")}')
    return payload, status


def login(account, password):
    body, _ = call('POST', '/auth/login', body={'student_id': account, 'password': password}, expect=0)
    return body['data']['access_token']


AUD_A = 'audit001'
AUD_B = 'audit002'


def main():
    admin = login('admin', 'admin123')

    # ---------- 准备两个审核员 ----------
    for sid, nick in ((AUD_A, '审核员甲'), (AUD_B, '审核员乙')):
        body, _ = call('POST', '/admin/users', admin,
                       {'student_id': sid, 'password': 'audit123', 'nickname': nick, 'role': 'auditor'},
                       expect=0)
        auditor_id = body['data']['id']
        if sid == AUD_A:
            aud_a_id = auditor_id
        else:
            aud_b_id = auditor_id
        assert body['data']['role'] == 'auditor', body
        assert body['data']['identity'] == 'staff', body
        assert body['data']['is_admin'] is False, body

    aud_a = login(AUD_A, 'audit123')
    aud_b = login(AUD_B, 'audit123')

    # ---------- 身份与能力 ----------
    me, _ = call('GET', '/auth/me', aud_a, expect=0)
    assert me['data']['role_label'] == '内容审核员', me
    assert me['data']['is_staff'] is True and me['data']['is_admin'] is False, me
    caps = set(me['data']['capabilities'])
    assert 'post.audit' in caps and 'comment.manage' in caps, caps
    assert 'config.manage' not in caps and 'user.role' not in caps, caps

    # ---------- 越权矩阵（应全部 403 / code 2003）----------
    for method, path in (
        ('GET', '/admin/configs'), ('PUT', '/admin/configs'),
        ('GET', '/admin/modules'), ('POST', '/admin/modules'),
        ('GET', '/admin/logs/operations'), ('GET', '/admin/logs/logins'),
        ('GET', '/admin/trash'), ('GET', '/admin/dashboard/media'),
        ('POST', '/admin/dashboard/media/clean'),
    ):
        call(method, path, aud_a, expect=2003)

    call('POST', f'/admin/users/{aud_b_id}/role', aud_a, {'role': 'user'}, expect=2003)
    call('POST', f'/admin/users/{aud_b_id}/reset-password', aud_a, {}, expect=2003)
    call('GET', f'/admin/users/{aud_b_id}', aud_a, expect=2003)
    call('GET', f'/admin/users/{aud_b_id}/posts', aud_a, expect=2003)
    call('GET', f'/admin/users/{aud_b_id}/logs', aud_a, expect=2003)
    # 审核员不能封禁同僚
    call('POST', f'/admin/users/{aud_b_id}/ban', aud_a, {'reason': '越权'}, expect=2003)

    # ---------- 允许矩阵 ----------
    for path in ('/admin/dashboard/overview', '/admin/posts/pending', '/admin/posts',
                 '/admin/comments', '/admin/reports', '/admin/users'):
        call('GET', path, aud_a, expect=0)

    # ---------- 造一条待审帖（审核员自己发的）----------
    own, _ = call('POST', '/lost_found/posts', aud_a,
                  {'type': 'lost_found', 'title': '审核员自己发的帖子',
                   'contact': '微信 aud_self'}, expect=0)
    own_id = own['data']['id']
    assert own['data']['audit_status'] == 'pending', own  # 审核员发帖必须走审核

    # 禁止自审
    call('POST', f'/admin/posts/{own_id}/audit', aud_a, {'audit_status': 'approved'}, expect=2003)
    # 别人可以审
    call('POST', f'/admin/posts/{own_id}/audit', aud_b, {'audit_status': 'approved'}, expect=0)

    # ---------- 普通用户发一条，走完整指派链路 ----------
    stu = login('20210001', '123456')
    post, _ = call('POST', '/lost_found/posts', stu,
                   {'type': 'lost_found', 'title': '指派链路验证帖',
                    'contact': '微信 flow_test'}, expect=0)
    post_id = post['data']['id']

    # 指派给甲
    call('POST', f'/admin/posts/{post_id}/assign', admin, {'assignee_id': aud_a_id}, expect=0)
    detail, _ = call('GET', f'/admin/posts/{post_id}', admin, expect=0)
    assert detail['data']['assignee_id'] == aud_a_id, detail['data']

    # 审核员不能指派（只有管理员能）
    call('POST', f'/admin/posts/{post_id}/assign', aud_b, {'assignee_id': aud_b_id}, expect=2003)

    # 改派给乙，再收回公共池
    call('POST', f'/admin/posts/{post_id}/assign', admin, {'assignee_id': aud_b_id}, expect=0)
    call('POST', f'/admin/posts/{post_id}/assign', admin, {'assignee_id': None}, expect=0)

    # 甲认领（先到先得）
    claimed, _ = call('POST', f'/admin/posts/{post_id}/claim', aud_a, expect=0)
    assert claimed['data']['assignee_id'] == aud_a_id, claimed
    assert claimed['data']['assignment_expires_at'], claimed  # 24 小时到期

    # 乙再抢 -> 4005
    call('POST', f'/admin/posts/{post_id}/claim', aud_b, expect=4005)
    # 乙也不能审（归属甲）
    call('POST', f'/admin/posts/{post_id}/audit', aud_b, {'audit_status': 'approved'}, expect=4005)
    # 甲审通过
    call('POST', f'/admin/posts/{post_id}/audit', aud_a,
         {'audit_status': 'approved', 'remark': '内容合规'}, expect=0)

    # 审核完成后指派被清空
    after, _ = call('GET', f'/admin/posts/{post_id}', admin, expect=0)
    assert after['data']['assignee_id'] is None, after['data']
    assert after['data']['auditor']['student_id'] == AUD_A, after['data']

    # ---------- 审核流水 ----------
    logs, _ = call('GET', f'/admin/posts/{post_id}/audit-logs', admin, expect=0)
    actions = [row['action'] for row in logs['data']['list']]
    assert actions == ['assign', 'assign', 'release', 'claim', 'approve'], actions
    claim_row = [r for r in logs['data']['list'] if r['action'] == 'claim'][0]
    assert claim_row['assign_source'] == 'self', claim_row
    assert claim_row['assignee']['student_id'] == AUD_A, claim_row

    # ---------- 审核员可封禁普通用户 ----------
    call('POST', f'/admin/users/{_student_id(admin)}/ban', aud_a, {'reason': '验证封禁能力'}, expect=0)
    call('POST', f'/admin/users/{_student_id(admin)}/unban', aud_a, expect=0)

    # ---------- 清理 ----------
    cleanup(admin, [own_id, post_id], [aud_a_id, aud_b_id])

    print()
    print('=' * 72)
    print(f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    for item in FAILED:
        print('  [FAIL]', item)
    print('=' * 72)
    return 1 if FAILED else 0


def _student_id(admin_token, keyword='20210001'):
    body, _ = call('GET', f'/admin/users?keyword={keyword}', admin_token, expect=0)
    return body['data']['list'][0]['id']


def cleanup(admin, post_ids, user_ids):
    """删除验证过程中产生的帖子与账号（走回收站彻底删除 + 删除用户）。

    用户删除接口要求 confirm_student_id 二次确认，所以先查学号再删。
    """
    for post_id in post_ids:
        call('DELETE', f'/admin/posts/{post_id}', admin)
        call('DELETE', f'/admin/trash/{post_id}', admin)
    for user_id in user_ids:
        body, _ = call('GET', f'/admin/users/{user_id}', admin)
        info = (body.get('data') or {}).get('user') or {}
        student_id = info.get('student_id')
        if student_id:
            call('DELETE', f'/admin/users/{user_id}', admin, {'confirm_student_id': student_id})


if __name__ == '__main__':
    sys.exit(main())
