# -*- coding: utf-8 -*-
"""v1.5 新模块测试：拼单 / 跑腿 / 日常。"""

from tests.conftest import auth_header


def _enable_module(client, admin_token, code):
    modules = client.get('/api/v1/admin/modules', headers=auth_header(admin_token)).get_json()
    row = next(item for item in modules['data']['list'] if item['code'] == code)
    response = client.post(f"/api/v1/admin/modules/{row['id']}/toggle",
                           json={'enabled': True}, headers=auth_header(admin_token))
    assert response.get_json()['code'] == 0


def _create(client, token, **payload):
    return client.post('/api/v1/lost_found/posts', json=payload,
                       headers=auth_header(token))


def _approve(client, admin_token, post_id):
    response = client.post(f'/api/v1/admin/posts/{post_id}/audit',
                           json={'audit_status': 'approved'}, headers=auth_header(admin_token))
    assert response.get_json()['code'] == 0


def _group_payload(target=5, current=2, start='2026-12-01'):
    return {'target_count': target, 'current_count': current, 'start_date': start}


def test_daily_publish_contact_optional(client, admin_token, student_token, student2_token):
    _enable_module(client, admin_token, 'daily')
    created = _create(client, student_token, type='daily', title='食堂新菜',
                      content='麻辣香锅挺好吃').get_json()
    assert created['code'] == 0, created
    post_id = created['data']['id']
    assert created['data']['type'] == 'daily'
    assert created['data']['contact'] == ''
    assert created['data']['ext'] == {}

    _approve(client, admin_token, post_id)
    listing = client.get('/api/v1/lost_found/posts?type=daily').get_json()
    assert any(item['id'] == post_id for item in listing['data']['list'])
    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student2_token)).get_json()
    assert detail['code'] == 0
    assert detail['data']['status_label'] == '正常'


def test_errand_requires_contact_and_time(client, admin_token, student_token):
    _enable_module(client, admin_token, 'errand')
    no_contact = _create(client, student_token, type='errand', title='帮取快递').get_json()
    assert no_contact['code'] == 1001

    no_time = _create(client, student_token, type='errand', title='帮取快递',
                      contact='微信 a').get_json()
    assert no_time['code'] == 1001

    created = _create(client, student_token, type='errand', title='帮取快递',
                      contact='微信 a', happened_at='2026-12-01 10:00:00').get_json()
    assert created['code'] == 0, created
    assert created['data']['type'] == 'errand'
    assert created['data']['happened_at'] == '2026-12-01 10:00:00'


def test_group_buy_ext_validation(client, admin_token, student_token):
    _enable_module(client, admin_token, 'group_buy')

    missing = _create(client, student_token, type='group_buy', title='拼奶茶',
                      ext={'current_count': 1, 'start_date': '2026-12-01'}).get_json()
    assert missing['code'] == 1001  # 缺 target_count

    bad_range = _create(client, student_token, type='group_buy', title='拼奶茶',
                        ext={'target_count': 0, 'current_count': 1,
                             'start_date': '2026-12-01'}).get_json()
    assert bad_range['code'] == 1001

    bad_date = _create(client, student_token, type='group_buy', title='拼奶茶',
                       ext={'target_count': 5, 'current_count': 1,
                            'start_date': '2026-13-99'}).get_json()
    assert bad_date['code'] == 1001

    valid = _create(client, student_token, type='group_buy', title='拼奶茶',
                    ext=_group_payload()).get_json()
    assert valid['code'] == 0, valid
    assert valid['data']['ext'] == {
        'target_count': 5, 'current_count': 2, 'start_date': '2026-12-01'
    }
    assert valid['data']['status_label'] == '招募中'


