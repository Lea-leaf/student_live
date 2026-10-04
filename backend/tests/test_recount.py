# -*- coding: utf-8 -*-
"""计数对账脚本测试：报告漂移 + --fix 回写。"""

from datetime import datetime


def test_recount_detects_and_fixes_drift(app, student, student2, sample_post):
    from app.extensions import db
    from app.models import Comment, CommentLike, Favorite, Post, PostLike
    from scripts.recount import recount_all

    with app.app_context():
        post = Post.query.get(sample_post)
        post.comment_count = 99
        post.like_count = 99
        post.favorite_count = 99
        post.view_count = -5

        top = Comment(post_id=sample_post, user_id=student2, content='顶级评论')
        db.session.add(top)
        db.session.flush()
        top.root_id = top.id
        reply = Comment(post_id=sample_post, user_id=student, content='子回复',
                        parent_id=top.id, root_id=top.id)
        db.session.add(reply)
        db.session.add(PostLike(user_id=student2, post_id=sample_post))
        db.session.add(Favorite(user_id=student2, post_id=sample_post))
        db.session.add(CommentLike(user_id=student, comment_id=top.id))
        top.like_count = 0
        top.reply_count = 0
        db.session.commit()

        report = recount_all(fix=False)
        assert report['summary']['post_drift'] >= 1
        assert report['summary']['comment_drift'] >= 1
        assert any('comment_count' in item['diffs'] for item in report['posts'])
        assert any('reply_count' in item['diffs'] for item in report['comments'])

        recount_all(fix=True)

        post = Post.query.get(sample_post)
        assert post.comment_count == 2
        assert post.like_count == 1
        assert post.favorite_count == 1
        assert post.view_count == 0

        top = Comment.query.filter_by(post_id=sample_post, parent_id=None).first()
        assert top.like_count == 1
        assert top.reply_count == 1


__all__ = []