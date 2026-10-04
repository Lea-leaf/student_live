# -*- coding: utf-8 -*-
"""失物招领模块测试：发布、审核、列表、详情状态规则、状态流转、回收站。"""

from tests.conftest import auth_header


def _create_post(client, token, **overrides):
    payload = {
        'title': '在图书馆丢了黑色雨伞',
        'content': '三楼自习区，伞柄有小熊挂件',
        'location': '图书馆三楼',
        'contact': '微信 xiaoming2021',
    }
    payload.update(overrides)
    return client.post('/api/v1/lost_found/posts', json=payload, headers=auth_header(token))


def test_create_requires_login(client):
    response = client.post('/api/v1/lost_found/posts', json={'contact': 'x'})
    assert response.status_code == 401


def test_create_requires_contact(client, student_token):
    """联系方式必填（需求 6.1）。"""
    response = client.post('/api/v1/lost_found/posts',
                           json={'title': '丢了东西'},
                           headers=auth_header(student_token))
    assert response.get_json()['code'] == 1001


def test_create_needs_audit_then_visible_after_approve(client, student_token, admin_token):
    """发布 → 待审核（公开列表不可见）→ 管理员通过 → 公开可见。"""
    created = _create_post(client, student_token).get_json()
    assert created['code'] == 0, created
    post_id = created['data']['id']
    assert created['data']['audit_status'] == 'pending'

    # 未审核：公开列表看不到
    listing = client.get('/api/v1/lost_found/posts').get_json()
    assert listing['data']['total'] == 0

    # 作者自己在「我的发布」里能看到
    mine = client.get('/api/v1/lost_found/my/posts', headers=auth_header(student_token)).get_json()
    assert mine['data']['total'] == 1

    # 管理员审核通过
    audited = client.post(f'/api/v1/admin/posts/{post_id}/audit',
                          json={'audit_status': 'approved', 'remark': '内容合规'},
                          headers=auth_header(admin_token)).get_json()
    assert audited['code'] == 0, audited

    listing = client.get('/api/v1/lost_found/posts').get_json()
    assert listing['data']['total'] == 1
    assert listing['data']['list'][0]['id'] == post_id


def test_ext_json_roundtrip_and_validation(client, student_token):
    """P3 前置：ext_json 写入链路必须可校验、可回读。"""
    ext = {'price': 120, 'condition': '九成新', 'trade_type': '面交'}
    created = _create_post(client, student_token, title='二手测试', ext=ext).get_json()
    assert created['code'] == 0, created
    assert created['data']['ext'] == ext

    # 非对象 / 超大 ext 都应在接口层被拒绝，而不是写坏数据库
    bad = _create_post(client, student_token, title='非法 ext', ext=['not', 'dict']).get_json()
    assert bad['code'] == 1001
    huge = _create_post(client, student_token, title='超大 ext',
                        ext={'blob': 'x' * 5000}).get_json()
    assert huge['code'] == 1001


def test_reject_sends_notification(client, student_token, admin_token):
    post_id = _create_post(client, student_token).get_json()['data']['id']
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'rejected', 'remark': '缺少物品特征'},
                headers=auth_header(admin_token))

    notifications = client.get('/api/v1/notifications', headers=auth_header(student_token)).get_json()
    assert notifications['data']['total'] == 1
    assert notifications['data']['list'][0]['type'] == 'audit'


def test_guest_can_list_but_not_detail(client, sample_post):
    """游客策略（需求待定项 1）：可浏览列表，不能查看详情。"""
    listing = client.get('/api/v1/lost_found/posts')
    assert listing.get_json()['code'] == 0

    detail = client.get(f'/api/v1/lost_found/posts/{sample_post}')
    assert detail.status_code == 401
    assert detail.get_json()['code'] == 2003


def test_detail_increments_view(client, student2_token, sample_post):
    """浏览量统计：非作者查看才计数（作者/管理员查看不计数）。"""
    first = client.get(f'/api/v1/lost_found/posts/{sample_post}',
                       headers=auth_header(student2_token)).get_json()
    assert first['code'] == 0
    assert first['data']['view_count'] == 1