def test_group_buy_count_endpoint(client, admin_token, student_token, student2_token,
                                  sample_post):
    _enable_module(client, admin_token, 'group_buy')
    post_id = _create(client, student_token, type='group_buy', title='拼奶茶',
                      ext=_group_payload()).get_json()['data']['id']

    forbidden = client.patch(f'/api/v1/lost_found/posts/{post_id}/count',
                             json={'current_count': 3}, headers=auth_header(student2_token))
    assert forbidden.status_code == 403

    updated = client.patch(f'/api/v1/lost_found/posts/{post_id}/count',
                           json={'current_count': 6, 'target_count': 5},
                           headers=auth_header(student_token)).get_json()
    assert updated['code'] == 0, updated
    assert updated['data']['ext']['current_count'] == 6
    assert updated['data']['ext']['target_count'] == 5

    lost = client.patch(f'/api/v1/lost_found/posts/{sample_post}/count',
                        json={'current_count': 3},
                        headers=auth_header(student_token)).get_json()
    assert lost['code'] == 1001

    second_id = _create(client, student_token, type='second_hand', title='二手测试',
                        contact='微信 a', happened_at='2026-12-01 10:00:00',
                        ext={'price': 10}).get_json()['data']['id']
    second = client.patch(f'/api/v1/lost_found/posts/{second_id}/count',
                          json={'current_count': 3},
                          headers=auth_header(student_token)).get_json()
    assert second['code'] == 1001


def test_group_buy_detail_visible_after_finished(client, admin_token,
                                                 student_token, student2_token):
    _enable_module(client, admin_token, 'group_buy')
    post_id = _create(client, student_token, type='group_buy', title='拼奶茶',
                      ext=_group_payload()).get_json()['data']['id']
    _approve(client, admin_token, post_id)

    changed = client.post(f'/api/v1/lost_found/posts/{post_id}/status',
                          json={'status': 'claimed'},
                          headers=auth_header(student_token)).get_json()
    assert changed['code'] == 0, changed
    assert changed['data']['status_label'] == '已结束'
    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student2_token)).get_json()
    assert detail['code'] == 0, detail

    closed = client.post(f'/api/v1/lost_found/posts/{post_id}/status',
                         json={'status': 'closed'},
                         headers=auth_header(student_token)).get_json()
    assert closed['code'] == 0
    listing = client.get('/api/v1/lost_found/posts?type=group_buy').get_json()
    assert all(item['id'] != post_id for item in listing['data']['list'])


def test_meta_status_subset_and_contact_required(client, admin_token):
    _enable_module(client, admin_token, 'group_buy')
    _enable_module(client, admin_token, 'errand')
    _enable_module(client, admin_token, 'daily')

    daily = client.get('/api/v1/lost_found/meta?type=daily').get_json()['data']
    assert [item['value'] for item in daily['statuses']] == ['ongoing', 'closed']
    assert len({item['label'] for item in daily['statuses']}) == 2
    assert daily['fields']['contact']['required'] is False

    group = client.get('/api/v1/lost_found/meta?type=group_buy').get_json()['data']
    assert [item['value'] for item in group['statuses']] == ['ongoing', 'claimed', 'closed']
    assert group['fields']['contact']['required'] is False
    assert group['fields']['target_count']['required'] is True

    errand = client.get('/api/v1/lost_found/meta?type=errand').get_json()['data']
    assert errand['fields']['contact']['required'] is True

    lost = client.get('/api/v1/lost_found/meta?type=lost_found').get_json()['data']
    assert len(lost['statuses']) == 4
    assert lost['fields']['contact']['required'] is True


def test_group_buy_like_is_intent_only(client, admin_token, student_token, student2_token):
    _enable_module(client, admin_token, 'group_buy')
    post_id = _create(client, student_token, type='group_buy', title='拼奶茶',
                      ext=_group_payload()).get_json()['data']['id']
    _approve(client, admin_token, post_id)

    liked = client.post(f'/api/v1/likes/posts/{post_id}',
                        headers=auth_header(student2_token)).get_json()
    assert liked['code'] == 0
    assert liked['data']['like_count'] == 1

    state = client.get(f'/api/v1/likes/posts/{post_id}',
                       headers=auth_header(student2_token)).get_json()
    assert state['data']['liked'] is True
    assert state['data']['users'] == []  # 非作者 / 非管理员看不到意向名单

    author_state = client.get(f'/api/v1/likes/posts/{post_id}',
                              headers=auth_header(student_token)).get_json()
    assert len(author_state['data']['users']) == 1

    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student_token)).get_json()
    assert detail['data']['like_count'] == 1
    assert detail['data']['ext']['current_count'] == 2


__all__ = []