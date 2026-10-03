# -*- coding: utf-8 -*-
"""帖子序列化字段完整性测试。

**为什么单独测这个**：曾经漏掉 `to_brief()` 里的 `like_count`，
列表接口不报错、但前端拿到的点赞数是 `undefined`——这种「静默缺字段」
只能靠显式断言字段清单来防。
"""

from tests.conftest import auth_header


#: 列表卡片（to_brief）必须包含的字段
BRIEF_FIELDS = [
    'id', 'type', 'title', 'content', 'media', 'location', 'happened_at',
    'status', 'status_label', 'audit_status', 'is_top',
    'view_count', 'comment_count', 'favorite_count', 'like_count',
    'created_at', 'author', 'module_name',
]

#: 详情（to_dict）必须包含的字段
#: 注意：module_name 只在 to_brief() 里（列表卡片显示模块名用）；
#: 详情页用 type + 前端字典映射模块名，因此不在此列。
DETAIL_FIELDS = [f for f in BRIEF_FIELDS if f != 'module_name'] + [
    'contact', 'audit_status_label', 'audit_remark', 'ext',
    'is_deleted', 'user_id', 'updated_at',
]


def test_brief_contains_all_list_fields(app, sample_post):
    """列表序列化必须带齐所有卡片要用的字段（含点赞与收藏计数）。"""
    from app.models import Post

    with app.app_context():
        post = Post.query.get(sample_post)
        brief = post.to_brief()
        missing = [f for f in BRIEF_FIELDS if f not in brief]
        assert missing == [], f'to_brief() 缺少字段：{missing}'


def test_detail_contains_all_fields(app, sample_post):
    """详情序列化必须带齐所有字段。"""
    from app.models import Post

    with app.app_context():
        detail = Post.query.get(sample_post).to_dict()
        missing = [f for f in DETAIL_FIELDS if f not in detail]
        assert missing == [], f'to_dict() 缺少字段：{missing}'


def test_counts_are_numbers_not_none(app, sample_post):
    """三个计数必须是数字（前端直接参与运算，None 会显示成 NaN）。"""
    from app.models import Post

    with app.app_context():
        post = Post.query.get(sample_post)
        for field in ('like_count', 'favorite_count', 'comment_count', 'view_count'):
            value = post.to_brief()[field]
            assert isinstance(value, int), f'{field} 应为 int，实际 {type(value).__name__}: {value}'
            assert post.to_dict()[field] == value


def test_list_api_returns_counts(client, app, student_token, admin_token):
    """端到端：列表接口返回的每条数据都要有点赞/收藏/评论计数。"""
    post_id = client.post('/api/v1/lost_found/posts',
                          json={'title': '计数测试', 'contact': '微信 a'},
                          headers=auth_header(student_token)).get_json()['data']['id']
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved'}, headers=auth_header(admin_token))

    listing = client.get('/api/v1/lost_found/posts?page=1&size=50').get_json()
    assert listing['code'] == 0
    rows = listing['data']['list']
    assert rows, '列表不应为空'
    for row in rows:
        for field in ('like_count', 'favorite_count', 'comment_count', 'view_count'):
            assert field in row, f'列表项缺少 {field}'
            assert row[field] is not None, f'列表项 {field} 为 None'

    # 详情接口同样检查
    detail = client.get(f'/api/v1/lost_found/posts/{post_id}',
                        headers=auth_header(student_token)).get_json()['data']
    for field in ('like_count', 'favorite_count', 'comment_count'):
        assert detail.get(field) == 0
