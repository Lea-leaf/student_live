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
import json
from datetime import datetime, timedelta

from flask import current_app

from ..extensions import db
from ..models import (
    AdminModuleAccess,
    Comment,
    CommentLike,
    Favorite,
    Message,
    Notification,
    OperationLog,
    Post,
    PostAuditLog,
    PostLike,
    Report,
    UploadFile,
    User,
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
    comment_ids = [row.id for row in comments]
    favorites = Favorite.query.filter_by(post_id=post.id).all()
    post_likes = PostLike.query.filter_by(post_id=post.id).all()

    # 审核流水（post_audit_logs.post_id 为 NOT NULL，必须先删，否则外键报错）
    audit_log_count = PostAuditLog.query.filter_by(post_id=post.id).delete(
        synchronize_session=False)

    # 举报：保留记录（审计价值），但必须解除对已删内容的引用
    reports = Report.query.filter_by(post_id=post.id).all()
    for report in reports:
        report.post_id = None
        if not report.handle_remark:
            report.handle_remark = '关联内容已被删除'

    # 私信可能关联帖子：帖子删了就把引用置空（不产生孤儿指针）
    Message.query.filter_by(post_id=post.id).update({'post_id': None}, synchronize_session=False)

    # 先清点赞关系，再删评论 / 帖子，避免外键约束报错
    comment_like_count = 0
    if comment_ids:
        comment_like_count = CommentLike.query.filter(
            CommentLike.comment_id.in_(comment_ids)
        ).count()
        CommentLike.query.filter(CommentLike.comment_id.in_(comment_ids)).delete(
            synchronize_session=False)
    for row in comments:
        db.session.delete(row)
    for row in favorites:
        db.session.delete(row)
    for row in post_likes:
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
        'post_likes': len(post_likes),
        'comment_likes': comment_like_count,
        'media_rows': len(media_rows),
        'media_files': removed_files,
        'reports_detached': len(reports),
        'audit_logs': audit_log_count,
    }


# ---------------------------------------------------------------------------
# 评论
# ---------------------------------------------------------------------------
def collect_comment_subtree_ids(comment):
    """按 parent_id 逐层收集评论及其全部后代 ID（支持任意层级楼中楼）。"""
    ids = [comment.id]
    stack = [comment.id]
    while stack:
        parent_id = stack.pop()
        children = Comment.query.with_entities(Comment.id).filter(
            Comment.parent_id == parent_id
        ).all()
        for (child_id,) in children:
            ids.append(child_id)
            stack.append(child_id)
    return ids


def purge_comment(comment):
    """彻底删除一条评论及其全部子回复、点赞、媒体文件，并回写帖子计数。"""
    comment_id = comment.id
    post_id = comment.post_id
    parent_id = comment.parent_id
    comment_ids = collect_comment_subtree_ids(comment)

    # 收集这些评论引用的媒体（优先 upload_files 归属，其次兼容 media JSON 里的 id/path）
    media_rows = UploadFile.query.filter(
        UploadFile.owner_type == 'comment', UploadFile.owner_id.in_(comment_ids)
    ).all()
    media_paths = [row.path for row in media_rows if row.path]
    known_paths = set(media_paths)

    import json as _json

    for row in Comment.query.filter(Comment.id.in_(comment_ids)).all():
        if not row.media:
            continue
        try:
            items = _json.loads(row.media)
        except (TypeError, ValueError):
            continue
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            rel_path = item.get('path')
            raw_id = item.get('id')
            if rel_path and rel_path not in known_paths:
                known_paths.add(rel_path)
                media_paths.append(rel_path)
            if raw_id:
                try:
                    record = UploadFile.query.get(int(raw_id))
                except (TypeError, ValueError):
                    record = None
                if record and record.path and record.path not in known_paths:
                    known_paths.add(record.path)
                    media_paths.append(record.path)
                    media_rows.append(record)

    # 删除点赞、相关互动通知、媒体记录、评论本体
    CommentLike.query.filter(CommentLike.comment_id.in_(comment_ids)).delete(
        synchronize_session=False)
    from ..utils.constants import NOTIFY_COMMENT, NOTIFY_LIKE, NOTIFY_MENTION

    Notification.query.filter(
        Notification.ref_id.in_(comment_ids),
        Notification.type.in_((NOTIFY_COMMENT, NOTIFY_LIKE, NOTIFY_MENTION)),
    ).delete(synchronize_session=False)
    for record in {row.id: row for row in media_rows}.values():
        db.session.delete(record)
    Comment.query.filter(Comment.id.in_(comment_ids)).delete(synchronize_session=False)
    db.session.commit()

    # 重算帖子评论数
    post = Post.query.get(post_id) if post_id else None
    if post:
        post.comment_count = Comment.query.filter_by(post_id=post_id, is_deleted=False).count()
    # 重算直接父评论的回复数
    if parent_id:
        parent = Comment.query.get(parent_id)
        if parent:
            parent.reply_count = Comment.query.filter_by(
                parent_id=parent_id, is_deleted=False
            ).count()
    db.session.commit()

    removed_files = upload_utils.delete_media_by_paths(media_paths)
    return {
        'comment_id': comment_id,
        'removed': len(comment_ids),
        'removed_files': removed_files,
        'post_id': post_id,
    }


