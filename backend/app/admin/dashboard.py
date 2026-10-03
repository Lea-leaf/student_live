# -*- coding: utf-8 -*-
"""管理端 - 首页统计。

需求：管理员首页展示 用户总数、帖子总数、今日新增、待审核数量。
额外提供 7 日趋势、模块分布、最近待审核列表，便于毕设答辩演示。
"""

from datetime import datetime, timedelta

from flask import Blueprint

from ..extensions import db
from ..models import Comment, LoginLog, Module, Post, Report, User
from ..utils.auth import admin_required
from ..utils.constants import AUDIT_PENDING, REPORT_PENDING, STATUS_BANNED
from ..utils.response import success

bp = Blueprint('admin_dashboard', __name__)


def _today_start():
    now = datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@bp.get('/dashboard/overview')
@admin_required
def overview():
    """统计卡片数据。"""
    today = _today_start()

    stats = {
        'user_total': User.query.count(),
        'user_today': User.query.filter(User.created_at >= today).count(),
        'user_banned': User.query.filter_by(status=STATUS_BANNED).count(),
        'post_total': Post.query.filter(Post.is_deleted.is_(False)).count(),
        'post_today': Post.query.filter(Post.created_at >= today, Post.is_deleted.is_(False)).count(),
        'post_pending': Post.query.filter(
            Post.audit_status == AUDIT_PENDING, Post.is_deleted.is_(False)
        ).count(),
        'comment_total': Comment.query.filter_by(is_deleted=False).count(),
        'recycle_total': Post.query.filter(Post.is_deleted.is_(True)).count(),
        'report_pending': Report.query.filter_by(status=REPORT_PENDING).count(),
        'login_today': LoginLog.query.filter(LoginLog.created_at >= today, LoginLog.success.is_(True)).count(),
    }
    return success(stats)


@bp.get('/dashboard/trend')
@admin_required
def trend():
    """近 7 天新增趋势（发帖 / 注册）。

    查询参数：days（默认 7，最大 30）
    """
    from ..utils.validators import ValidationError, as_error, get_int

    try:
        days = get_int('days', 7, minimum=1, maximum=30, source='args')
        today = _today_start()
        labels, post_series, user_series = [], [], []
        for offset in range(days - 1, -1, -1):
            start = today - timedelta(days=offset)
            end = start + timedelta(days=1)
            labels.append(start.strftime('%m-%d'))
            post_series.append(Post.query.filter(
                Post.created_at >= start, Post.created_at < end, Post.is_deleted.is_(False)
            ).count())
            user_series.append(User.query.filter(
                User.created_at >= start, User.created_at < end
            ).count())
        return success({'labels': labels, 'posts': post_series, 'users': user_series})
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/dashboard/module-stats')
@admin_required
def module_stats():
    """各模块帖子数量分布。"""
    rows = (
        db.session.query(Post.type, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(False))
        .group_by(Post.type)
        .all()
    )
    names = {item.code: item.name for item in Module.query.all()}
    data = [
        {'type': code, 'name': names.get(code, code), 'count': count}
        for code, count in rows
    ]
    data.sort(key=lambda item: item['count'], reverse=True)
    return success({'list': data})


@bp.get('/dashboard/pending')
@admin_required
def pending_list():
    """最近待审核帖子（首页快捷入口）。"""
    from ..utils.validators import get_int

    limit = get_int('limit', 10, minimum=1, maximum=50, source='args')
    rows = (
        Post.query.filter(Post.audit_status == AUDIT_PENDING, Post.is_deleted.is_(False))
        .order_by(Post.id.desc())
        .limit(limit)
        .all()
    )
    return success({'list': [item.to_dict() for item in rows], 'total': len(rows)})


@bp.get('/dashboard/media')
@admin_required
def media_storage():
    """媒体存储用量：按用户目录统计磁盘占用。

    配合「数据按用户分目录存放」的设计，管理员可以在这里看清
    每个用户占了多少空间，也便于发现异常占用。
    """
    from ..utils.cleanup import media_orphan_files
    from ..utils.uploads import media_stats

    stats = media_stats()
    orphans = media_orphan_files()

    # 把目录名（学号）关联到用户名，便于阅读
    dir_names = [item['dir'] for item in stats['dirs']]
    users = {
        user.student_id: user.to_brief()
        for user in User.query.filter(User.student_id.in_(dir_names)).all()
    } if dir_names else {}
    for item in stats['dirs']:
        brief = users.get(item['dir'])
        item['user'] = brief
        item['display'] = brief['display_name'] if brief else item['dir']

    return success({
        'root_files': stats['files'],
        'root_bytes': stats['bytes'],
        'users': stats['dirs'],
        'orphan_files': orphans[:50],
        'orphan_count': len(orphans),
    })