def test_status_rules_claimed_and_closed(client, student_token, student2_token, sample_post):
    """状态规则（需求 6.2）：已认领在列表中可见但详情不可点；已关闭不进公开列表。"""
    claimed = client.post(f'/api/v1/lost_found/posts/{sample_post}/claim',
                          headers=auth_header(student_token)).get_json()
    assert claimed['code'] == 0
    assert claimed['data']['status'] == 'claimed'

    # 列表仍可见
    listing = client.get('/api/v1/lost_found/posts').get_json()
    assert listing['data']['total'] == 1
    assert listing['data']['list'][0]['status'] == 'claimed'

    # 其他普通用户看不到详情（作者本人与管理员仍可查看）
    detail = client.get(f'/api/v1/lost_found/posts/{sample_post}', headers=auth_header(student2_token))
    assert detail.get_json()['code'] == 4002

    # 关闭后不进公开列表
    closed = client.post(f'/api/v1/lost_found/posts/{sample_post}/status',
                         json={'status': 'closed'}, headers=auth_header(student_token)).get_json()
    assert closed['code'] == 0
    listing = client.get('/api/v1/lost_found/posts').get_json()
    assert listing['data']['total'] == 0


def test_invalid_status_transition(client, app, student_token, sample_post):
    """非法状态流转被 service 层拦住（这里是单元级断言，避免作者权限干扰）。"""
    from app.extensions import db
    from app.models import Post
    from app.modules import posts_service as svc
    from app.utils.validators import ValidationError

    with app.app_context():
        post = Post.query.get(sample_post)
        # ongoing → closed 合法
        assert svc.can_transition('ongoing', 'closed') is True
        # closed → claimed 非法
        assert svc.can_transition('closed', 'claimed') is False
        post.status = 'closed'
        db.session.commit()
        try:
            svc.apply_status(post, 'claimed')
            raise AssertionError('非法流转应抛出 ValidationError')
        except ValidationError as exc:
            assert exc.code == 4004


def test_invalid_status_value(client, student_token, sample_post):
    response = client.post(f'/api/v1/lost_found/posts/{sample_post}/status',
                           json={'status': '不存在的状态'}, headers=auth_header(student_token))
    assert response.get_json()['code'] == 1001


def test_cannot_edit_others_post(client, student2_token, sample_post):
    """越权：不能编辑 / 删除他人的帖子。"""
    response = client.put(f'/api/v1/lost_found/posts/{sample_post}',
                          json={'title': '篡改'}, headers=auth_header(student2_token))
    assert response.get_json()['code'] == 2003

    response = client.delete(f'/api/v1/lost_found/posts/{sample_post}',
                             headers=auth_header(student2_token))
    assert response.get_json()['code'] == 2003


def test_edit_resets_audit_status(client, student_token, sample_post):
    """已通过的帖子被作者编辑后重新进入待审核。"""
    response = client.put(f'/api/v1/lost_found/posts/{sample_post}',
                          json={'title': '改了标题'}, headers=auth_header(student_token)).get_json()
    assert response['code'] == 0
    assert response['data']['audit_status'] == 'pending'