# ---------------------------------------------------------------------------
# 私信
# ---------------------------------------------------------------------------
def purge_message(message):
    """彻底删除一条私信（撤回 / 双方都删除后清理）。

    同时清理：
    - `upload_files` 中 owner_type='message' 的媒体记录与磁盘文件；
    - 接收方的私信通知（ref_id 指向该消息），避免通知点进去是空会话。
    """
    import json

    message_id = message.id
    media_rows = UploadFile.query.filter_by(
        owner_type='message', owner_id=message_id).all()
    media_paths = [row.path for row in media_rows if row.path]
    known_paths = set(media_paths)

    # 兼容历史数据：media JSON 里有 id/path 但 owner 未回写的情况
    if message.media:
        try:
            items = json.loads(message.media)
        except (TypeError, ValueError):
            items = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            rel_path = item.get('path')
            if rel_path and rel_path not in known_paths:
                known_paths.add(rel_path)
                media_paths.append(rel_path)
            raw_id = item.get('id')
            if raw_id:
                try:
                    record = UploadFile.query.get(int(raw_id))
                except (TypeError, ValueError):
                    record = None
                if record and record.path and record.path not in known_paths:
                    known_paths.add(record.path)
                    media_paths.append(record.path)
                    media_rows.append(record)

    for record in {row.id: row for row in media_rows}.values():
        db.session.delete(record)
    Notification.query.filter_by(type='message', ref_id=message_id).delete(
        synchronize_session=False)
    db.session.delete(message)
    db.session.commit()

    removed_files = upload_utils.delete_media_by_paths(media_paths)
    return {
        'message_id': message_id,
        'removed_files': removed_files,
    }


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
        'likes': 0,
        'media_rows': 0,
        'media_files': 0,
        'leftover_files': 0,
        'audit_logs_cleared': 0,
        'upload_dir': None,
    }

    # ---- 1. 先删该用户的帖子（复用 purge_post，保证其关联数据也被清理）----
    for post in posts:
        result = purge_post(post, delete_files=False)  # 磁盘最后统一删
        stats['posts'] += 1
        stats['comments'] += result['comments']
        stats['favorites'] += result['favorites']
        stats['media_rows'] += result['media_rows']

    # ---- 2. 点赞关系：必须在删评论之前清理，否则 comment_likes 的外键会拦住 ----
    own_comment_ids = [row[0] for row in
                       db.session.query(Comment.id).filter(Comment.user_id == uid).all()]
    # 2.1 他名下评论收到的赞（别人点的）
    like_count = 0
    if own_comment_ids:
        like_count += CommentLike.query.filter(
            CommentLike.comment_id.in_(own_comment_ids)).count()
        CommentLike.query.filter(CommentLike.comment_id.in_(own_comment_ids)).delete(
            synchronize_session=False)
    # 2.2 他发出的帖子赞 / 评论赞
    like_count += PostLike.query.filter_by(user_id=uid).count()
    PostLike.query.filter_by(user_id=uid).delete(synchronize_session=False)
    like_count += CommentLike.query.filter_by(user_id=uid).count()
    CommentLike.query.filter_by(user_id=uid).delete(synchronize_session=False)
    stats['likes'] = like_count

    # ---- 3. 该用户发出的其它数据 ----
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

    # ---- 4. 私信 ----

    # 私信：发件与收件分别清理（Message 没有 user_id 列）
    sent = Message.query.filter_by(sender_id=uid).count()
    Message.query.filter_by(sender_id=uid).delete(synchronize_session=False)
    received = Message.query.filter_by(receiver_id=uid).count()
    Message.query.filter_by(receiver_id=uid).delete(synchronize_session=False)
    stats['messages'] += sent + received
    db.session.commit()

    # ---- 5. 举报：保留审计记录，解除对用户/内容的引用 ----
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

    # ---- 6. 日志：保留但置空 user_id（审计价值 > 引用完整性）----
    OperationLog.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    # 审核流水同理：他是审核员时留下的记录仍有审计价值（谁审的哪条、用了多久），
    # 但要解除对已注销用户的引用，避免出现指向不存在用户的裸指针。
    cleared_actor = PostAuditLog.query.filter_by(actor_id=uid).update(
        {'actor_id': None}, synchronize_session=False)
    cleared_assignee = PostAuditLog.query.filter_by(assignee_id=uid).update(
        {'assignee_id': None}, synchronize_session=False)
    stats['audit_logs_cleared'] = cleared_actor + cleared_assignee
    db.session.commit()

    # ---- 7. 删除磁盘文件 ----
    if delete_files:
        # 7.1 按数据库记录精确删除（统计进 media_files）
        stats['media_files'] = upload_utils.delete_media_by_paths(media_paths)
        # 7.2 整目录兜底：目录里可能还有记录已丢失的历史遗留文件
        leftover, directory = upload_utils.delete_user_upload_dir(
            student_id=student_id, user_id=uid
        )
        stats['leftover_files'] = leftover
        stats['upload_dir'] = directory

    # ---- 8. 最后删用户本体 ----
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
    user_ids = [row[0] for row in db.session.query(User.id).all()]

    collect('评论指向不存在的帖子',
            db.session.query(Comment.id).filter(Comment.post_id.notin_(post_ids)))
    collect('收藏指向不存在的帖子',
            db.session.query(Favorite.id).filter(Favorite.post_id.notin_(post_ids)))
    collect('帖子点赞指向不存在的帖子',
            db.session.query(PostLike.id).filter(PostLike.post_id.notin_(post_ids)))
    collect('帖子点赞指向不存在的用户',
            db.session.query(PostLike.id).filter(PostLike.user_id.notin_(user_ids)))
    collect('评论点赞指向不存在的评论',
            db.session.query(CommentLike.id).filter(CommentLike.comment_id.notin_(comment_ids)))
    collect('回复指向不存在的父评论',
            db.session.query(Comment.id).filter(Comment.parent_id.isnot(None),
                                              Comment.parent_id.notin_(comment_ids)))
    collect('私信指向不存在的发送者',
            db.session.query(Message.id).filter(Message.sender_id.notin_(user_ids)))
    collect('私信指向不存在的接收者',
            db.session.query(Message.id).filter(Message.receiver_id.notin_(user_ids)))
    return problems


