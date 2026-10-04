# -*- coding: utf-8 -*-
"""接口冒烟测试：对「已启动的真实服务」发请求，验证端到端链路。

与 pytest 的区别：
- pytest 用内存库 + 测试客户端（进程内）；
- 本脚本用 HTTP 请求打真实端口，覆盖 CORS、真实数据库、真实 JWT 链路。

用法：python scripts/smoke_test.py [base_url]
默认 base_url = http://127.0.0.1:5000
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000').rstrip('/')
PREFIX = f'{BASE}/api/v1'

passed = 0
failed = 0


def call(method, path, data=None, token=None, expect_code=0):
    """发一次请求并断言业务码。"""
    global passed, failed
    url = path if path.startswith('http') else f'{PREFIX}{path}'
    # 查询串里的中文需要百分号编码，否则 urllib 会以 ascii 发送而报错
    url = urllib.parse.quote(url, safe=':/?&=%#')
    body = json.dumps(data).encode('utf-8') if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header('Content-Type', 'application/json')
    if token:
        request.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        failed += 1
        print(f'  [FAIL] {method} {path} -> 请求异常：{exc}')
        return None

    ok = payload.get('code') == expect_code
    if ok:
        passed += 1
        print(f'  [ OK ] {method} {path} -> code={payload.get("code")} msg={payload.get("msg")}')
    else:
        failed += 1
        print(f'  [FAIL] {method} {path} -> code={payload.get("code")} msg={payload.get("msg")} (期望 {expect_code})')
    return payload.get('data')


def main():
    print(f'>>> 冒烟测试目标：{BASE}\n')

    print('[1] 基础接口')
    call('GET', '/common/health')
    call('GET', '/common/enums')
    call('GET', '/common/configs')
    modules = call('GET', '/common/modules')
    if modules:
        print(f'       启用中的模块：{[item["code"] for item in modules["list"]]}')

    print('\n[2] 认证')
    captcha = call('GET', '/auth/captcha')
    call('POST', '/auth/login', {'student_id': 'admin', 'password': 'wrong-password'}, expect_code=2006)
    admin_login = call('POST', '/auth/login', {'student_id': 'admin', 'password': 'admin123'})
    student_login = call('POST', '/auth/login', {'student_id': '20210001', 'password': '123456'})
    if not admin_login or not student_login:
        print('\n登录失败，后续用例跳过（请确认已执行 scripts/dev_init.py --seed）')
        print(f'\n结果：通过 {passed}，失败 {failed}')
        return 1
    admin_token = admin_login['access_token']
    student_token = student_login['access_token']
    admin_uid = (admin_login.get('user') or {}).get('id')
    student_uid = (student_login.get('user') or {}).get('id')
    call('GET', '/auth/me', token=student_token)
    call('GET', '/auth/me', expect_code=2001)
    call('GET', '/auth/security-notice')

    print('\n[3] 失物招领：列表 / 详情 / 发布')
    listing = call('GET', '/lost_found/posts?page=1&size=5')
    total = listing['total'] if listing else 0
    print(f'       公开列表条数：{total}')
    call('GET', '/lost_found/meta')
    created = call('POST', '/lost_found/posts', {
        'title': '冒烟测试：捡到一把钥匙',
        'content': '在实验楼门口捡到，已交给门卫',
        'location': '实验楼',
        'contact': '微信 smoke_test',
    }, token=student_token)
    new_id = created['id'] if created else None
    if new_id:
        print(f'       新帖 ID={new_id}，审核状态={created["audit_status"]}')
    call('GET', '/lost_found/my/posts', token=student_token)
    call('GET', '/lost_found/posts?keyword=钥匙')
    call('GET', '/lost_found/posts/999999', token=student_token, expect_code=4001)

    print('\n[4] 管理端')
    call('GET', '/admin/dashboard/overview', token=admin_token)
    call('GET', '/admin/dashboard/trend', token=admin_token)
    call('GET', '/admin/dashboard/module-stats', token=admin_token)
    call('GET', '/admin/dashboard/media', token=admin_token)
    call('GET', '/admin/users?page=1&size=5', token=admin_token)
    call('GET', '/admin/posts?page=1&size=5', token=admin_token)
    call('GET', '/admin/posts/pending', token=admin_token)
    call('GET', '/admin/modules', token=admin_token)
    call('GET', '/admin/trash', token=admin_token)
    call('GET', '/admin/reports', token=admin_token)
    call('GET', '/admin/logs/operations', token=admin_token)
    call('GET', '/admin/logs/logins', token=admin_token)
    call('GET', '/admin/logs/summary', token=admin_token)
    call('GET', '/admin/configs', token=admin_token)
    call('GET', '/admin/dashboard/overview', token=student_token, expect_code=2003)
    call('GET', '/admin/dashboard/overview', expect_code=2001)

    print('\n[5] 审核闭环')
    if new_id:
        call('POST', f'/admin/posts/{new_id}/audit', {'audit_status': 'approved', 'remark': '冒烟测试通过'},
             token=admin_token)
        detail = call('GET', f'/lost_found/posts/{new_id}', token=student_token)
        if detail:
            print(f'       审核后详情可访问，状态={detail["status"]}，联系方式={detail["contact"]}')
        call('POST', f'/lost_found/posts/{new_id}/claim', token=student_token)
        call('GET', f'/lost_found/posts/{new_id}', token=student_token)
        call('DELETE', f'/lost_found/posts/{new_id}', token=student_token)
        call('POST', f'/admin/trash/{new_id}/restore', token=admin_token)

    print('\n[6] 互动：评论 / 点赞 / 私信 / 通知')
    call('GET', '/notifications', token=student_token)
    call('GET', '/notifications/unread-count', token=student_token)
    call('GET', '/favorites', token=student_token)

    comment = None
    if new_id:
        comment = call('POST', f'/comments/posts/{new_id}/comments',
                       {'content': '冒烟测试：这是一条评论'}, token=student_token)
    if comment:
        comment_id = comment['id']
        call('POST', f'/comments/posts/{new_id}/comments',
             {'content': '冒烟测试：楼中楼回复', 'parent_id': comment_id}, token=admin_token)
        call('GET', f'/comments/posts/{new_id}/comments')
        call('POST', f'/likes/comments/{comment_id}', token=admin_token)
        call('GET', f'/likes/comments/{comment_id}', token=admin_token)

    if new_id:
        call('POST', f'/likes/posts/{new_id}', token=admin_token)
        call('GET', f'/likes/posts/{new_id}', token=admin_token)

    if admin_uid and student_uid:
        message = call('POST', f'/messages/with/{student_uid}',
                       {'content': '冒烟测试：一条私信'}, token=admin_token)
        call('GET', '/messages/unread-count', token=student_token)
        call('GET', '/messages/conversations', token=student_token)
        call('GET', f'/messages/with/{admin_uid}', token=student_token)
        if message:
            call('POST', f'/messages/read/{message["id"]}', token=student_token)

    call('GET', '/notifications', token=student_token)

    print(f'\n===== 结果：通过 {passed}，失败 {failed} =====')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
