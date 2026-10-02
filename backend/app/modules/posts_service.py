# -*- coding: utf-8 -*-
"""帖子领域服务：跨模块共用的帖子逻辑。

失物招领、二手交易、拼单、跑腿共用这张 `posts` 表，
因此把「取数 / 权限判断 / 状态流转 / 审核」统一收在这里，
模块路由只负责解析参数和组装响应，后续新增模块可直接复用。
"""

import json

from ..extensions import db
from ..models import Post
from ..utils.constants import (
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_REJECTED,
    POST_CLAIMED,
    POST_CLOSED,
    POST_EXPIRED,
    POST_ONGOING,
)
from ..utils.validators import ValidationError


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------
def base_query(post_type=None):
    """基础查询：默认排除软删除。"""
    query = Post.query.filter(Post.is_deleted.is_(False))
    if post_type:
        query = query.filter(Post.type == post_type)
    return query


def get_post(post_id, post_type=None, include_deleted=False):
    """按 ID 取帖子，可选限定模块。"""
    query = Post.query.filter(Post.id == post_id)
    if post_type:
        query = query.filter(Post.type == post_type)
    if not include_deleted:
        query = query.filter(Post.is_deleted.is_(False))
    return query.first()


def require_post(post_id, post_type=None, include_deleted=False):
    post = get_post(post_id, post_type, include_deleted)
    if post is None:
        raise ValidationError('帖子不存在或已删除', 4001)
    return post


def can_view_detail(post, user):
    """详情可见性判断。

    规则（需求 6.2）：
    - 管理员：全部可见；
    - 作者本人：可见（含待审核 / 已关闭），便于自己管理；
    - 普通用户 / 游客：必须审核通过，且状态为「进行中」。
    """
    if user and user.is_admin:
        return True
    if user and post.user_id == user.id:
        return True
    return post.detail_visible


def can_edit(post, user):
    """编辑权限：作者本人或管理员，且帖子未关闭。"""
    if not user:
        return False
    if user.is_admin:
        return True
    return post.user_id == user.id and post.status != POST_CLOSED


# ---------------------------------------------------------------------------
# 状态流转
# ---------------------------------------------------------------------------
#: 允许的状态迁移：当前状态 → 可迁移到的状态集合
STATUS_TRANSITIONS = {
    POST_ONGOING: {POST_CLAIMED, POST_CLOSED, POST_EXPIRED},
    POST_CLAIMED: {POST_CLOSED, POST_ONGOING},
    POST_EXPIRED: {POST_ONGOING, POST_CLOSED},
    POST_CLOSED: {POST_ONGOING},
}


def can_transition(current, target):
    if current == target:
        return False
    return target in STATUS_TRANSITIONS.get(current, set())


def apply_status(post, target_status, operator=None, reason=None):
    """执行状态流转（含权限与合法性校验）。"""
    from ..utils.constants import POST_STATUS_LABELS

    if not can_transition(post.status, target_status):
        raise ValidationError(
            f'不允许从「{POST_STATUS_LABELS.get(post.status, post.status)}」'
            f'变更为「{POST_STATUS_LABELS.get(target_status, target_status)}」',
            4004,
        )
    post.status = target_status
    if reason:
        post.audit_remark = reason
    return post


# ---------------------------------------------------------------------------
# 审核
# ---------------------------------------------------------------------------
def approve(post, operator, remark=None):
    from datetime import datetime

    post.audit_status = AUDIT_APPROVED
    post.audit_remark = remark
    post.audited_by = operator.id
    post.audited_at = datetime.now()
    return post


def reject(post, operator, remark=None):
    from datetime import datetime

    post.audit_status = AUDIT_REJECTED
    post.audit_remark = remark or '内容不符合平台规范'
    post.audited_by = operator.id
    post.audited_at = datetime.now()
    return post


def pending_audit_query(post_type=None):
    return base_query(post_type).filter(Post.audit_status == AUDIT_PENDING)


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------
def save_post(post, media=None, ext=None, commit=True):
    """保存帖子，媒体与扩展字段以 JSON 存储。"""
    if media is not None:
        post.media = json.dumps(media, ensure_ascii=False) if media else None
    if ext is not None:
        post.ext_json = json.dumps(ext, ensure_ascii=False) if ext else None
    db.session.add(post)
    if commit:
        db.session.commit()
    return post


def build_post(post_type, user, data, audit_enabled=True):
    """按请求数据构造 Post 实例（不落库）。"""
    from ..utils.validators import clean_text, parse_datetime, validate_contact

    post = Post(
        type=post_type,
        user_id=user.id,
        title=clean_text(data.get('title'), 128, '标题'),
        content=clean_text(data.get('content'), 5000, '描述'),
        location=clean_text(data.get('location'), 128, '地点'),
        happened_at=parse_datetime(data.get('happened_at'), '发生时间'),
        contact=validate_contact(data.get('contact')),
        status=POST_ONGOING,
    )
    # 管理员发帖默认直接通过；否则按平台开关决定是否需要审核
    if user.is_admin or not audit_enabled:
        post.audit_status = AUDIT_APPROVED
    else:
        post.audit_status = AUDIT_PENDING
    return post


def attach_media(post, media):
    """把已上传的媒体挂到帖子上。"""
    from ..models import UploadFile

    for item in media or []:
        if isinstance(item, dict) and item.get('id'):
            record = UploadFile.query.get(item['id'])
            if record:
                record.post_id = post.id
    db.session.commit()


def bump_view(post, commit=True):
    """浏览量 +1（原型阶段直接写库；量大后可改 Redis 计数）。"""
    post.view_count = (post.view_count or 0) + 1
    if commit:
        db.session.commit()
    return post.view_count


def soft_delete(post, operator=None, auto_purge=True):
    """软删除并维护回收站容量。"""
    post.soft_delete(operator_id=getattr(operator, 'id', None))
    db.session.commit()
    if auto_purge:
        purge_overflow()
    return post


def purge_overflow():
    """回收站超出保留条数时，按配置处理（默认彻底删除最旧的）。"""
    from ..utils.config_service import get_config, get_config_int

    limit = get_config_int('recycle_retention_count', 10)
    if limit <= 0:
        return 0
    deleted = Post.query.filter(Post.is_deleted.is_(True)).order_by(Post.deleted_at.desc()).all()
    overflow = deleted[limit:]
    if not overflow:
        return 0
    mode = get_config('recycle_retention_mode', 'force')
    if mode != 'force':
        return 0
    for item in overflow:
        db.session.delete(item)
    db.session.commit()
    return len(overflow)


def recycle_bin_query(post_type=None):
    """回收站列表（仅管理员可见）。"""
    query = Post.query.filter(Post.is_deleted.is_(True))
    if post_type:
        query = query.filter(Post.type == post_type)
    return query.order_by(Post.deleted_at.desc())


__all__ = [
    'base_query', 'get_post', 'require_post', 'can_view_detail', 'can_edit',
    'STATUS_TRANSITIONS', 'can_transition', 'apply_status', 'approve', 'reject',
    'pending_audit_query', 'save_post', 'build_post', 'attach_media', 'bump_view',
    'soft_delete', 'purge_overflow', 'recycle_bin_query',
]