def _media_json_paths():
    """收集 posts / comments / messages 三处 media JSON 里的媒体相对路径。"""
    known = set()

    def collect(raw):
        try:
            items = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            return
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            rel_path = str(item.get('path') or '').replace('\\', '/').lstrip('/')
            if rel_path:
                known.add(rel_path)
            url = str(item.get('url') or '').replace('\\', '/')
            for marker in ('/files/', 'files/'):
                if marker in url:
                    rel_from_url = url.split(marker, 1)[1].lstrip('/')
                    if rel_from_url:
                        known.add(rel_from_url)
                    break

    for model in (Post, Comment, Message):
        rows = db.session.query(model.media).filter(model.media.isnot(None)).all()
        for (raw,) in rows:
            collect(raw)
    return known


def _known_media_paths():
    """媒体已知被引用路径：upload_files 记录 + 三处 media JSON。"""
    known = {row[0] for row in db.session.query(UploadFile.path).all() if row[0]}
    return known | _media_json_paths()


def media_orphan_files():
    """找出磁盘上存在但数据库任何地方都没有引用的文件（孤儿文件）。"""
    import os

    root = upload_utils._upload_root()  # noqa: SLF001 - 内部工具，集中在此使用
    known = _known_media_paths()
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


def unattached_upload_files(hours=24, now=None):
    """未提交业务的临时上传：upload_files 里没有任何归属、且超过保留时长。

    用户先调 /common/upload 拿到 media，但最终没有发帖 / 评论 / 私信时，
    记录会一直挂在 upload_files 里。超过 `hours` 小时仍未归属的视为临时文件。
    """
    cutoff = (now or datetime.now()) - timedelta(hours=max(int(hours or 0), 0))
    media_json_paths = _media_json_paths()  # 兼容历史数据：media JSON 里仍引用则不能删
    query = UploadFile.query.filter(
        db.or_(UploadFile.owner_type.is_(None), UploadFile.owner_id.is_(None)),
        UploadFile.post_id.is_(None),
        UploadFile.created_at < cutoff,
    ).order_by(UploadFile.id.asc())
    return [row for row in query.all() if row.path not in media_json_paths]


def clean_unused_uploads(hours=24, now=None):
    """删除超过保留时长的未提交上传：数据库记录 + 磁盘文件。"""
    rows = unattached_upload_files(hours=hours, now=now)
    paths = [row.path for row in rows if row.path]
    total_bytes = sum(int(row.size or 0) for row in rows)

    for row in rows:
        db.session.delete(row)
    if rows:
        db.session.commit()

    removed_files = upload_utils.delete_media_by_paths(paths) if paths else 0
    return {
        'records': len(rows),
        'files': len(paths),
        'removed_files': removed_files,
        'bytes': total_bytes,
        'hours': max(int(hours or 0), 0),
    }


def clean_unused_media(hours=24):
    """管理端清理未引用媒体：未提交上传 + 磁盘孤儿文件一起清。"""
    unattached = clean_unused_uploads(hours=hours)
    orphans = media_orphan_files()
    orphan_bytes = sum(int(item.get('size') or 0) for item in orphans)
    orphan_paths = [item['path'] for item in orphans if item.get('path')]
    orphan_removed = upload_utils.delete_media_by_paths(orphan_paths) if orphan_paths else 0

    return {
        'unattached': unattached,
        'orphan_count': len(orphans),
        'orphan_removed': orphan_removed,
        'orphan_bytes': orphan_bytes,
    }


__all__ = ['purge_post', 'purge_comment', 'purge_message', 'purge_user',
           'check_orphans', 'media_orphan_files', 'unattached_upload_files',
           'clean_unused_uploads', 'clean_unused_media']
