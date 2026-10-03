# -*- coding: utf-8 -*-
"""数据清理服务：保证删除操作不留下孤儿指针与孤儿文件。

**孤儿指针**指某张表里的外键指向了一条已经不存在的记录（例如帖子删了，
评论还记着那个 post_id），查询时 JOIN 不到、页面显示空白或报错。
**孤儿文件**指磁盘上的媒体文件已经没有任何数据库记录引用它，
白占空间且无法通过页面管理。

本模块集中处理这两件事，供以下入口调用：
- 删除帖子（回收站彻底删除）
- 删除评论
- **删除用户（级联：帖子 / 评论 / 收藏 / 举报 / 通知 / 消息 / 上传记录 + 磁盘目录）**

设计取舍：
- 删除顺序固定为「先收集磁盘路径 → 再删数据库行 → 最后删磁盘」，
  中途失败也不会先丢文件后丢记录；
- 用户删除时对其帖子下的**他人评论**做物理删除（而不是留一个指向已删帖子的孤儿），
  这是需求「不要出现孤儿指针」的直接要求；
- 举报采用「置空 + 标记」而非物理删除：举报记录具有审计价值，
  但指向已删内容的外键必须置空，否则就是孤儿指针。
"""

import contextlib

from flask import current_app

from ..extensions import db
from ..models import (
    AdminModuleAccess,
    Comment,
    Favorite,
    Message,
    Notification,
    OperationLog,
    Post,
    Report,
    UploadFile,
)
from . import uploads as upload_utils


def _log(message, *args):
    if current_app:
        current_app.logger.info(message, *args)


# ---------------------------------------------------------------------------
# 帖子
# ---------------------------------------------------------------------------
def purge_post(post, delete_files=True):
    """彻底删除一条帖子及其全部关联数据。

    :param post: Post 实例
    :param delete_files: 是否同时删除磁盘上的媒体文件
    :return: dict 统计信息
    """
    media_rows = UploadFile.query.filter_by(post_id=post.id).all()
    paths = [row.path for row in media_rows]

    comments = Comment.query.filter_by(post_id=post.id).all()
    favorites = Favorite.query.filter_by(post_id=post.id).all()

    # 举报：保留记录（审计价值），但必须解除对已删内容的引用
    reports = Report.query.filter_by(post_id=post.id).all()
    for report in reports:
        report.post_id = None
        if not report.handle_remark:
            report.handle_remark = '关联内容已被删除'

    for row in comments:
        db.session.delete(row)
    for row in favorites:
        db.session.delete(row)
    for row in media_rows:
        db.session.delete(row)
    db.session.delete(post)
    db.session.commit()

    removed_files = 0
    if delete_files and paths:
        removed_files = upload_utils.delete_media_by_paths(paths)

    return {
        'post_id': post.id,
        'comments': len(comments),
        'favorites': len(favorites),
        'media_rows': len(media_rows),
        'media_files': removed_files,
        'reports_detached': len(reports),
    }


# ---------------------------------------------------------------------------
# 评论
# ---------------------------------------------------------------------------
def purge_comment(comment):
    """删除一条评论及其子回复，并回写帖子的评论计数（避免计数漂移）。"""
    post_id = comment.post_id
    removed = 0
    for reply in Comment.query.filter_by(parent_id=comment.id).all():
        db.session.delete(reply)
        removed += 1
    db.session.delete(comment)
    removed += 1
    db.session.commit()

    # 重算计数，避免 comment_count 与实际行数不一致
    post = Post.query.get(post_id) if post_id else None
    if post:
        post.comment_count = Comment.query.filter_by(post_id=post_id, is_deleted=False).count()
        db.session.commit()
    return {'comment_id': comment.id, 'removed': removed, 'post_id': post_id}


