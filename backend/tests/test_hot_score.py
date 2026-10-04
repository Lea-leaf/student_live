# -*- coding: utf-8 -*-
"""热度排序测试。"""

from datetime import datetime, timedelta


def test_hot_score_formula_and_decay():
    from app.models import Post
    from app.utils.hot_score import hot_score

    now = datetime.now()
    fresh = Post(view_count=10, comment_count=2, like_count=5, favorite_count=1,
                 created_at=now)
    # 101 + 23 + 52 + 12 = 28
    assert hot_score(fresh, now=now) == 28.0

    old = Post(view_count=10, comment_count=2, like_count=5, favorite_count=1,
               created_at=now - timedelta(hours=24))
    # 24 小时后衰减为一半
    assert hot_score(old, now=now) == 14.0


def test_hot_sort_endpoint_uses_weighted_score(client, app, student, sample_post):
    from app.extensions import db
    from app.models import Post

    with app.app_context():
        first = Post.query.get(sample_post)
        first.created_at = datetime.now() - timedelta(days=2)
        first.view_count = 100
        first.comment_count = 0
        first.like_count = 0
        first.favorite_count = 0
        second = Post(type='lost_found', user_id=student, title='互动更多的新帖',
                      content='评论和点赞更多', contact='微信 hot',
                      audit_status='approved', status='ongoing',
                      view_count=1, comment_count=10, like_count=5,
                      favorite_count=2)
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    listing = client.get('/api/v1/lost_found/posts?sort=hot&size=10').get_json()
    assert listing['code'] == 0
    assert listing['data']['list'][0]['id'] == second_id


__all__ = []