def test_search_and_filter(client, student_token, admin_token):
    _create_post(client, student_token, title='丢失校园卡', location='二食堂')
    created = _create_post(client, student_token, title='丢失雨伞', location='图书馆')
    post_id = created.get_json()['data']['id']
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))
    # 第二条也审核通过
    first_id = client.get('/api/v1/lost_found/my/posts',
                          headers=auth_header(student_token)).get_json()['data']['list'][-1]['id']
    client.post(f'/api/v1/admin/posts/{first_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    listing = client.get('/api/v1/lost_found/posts?keyword=雨伞').get_json()
    assert listing['data']['total'] == 1
    assert '雨伞' in listing['data']['list'][0]['title']

    listing = client.get('/api/v1/lost_found/posts?keyword=图书馆').get_json()
    assert listing['data']['total'] == 1


def test_pagination(client, student_token, admin_token):
    for index in range(3):
        post_id = _create_post(client, student_token, title=f'测试 {index}').get_json()['data']['id']
        client.post(f'/api/v1/admin/posts/{post_id}/audit',
                    json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    page1 = client.get('/api/v1/lost_found/posts?page=1&size=2').get_json()
    assert page1['data']['total'] == 3
    assert len(page1['data']['list']) == 2
    assert page1['data']['pages'] == 2

    page2 = client.get('/api/v1/lost_found/posts?page=2&size=2').get_json()
    assert len(page2['data']['list']) == 1


def test_delete_goes_to_recycle_bin(client, student_token, admin_token, sample_post):
    """软删除：用户看不到，管理员在回收站能看到并恢复。"""
    response = client.delete(f'/api/v1/lost_found/posts/{sample_post}',
                             headers=auth_header(student_token)).get_json()
    assert response['code'] == 0

    assert client.get('/api/v1/lost_found/posts').get_json()['data']['total'] == 0

    trash = client.get('/api/v1/admin/trash', headers=auth_header(admin_token)).get_json()
    assert trash['data']['total'] == 1

    restored = client.post(f'/api/v1/admin/trash/{sample_post}/restore',
                           headers=auth_header(admin_token)).get_json()
    assert restored['code'] == 0
    assert client.get('/api/v1/lost_found/posts').get_json()['data']['total'] == 1


def test_second_hand_ext_flow(client, student_token, admin_token):
    """P3 验证：二手交易的 ext_json 真实落库、按 type 列表、详情回读、必填校验。"""
    ext = {'price': 388.5, 'original_price': 599, 'condition': '九成新', 'trade_type': '面交'}
    created = client.post(
        '/api/v1/lost_found/posts',
        json={'type': 'second_hand', 'title': '出二手显示器', 'content': '27 寸 2K，无坏点',
              'contact': '微信 screen', 'happened_at': '2026-12-01 10:00:00', 'ext': ext},
        headers=auth_header(student_token),
    ).get_json()
    assert created['code'] == 0, created
    post_id = created['data']['id']
    assert created['data']['type'] == 'second_hand'
    assert created['data']['ext'] == ext
    assert created['data']['status_label'] == '在售中'

    # 缺交易时间 / 缺价格都必须被接口层拒绝
    no_time = client.post(
        '/api/v1/lost_found/posts',
        json={'type': 'second_hand', 'title': '没写交易时间', 'contact': '微信 x',
              'ext': {'price': 10}},
        headers=auth_header(student_token),
    ).get_json()
    assert no_time['code'] == 1001

    bad = client.post(
        '/api/v1/lost_found/posts',
        json={'type': 'second_hand', 'title': '没写价格', 'contact': '微信 x',
              'ext': {'condition': '全新'}},
        headers=auth_header(student_token),
    ).get_json()
    assert bad['code'] == 1001

    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    # 按模块筛选：二手交易列表能看到，失物招领列表看不到
    second_list = client.get('/api/v1/lost_found/posts?type=second_hand').get_json()
    assert any(item['id'] == post_id for item in second_list['data']['list'])
    assert all(item['type'] == 'second_hand' for item in second_list['data']['list'])
    lost_list = client.get('/api/v1/lost_found/posts').get_json()
    assert all(item['id'] != post_id for item in lost_list['data']['list'])

    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student_token)).get_json()
    assert detail['data']['ext']['price'] == 388.5

    # 二手交易下 claimed 的显示文案应为「已售出」
    claimed = client.post(f'/api/v1/lost_found/posts/{post_id}/claim',
                          headers=auth_header(student_token)).get_json()
    assert claimed['code'] == 0, claimed
    assert claimed['data']['status_label'] == '已售出'
    assert '已售出' in claimed['msg']

    meta = client.get('/api/v1/lost_found/meta?type=second_hand').get_json()
    assert meta['data']['module'] == 'second_hand'
    assert 'price' in meta['data']['fields']
    assert dict((item['value'], item['label'])
                for item in meta['data']['statuses'])['claimed'] == '已售出'


def test_module_meta(client):
    body = client.get('/api/v1/lost_found/meta').get_json()
    assert body['code'] == 0
    assert body['data']['fields']['contact']['required'] is True
    assert body['data']['fields']['contact']['public'] is True
