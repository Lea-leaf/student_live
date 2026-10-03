# -*- coding: utf-8 -*-
"""管理端测试：权限、用户管理、内容管理、模块管理、日志、配置、举报。"""

from tests.conftest import auth_header, login


def test_admin_endpoints_require_admin(client, student_token):
    """普通用户访问管理端接口必须被拒绝。"""
    for url in ('/api/v1/admin/dashboard/overview', '/api/v1/admin/users',
                '/api/v1/admin/posts', '/api/v1/admin/trash', '/api/v1/admin/modules',
                '/api/v1/admin/logs/operations', '/api/v1/admin/configs'):
        response = client.get(url, headers=auth_header(student_token))
        assert response.status_code == 403, url
        assert response.get_json()['code'] == 2003, url


def test_admin_endpoints_require_login(client):
    response = client.get('/api/v1/admin/dashboard/overview')
    assert response.status_code == 401


def test_dashboard_overview(client, admin_token):
    body = client.get('/api/v1/admin/dashboard/overview', headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    for key in ('user_total', 'post_total', 'post_today', 'post_pending'):
        assert key in body['data'], key


def test_user_list_and_search(client, admin_token, student):
    body = client.get('/api/v1/admin/users', headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    assert body['data']['total'] >= 1

    body = client.get('/api/v1/admin/users?keyword=20210001', headers=auth_header(admin_token)).get_json()
    assert body['data']['total'] == 1
    assert body['data']['list'][0]['student_id'] == '20210001'


def test_ban_unban_and_token_invalidated(client, admin_token, student_token, student):
    banned = client.post(f'/api/v1/admin/users/{student}/ban',
                         json={'reason': '发布广告'}, headers=auth_header(admin_token)).get_json()
    assert banned['code'] == 0
    assert banned['data']['status'] == 'banned'

    # 被封禁用户的 token 立即失效
    me = client.get('/api/v1/auth/me', headers=auth_header(student_token))
    assert me.get_json()['code'] == 2004

    unbanned = client.post(f'/api/v1/admin/users/{student}/unban',
                           headers=auth_header(admin_token)).get_json()
    assert unbanned['code'] == 0
    assert login(client, '20210001', '123456')


def test_admin_cannot_ban_self(client, admin_token, admin):
    response = client.post(f'/api/v1/admin/users/{admin}/ban',
                           json={'reason': 'test'}, headers=auth_header(admin_token))
    assert response.get_json()['code'] == 1001


def test_reset_password(client, admin_token, student):
    body = client.post(f'/api/v1/admin/users/{student}/reset-password',
                       json={}, headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    assert body['data']['new_password'] == '123456'
    assert login(client, '20210001', '123456')


def test_admin_user_posts_and_logs(client, admin_token, student, sample_post):
    posts = client.get(f'/api/v1/admin/users/{student}/posts',
                       headers=auth_header(admin_token)).get_json()
    assert posts['data']['total'] == 1

    logs = client.get(f'/api/v1/admin/users/{student}/logs',
                      headers=auth_header(admin_token)).get_json()
    assert logs['code'] == 0
    assert 'login_logs' in logs['data']


def test_batch_audit(client, admin_token, student_token):
    ids = []
    for index in range(3):
        created = client.post('/api/v1/lost_found/posts',
                              json={'title': f'批量 {index}', 'contact': '微信 a'},
                              headers=auth_header(student_token)).get_json()
        ids.append(created['data']['id'])

    body = client.post('/api/v1/admin/posts/batch/audit',
                       json={'post_ids': ids, 'audit_status': 'approved'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0
    assert body['data']['affected'] == 3
    assert client.get('/api/v1/lost_found/posts').get_json()['data']['total'] == 3


def test_post_toggle_top_and_status(client, admin_token, sample_post):
    top = client.post(f'/api/v1/admin/posts/{sample_post}/top',
                      json={}, headers=auth_header(admin_token)).get_json()
    assert top['data']['is_top'] is True

    status = client.post(f'/api/v1/admin/posts/{sample_post}/status',
                         json={'status': 'expired', 'reason': '超期自动标记'},
                         headers=auth_header(admin_token)).get_json()
    assert status['data']['status'] == 'expired'


def test_admin_delete_moves_to_trash_and_purge(client, admin_token, sample_post):
    client.delete(f'/api/v1/admin/posts/{sample_post}', headers=auth_header(admin_token))
    trash = client.get('/api/v1/admin/trash', headers=auth_header(admin_token)).get_json()
    assert trash['data']['total'] == 1

    purged = client.delete(f'/api/v1/admin/trash/{sample_post}',
                           headers=auth_header(admin_token)).get_json()
    assert purged['code'] == 0
    trash = client.get('/api/v1/admin/trash', headers=auth_header(admin_token)).get_json()
    assert trash['data']['total'] == 0


def test_module_management(client, admin_token):
    """模块启停 / 排序 / 新增 —— 需求「模块管理」+「其他（后台可新增）」。"""
    modules = client.get('/api/v1/admin/modules', headers=auth_header(admin_token)).get_json()
    assert modules['code'] == 0
    codes = [item['code'] for item in modules['data']['list']]
    assert 'lost_found' in codes and 'second_hand' in codes

    # 启用二手交易
    second_hand = next(item for item in modules['data']['list'] if item['code'] == 'second_hand')
    toggled = client.post(f"/api/v1/admin/modules/{second_hand['id']}/toggle",
                          json={'enabled': True}, headers=auth_header(admin_token)).get_json()
    assert toggled['data']['enabled'] is True

    public_modules = client.get('/api/v1/common/modules').get_json()
    assert 'second_hand' in [item['code'] for item in public_modules['data']['list']]

    # 新增「其他」模块
    created = client.post('/api/v1/admin/modules',
                          json={'code': 'other', 'name': '其他', 'sort_order': 99},
                          headers=auth_header(admin_token)).get_json()
    assert created['code'] == 0
    assert created['data']['code'] == 'other'

    # 排序
    reorder = client.post('/api/v1/admin/modules/reorder',
                          json={'items': [{'id': created['data']['id'], 'sort_order': 1}]},
                          headers=auth_header(admin_token)).get_json()
    assert reorder['code'] == 0

    # 删除新增模块
    deleted = client.delete(f"/api/v1/admin/modules/{created['data']['id']}",
                            headers=auth_header(admin_token)).get_json()
    assert deleted['code'] == 0

    # 系统内置模块不允许删除
    lost_found = next(item for item in modules['data']['list'] if item['code'] == 'lost_found')
    forbidden = client.delete(f"/api/v1/admin/modules/{lost_found['id']}",
                              headers=auth_header(admin_token)).get_json()
    assert forbidden['code'] != 0


def test_configs_update_affects_behavior(client, admin_token, student_token):
    """关闭发帖审核后，新帖直接通过。"""
    updated = client.put('/api/v1/admin/configs',
                         json={'items': [{'key': 'post_audit_enabled', 'value': '0'}]},
                         headers=auth_header(admin_token)).get_json()
    assert updated['code'] == 0

    created = client.post('/api/v1/lost_found/posts',
                          json={'title': '免审帖', 'contact': '微信 a'},
                          headers=auth_header(student_token)).get_json()
    assert created['data']['audit_status'] == 'approved'

    # 恢复默认
    client.put('/api/v1/admin/configs',
               json={'items': [{'key': 'post_audit_enabled', 'value': '1'}]},
               headers=auth_header(admin_token))


def test_logs_endpoints(client, admin_token, student_token):
    # 产生一些日志
    client.get('/api/v1/auth/me', headers=auth_header(student_token))

    operations = client.get('/api/v1/admin/logs/operations',
                            headers=auth_header(admin_token)).get_json()
    assert operations['code'] == 0
    assert operations['data']['total'] >= 1

    logins = client.get('/api/v1/admin/logs/logins', headers=auth_header(admin_token)).get_json()
    assert logins['code'] == 0
    assert logins['data']['total'] >= 1

    summary = client.get('/api/v1/admin/logs/summary', headers=auth_header(admin_token)).get_json()
    assert 'operation_total' in summary['data']


def test_report_flow(client, admin_token, student2_token, sample_post):
    """举报 → 管理员处理（联动删除帖子）。"""
    created = client.post('/api/v1/reports',
                          json={'post_id': sample_post, 'reason': '虚假信息'},
                          headers=auth_header(student2_token)).get_json()
    assert created['code'] == 0
    report_id = created['data']['id']

    # 重复举报被拦住
    again = client.post('/api/v1/reports',
                        json={'post_id': sample_post, 'reason': '虚假信息'},
                        headers=auth_header(student2_token)).get_json()
    assert again['code'] != 0

    handled = client.post(f'/api/v1/admin/reports/{report_id}/handle',
                          json={'status': 'handled', 'remark': '举报成立', 'action': 'delete_post'},
                          headers=auth_header(admin_token)).get_json()
    assert handled['code'] == 0
    assert handled['data']['action_result']

    # 帖子已进回收站
    trash = client.get('/api/v1/admin/trash', headers=auth_header(admin_token)).get_json()
    assert trash['data']['total'] == 1


def test_recycle_retention_count(client, admin_token, student_token, app):
    """回收站保留条数可配置（需求：默认保留最近 10 条）。"""
    from app.utils.config_service import get_config_int

    client.post('/api/v1/admin/trash/cleanup',
                json={'keep': 2}, headers=auth_header(admin_token))
    with app.app_context():
        assert get_config_int('recycle_retention_count', 10) == 2

    # 造 4 条已删除帖子
    for index in range(4):
        post_id = client.post('/api/v1/lost_found/posts',
                              json={'title': f'待删 {index}', 'contact': '微信 a'},
                              headers=auth_header(student_token)).get_json()['data']['id']
        client.post(f'/api/v1/admin/posts/{post_id}/audit',
                    json={'audit_status': 'approved'}, headers=auth_header(admin_token))
        client.delete(f'/api/v1/admin/posts/{post_id}', headers=auth_header(admin_token))

    trash = client.get('/api/v1/admin/trash', headers=auth_header(admin_token)).get_json()
    assert trash['data']['total'] <= 2
    assert trash['data']['retention_count'] == 2


def test_common_endpoints(client):
    enums = client.get('/api/v1/common/enums').get_json()
    assert enums['code'] == 0
    assert any(item['value'] == 'ongoing' for item in enums['data']['post_status'])

    modules = client.get('/api/v1/common/modules').get_json()
    assert modules['code'] == 0
    assert modules['data']['list'], '至少应有一个启用中的模块'

    health = client.get('/api/v1/common/health').get_json()
    assert health['data']['database'] is True

    configs = client.get('/api/v1/common/configs').get_json()
    assert 'site_name' in configs['data']


def test_favorites(client, student_token, sample_post):
    toggled = client.post(f'/api/v1/favorites/posts/{sample_post}',
                          headers=auth_header(student_token)).get_json()
    assert toggled['data']['favorited'] is True

    listing = client.get('/api/v1/favorites', headers=auth_header(student_token)).get_json()
    assert listing['data']['total'] == 1

    toggled = client.post(f'/api/v1/favorites/posts/{sample_post}',
                          headers=auth_header(student_token)).get_json()
    assert toggled['data']['favorited'] is False


def test_comment_endpoint_now_available(client, admin_token, student_token, sample_post):
    """v1.2 已开放评论：接口返回成功，且管理员评论列表能看到。"""
    response = client.post(f'/api/v1/comments/posts/{sample_post}/comments',
                           json={'content': '管理员视角可见的评论'},
                           headers=auth_header(student_token))
    assert response.status_code == 200
    body = response.get_json()
    assert body['code'] == 0, body

    listing = client.get('/api/v1/admin/comments', headers=auth_header(admin_token)).get_json()
    assert listing['code'] == 0
    assert any(item['content'] == '管理员视角可见的评论' for item in listing['data']['list'])