# ---------------------------------------------------------------------------
# 用户（级联删除）
# ---------------------------------------------------------------------------
def purge_user(user, delete_files=True):
    """彻底删除一个用户及其全部数据与上传文件。

    删除范围：
        帖子（连同其评论 / 收藏 / 媒体记录 / 举报引用解除）
        该用户发出的评论、收藏、举报、消息、通知、模块授权、上传记录
        磁盘目录 `uploads/<学号>/`
        操作日志：保留（审计需要），但把 user_id 置空避免孤儿指针

    :return: dict 统计信息
    """
    uid = user.id
    student_id = user.student_id

    posts = Post.query.filter_by(user_id=uid).all()
    media_rows = UploadFile.query.filter_by(user_id=uid).all()
    # 该用户帖子上的媒体也可能被别的路径引用，统一收集
    media_rows += UploadFile.query.filter(UploadFile.post_id.in_([p.id for p in posts])).all() \
        if posts else []
    media_paths = sorted({row.path for row in media_rows if row.path})

    stats = {
        'user_id': uid,
        'student_id': student_id,
        'posts': 0,
        'comments': 0,
        'favorites': 0,
        'reports': 0,
        'messages': 0,
        'notifications': 0,
        'media_rows': 0,
        'media_files': 0,
        'leftover_files': 0,
        'upload_dir': None,
    }

    # ---- 1. 先删该用户的帖子（复用 purge_post，保证其关联数据也被清理）----
    for post in posts:
        result = purge_post(post, delete_files=False)  # 磁盘最后统一删
        stats['posts'] += 1
        stats['comments'] += result['comments']
        stats['favorites'] += result['favorites']
        stats['media_rows'] += result['media_rows']

    # ---- 2. 该用户发出的其它数据 ----
    # 注意：各表的"归属字段"不统一，不能用通用的 user_id 批量处理。
    #   Message 用 sender_id / receiver_id 两个字段；
    #   AdminModuleAccess 用 user_id；
    #   LoginLog 保留（审计价值），此处不动。
    simple_targets = (
        (Comment, 'user_id', 'comments'),
        (Favorite, 'user_id', 'favorites'),
        (Notification, 'user_id', 'notifications'),
        (AdminModuleAccess, 'user_id', None),
        (UploadFile, 'user_id', 'media_rows'),
    )
    for model, field, key in simple_targets:
        query = model.query.filter(getattr(model, field) == uid)
        count = query.count()
        query.delete(synchronize_session=False)
        if key:
            stats[key] += count

    # 私信：发件与收件分别清理（Message 没有 user_id 列）
    sent = Message.query.filter_by(sender_id=uid).count()
    Message.query.filter_by(sender_id=uid).delete(synchronize_session=False)
    received = Message.query.filter_by(receiver_id=uid).count()
    Message.query.filter_by(receiver_id=uid).delete(synchronize_session=False)
    stats['messages'] += sent + received
    db.session.commit()

    # ---- 3. 举报：保留审计记录，解除对用户/内容的引用 ----
    reports = Report.query.filter_by(reporter_id=uid).all()
    reports += Report.query.filter_by(target_user_id=uid).all()
    for report in reports:
        if report.reporter_id == uid:
            # 举报人没了，记录失去意义，直接删除
            db.session.delete(report)
            stats['reports'] += 1
        else:
            report.target_user_id = None
            if not report.handle_remark:
                report.handle_remark = '被举报用户已注销'
    db.session.commit()

    # ---- 4. 日志：保留但置空 user_id（审计价值 > 引用完整性）----
    OperationLog.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    db.session.commit()

    # ---- 5. 删除磁盘文件 ----
    if delete_files:
        # 5.1 按数据库记录精确删除（统计进 media_files）
        stats['media_files'] = upload_utils.delete_media_by_paths(media_paths)
        # 5.2 整目录兜底：目录里可能还有记录已丢失的历史遗留文件
        leftover, directory = upload_utils.delete_user_upload_dir(
            student_id=student_id, user_id=uid
        )
        stats['leftover_files'] = leftover
        stats['upload_dir'] = directory

    # ---- 6. 最后删用户本体 ----
    db.session.delete(user)
    db.session.commit()

    _log('已彻底删除用户 %s（id=%s）：%s', student_id, uid, stats)
    return stats


# ---------------------------------------------------------------------------
# 校验：孤儿检查（测试与运维自检用）
# ---------------------------------------------------------------------------
def check_orphans():
    """扫描外键一致性，返回发现的孤儿指针清单（空列表 = 健康）。

    只检查本平台真实存在外键约束的关联；设计上允许为空的关联
    （例如举报的 post_id 在内容被删后会置空）不计入。
    """
    problems = []

    def collect(label, query):
        rows = query.all()
        if rows:
            problems.append({
                'type': label,
                'count': len(rows),
                'sample': [row[0] for row in rows[:5]],
            })

    post_ids = [row[0] for row in db.session.query(Post.id).all()]
    comment_ids = [row[0] for row in db.session.query(Comment.id).all()]

    collect('评论指向不存在的帖子',
            db.session.query(Comment.id).filter(Comment.post_id.notin_(post_ids)))
    collect('收藏指向不存在的帖子',
            db.session.query(Favorite.id).filter(Favorite.post_id.notin_(post_ids)))
    collect('回复指向不存在的父评论',
            db.session.query(Comment.id).filter(Comment.parent_id.isnot(None),
                                              Comment.parent_id.notin_(comment_ids)))
    return problems


def media_orphan_files():
    """找出磁盘上存在但没有数据库记录引用的文件（孤儿文件）。"""
    import os

    root = upload_utils._upload_root()  # noqa: SLF001 - 内部工具，集中在此使用
    known = {row.path for row in db.session.query(UploadFile.path).all()}
    orphans = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename == '.gitkeep':
                continue
            abs_path = os.path.join(dirpath, filename)
            rel = os.path.relpath(abs_path, root).replace(os.sep, '/')
            if rel not in known:
                with contextlib.suppress(OSError):
                    orphans.append({'path': rel, 'size': os.path.getsize(abs_path)})
    return orphans


__all__ = ['purge_post', 'purge_comment', 'purge_user', 'check_orphans', 'media_orphan_files']
