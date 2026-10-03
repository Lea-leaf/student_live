# -*- coding: utf-8 -*-
"""管理端 - 回收站。

需求：软删除帖子仅管理员可见，默认保留最近 10 条，数量可配置。

实现：
- 软删除通过 `posts.is_deleted` 标记，普通用户完全看不到；
- `posts_service.purge_overflow()` 在每次删除后按配置自动清理超出部分；
- 保留条数与超量处理方式在「系统配置」里改（recycle_retention_count / recycle_retention_mode）。
"""

from flask import Blueprint, request

from ..extensions import db
from ..models import Post, UploadFile, User
from ..models.base import paginate
from ..utils.auth import admin_required
from ..utils.config_service import get_config, get_config_int
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import paginated, success
from ..utils.validators import ValidationError, as_error, get_json, parse_int_list
from ..modules import posts_service as svc

bp = Blueprint('admin_trash', __name__, url_prefix='/trash')


@bp.get('')
@admin_required
def list_trash():
    """回收站列表（按删除时间倒序）。参数：page / size / type / keyword。"""
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        post_type = (request.args.get('type') or '').strip() or None
        query = svc.recycle_bin_query(post_type)
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(Post.title.like(like), Post.content.like(like),
                                        Post.contact.like(like)))
        items, total, page, size = paginate(query, page, size)
        data = []
        for post in items:
            item = post.to_dict()
            deleter = User.query.get(post.deleted_by) if post.deleted_by else None
            item['deleted_by_user'] = deleter.to_brief() if deleter else None
            data.append(item)
        limit = get_config_int('recycle_retention_count', 10)
        return paginated(data, total, page, size,
                         extra={'retention_count': limit,
                                'retention_mode': get_config('recycle_retention_mode', 'force')})
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:post_id>/restore')
@admin_required
def restore_post(post_id):
    """从回收站恢复。"""
    try:
        post = Post.query.filter_by(id=post_id, is_deleted=True).first()
        if post is None:
            raise ValidationError('回收站中没有该帖子', 4001)
        post.restore()
        db.session.commit()
        write_operation_log('restore', module=post.type, target_type='post', target_id=post.id)
        send(post.user_id, '你的信息已恢复', f'《{post.title or "无标题"}》已被管理员恢复。',
             notify_type='system', ref_id=post.id)
        return success(post.to_dict(), msg='已恢复')
    except ValidationError as exc:
        return as_error(exc)


@bp.delete('/<int:post_id>')
@admin_required
def purge_post(post_id):
    """彻底删除（不可恢复）。

    通过 `utils.cleanup.purge_post()` 级联清理，确保不留下孤儿指针与孤儿文件：
        媒体记录 + 磁盘文件 + 该帖的评论 + 收藏，举报记录保留但解除引用。
    """
    try:
        from ..utils.cleanup import purge_post as purge_post_service

        post = Post.query.filter_by(id=post_id, is_deleted=True).first()
        if post is None:
            raise ValidationError('回收站中没有该帖子', 4001)
        title, post_type = post.title, post.type
        stats = purge_post_service(post, delete_files=True)
        write_operation_log('purge', module=post_type, target_type='post', target_id=post_id,
                            detail={'title': title, **stats})
        return success(stats, msg=f'已彻底删除（同时清理 {stats["media_files"]} 个磁盘文件、'
                                  f'{stats["comments"]} 条评论）')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/batch/restore')
@admin_required
def batch_restore():
    """批量恢复：{"post_ids": [1,2]}"""
    try:
        payload = get_json()
        ids = parse_int_list(payload.get('post_ids'), '帖子ID')
        if not ids:
            raise ValidationError('请选择要恢复的帖子')
        affected = 0
        for pid in ids:
            post = Post.query.filter_by(id=pid, is_deleted=True).first()
            if post is None:
                continue
            post.restore()
            affected += 1
        db.session.commit()
        write_operation_log('batch_restore', module='trash', detail={'ids': ids, 'affected': affected})
        return success({'affected': affected}, msg=f'已恢复 {affected} 条')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/batch/purge')
@admin_required
def batch_purge():
    """批量彻底删除：{"post_ids": [1,2]}

    逐条走 `purge_post()` 级联清理（媒体文件 + 评论 + 收藏），不留下孤儿数据。
    """
    try:
        from ..utils.cleanup import purge_post as purge_post_service

        payload = get_json()
        ids = parse_int_list(payload.get('post_ids'), '帖子ID')
        if not ids:
            raise ValidationError('请选择要删除的帖子')
        affected = 0
        files = 0
        for pid in ids:
            post = Post.query.filter_by(id=pid, is_deleted=True).first()
            if post is None:
                continue
            stats = purge_post_service(post, delete_files=True)
            files += stats['media_files']
            affected += 1
        write_operation_log('batch_purge', module='trash',
                            detail={'ids': ids, 'affected': affected, 'files': files})
        return success({'affected': affected, 'media_files': files},
                       msg=f'已彻底删除 {affected} 条（清理 {files} 个磁盘文件）')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/cleanup')
@admin_required
def cleanup():
    """按保留条数立即清理回收站。

    请求体（可选）：{"keep": 10}
    """
    try:
        payload = get_json(required=False)
        keep = payload.get('keep')
        if keep is not None:
            from ..utils.config_service import set_config

            keep = int(keep)
            set_config('recycle_retention_count', keep, value_type='int')
        removed = svc.purge_overflow()
        write_operation_log('cleanup_trash', module='trash', detail={'removed': removed})
        keep_now = get_config_int('recycle_retention_count', 10)
        return success({'removed': removed, 'keep': keep_now},
                       msg=f'已清理 {removed} 条（当前保留最近 {keep_now} 条）')
    except (ValidationError, TypeError, ValueError) as exc:
        return as_error(exc)


@bp.get('/stats')
@admin_required
def trash_stats():
    """回收站概览。"""
    total = Post.query.filter(Post.is_deleted.is_(True)).count()
    rows = (
        db.session.query(Post.type, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(True))
        .group_by(Post.type)
        .all()
    )
    return success({
        'total': total,
        'by_module': {code: count for code, count in rows},
        'retention_count': get_config_int('recycle_retention_count', 10),
        'retention_mode': get_config('recycle_retention_mode', 'force'),
    })


__all__ = ['bp']
