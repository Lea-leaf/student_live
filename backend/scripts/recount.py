# -*- coding: utf-8 -*-
"""计数对账脚本：重算帖子 / 评论的冗余计数并报告差异。

用法（在 backend 目录下）：

    python scripts/recount.py            # 只检查并报告，不修改数据库
    python scripts/recount.py --fix      # 把漂移的计数写回数据库
    python scripts/recount.py --json     # 输出 JSON，便于其他脚本消费

覆盖字段：
    posts.comment_count     comments 中 is_deleted=False 的行数（含楼中楼）
    posts.like_count        post_likes 实际行数
    posts.favorite_count    favorites 实际行数
    comments.like_count     comment_likes 实际行数
    comments.reply_count    直接子回复中 is_deleted=False 的行数

说明：view_count 没有独立的行为日志，无法从其他表反推；
      本脚本只检查它是否为负数，为负时用 --fix 归零。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Comment, CommentLike, Favorite, Post, PostLike  # noqa: E402


def _stored(value):
    return int(value or 0)


def recount_posts(fix=False):
    """重算所有帖子计数，返回 (漂移报告, 检查数量, 漂移数量)。"""
    reports = []
    for post in Post.query.order_by(Post.id.asc()).all():
        actual = {
            'comment_count': Comment.query.filter_by(post_id=post.id, is_deleted=False).count(),
            'like_count': PostLike.query.filter_by(post_id=post.id).count(),
            'favorite_count': Favorite.query.filter_by(post_id=post.id).count(),
        }
        diffs = {}
        for field, actual_value in actual.items():
            stored_value = _stored(getattr(post, field))
            if stored_value != actual_value:
                diffs[field] = {'stored': stored_value, 'actual': actual_value}

        # view_count 无事件日志可反推，只做合法性检查
        stored_views = _stored(post.view_count)
        if stored_views < 0:
            diffs['view_count'] = {'stored': stored_views, 'actual': 0}

        if diffs:
            reports.append({
                'id': post.id,
                'title': post.title or (post.content or '')[:30],
                'diffs': diffs,
            })

        if fix:
            if post.comment_count != actual['comment_count']:
                post.comment_count = actual['comment_count']
            if post.like_count != actual['like_count']:
                post.like_count = actual['like_count']
            if post.favorite_count != actual['favorite_count']:
                post.favorite_count = actual['favorite_count']
            if stored_views < 0:
                post.view_count = 0

    return reports


def recount_comments(fix=False):
    """重算所有未删除评论的点赞数 / 直接回复数，返回漂移报告。"""
    reports = []
    comments = Comment.query.filter_by(is_deleted=False).order_by(Comment.id.asc()).all()
    for comment in comments:
        actual_like = CommentLike.query.filter_by(comment_id=comment.id).count()
        actual_reply = Comment.query.filter_by(parent_id=comment.id, is_deleted=False).count()

        diffs = {}
        if _stored(comment.like_count) != actual_like:
            diffs['like_count'] = {'stored': _stored(comment.like_count), 'actual': actual_like}
        if _stored(comment.reply_count) != actual_reply:
            diffs['reply_count'] = {'stored': _stored(comment.reply_count), 'actual': actual_reply}

        if diffs:
            reports.append({
                'id': comment.id,
                'post_id': comment.post_id,
                'content': (comment.content or '')[:30],
                'diffs': diffs,
            })

        if fix:
            if comment.like_count != actual_like:
                comment.like_count = actual_like
            if comment.reply_count != actual_reply:
                comment.reply_count = actual_reply

    return reports


def recount_all(fix=False):
    """执行全量对账，返回结构化报告；fix=True 时写回数据库。"""
    post_reports = recount_posts(fix=fix)
    comment_reports = recount_comments(fix=fix)
    if fix:
        db.session.commit()

    return {
        'posts': post_reports,
        'comments': comment_reports,
        'summary': {
            'post_checked': Post.query.count(),
            'comment_checked': Comment.query.filter_by(is_deleted=False).count(),
            'post_drift': len(post_reports),
            'comment_drift': len(comment_reports),
        },
        'note': 'view_count 没有独立行为日志，只做非负校验；其余计数均可从关联表重算。',
    }


def _print_report(report):
    summary = report['summary']
    print('=' * 72)
    print('计数对账报告')
    print('=' * 72)
    if not report['posts'] and not report['comments']:
        print('   所有计数一致，未发现漂移')
    else:
        for item in report['posts']:
            print(f"  [帖子 #{item['id']}] {item['title']}")
            for field, diff in item['diffs'].items():
                print(f"      {field}: 数据库={diff['stored']}  实际={diff['actual']}")
        for item in report['comments']:
            print(f"  [评论 #{item['id']}  帖子 {item['post_id']}] {item['content']}")
            for field, diff in item['diffs'].items():
                print(f"      {field}: 数据库={diff['stored']}  实际={diff['actual']}")

    print('-' * 72)
    print(f"检查：帖子 {summary['post_checked']} 条，评论 {summary['comment_checked']} 条")
    print(f"漂移：帖子 {summary['post_drift']} 条，评论 {summary['comment_drift']} 条")
    print(f"说明：{report['note']}")
    print('=' * 72)


def main():
    parser = argparse.ArgumentParser(description='重算帖子 / 评论冗余计数并对账')
    parser.add_argument('--fix', action='store_true', help='把不一致的计数写回数据库')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式报告')
    args = parser.parse_args()

    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    with app.app_context():
        report = recount_all(fix=args.fix)
        if args.json:
            report['fixed'] = bool(args.fix)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_report(report)
            if args.fix:
                print('已执行 --fix：漂移计数已写回数据库。')
            elif report['posts'] or report['comments']:
                print('提示：加 --fix 可自动修正这些计数。')

        has_drift = bool(report['posts'] or report['comments'])
        return 0 if (not has_drift or args.fix) else 1


if __name__ == '__main__':
    sys.exit(main())