# -*- coding: utf-8 -*-
"""帖子领域服务：跨模块共用的帖子逻辑。

失物招领、二手交易、拼单、跑腿共用这张 `posts` 表，
因此把「取数 / 权限判断 / 状态流转 / 审核」统一收在这里，
模块路由只负责解析参数和组装响应，后续新增模块可直接复用。
"""

import json
import re
from datetime import datetime, timedelta

from ..extensions import db
from ..models import Post
from ..utils.constants import (
    ASSIGNMENT_CLAIM_TTL_HOURS,
    ASSIGN_SOURCE_ADMIN,
    ASSIGN_SOURCE_SELF,
    AUDIT_ACTION_APPROVE,
    AUDIT_ACTION_ASSIGN,
    AUDIT_ACTION_CLAIM,
    AUDIT_ACTION_REJECT,
    AUDIT_ACTION_RELEASE,
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_REJECTED,
    MODULE_DAILY,
    MODULE_GROUP_BUY,
    MODULE_SECOND_HAND,
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
    - 后台角色（管理员 / 审核员 / 版主）：全部可见 —— 审核员必须能看待审帖；
    - 作者本人：可见（含待审核 / 已关闭），便于自己管理；
    - 普通用户 / 游客：必须审核通过，且状态为「进行中」。
    """
    if user and user.is_staff:
        return True
    if user and post.user_id == user.id:
        return True
    return post.detail_visible


def can_edit(post, user):
    """编辑权限：作者本人或**真正的管理员**，且帖子未关闭。

    注意这里是 `is_admin` 而不是 `is_staff`：审核员可以审核、删帖、置顶，
    但**不能改别人的正文** —— 改内容属发布者权利，审核员替人改会造成责任不清。
    """
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
def _write_audit_log(post, action, actor_id=None, assignee_id=None,
                     assign_source=None, remark=None, duration_ms=None, commit=False):
    """写一条审核流水（只追加）。失败不阻断主流程。"""
    try:
        from ..models import PostAuditLog

        log = PostAuditLog(
            post_id=post.id,
            action=action,
            actor_id=actor_id,
            assignee_id=assignee_id,
            assign_source=assign_source,
            remark=(remark or None),
            duration_ms=duration_ms,
        )
        db.session.add(log)
        if commit:
            db.session.commit()
        return log
    except Exception:  # noqa: BLE001 - 流水写失败不应影响审核动作本身
        db.session.rollback()
        return None


def _assignment_duration_ms(post):
    """从指派/认领到现在的耗时（毫秒）。"""
    if not post.assigned_at:
        return None
    delta = datetime.now() - post.assigned_at
    return max(int(delta.total_seconds() * 1000), 0)


def _clear_assignment(post):
    """清空指派关系（审核结束或退回公共池）。"""
    post.assignee_id = None
    post.assigned_by = None
    post.assigned_at = None
    post.assignment_expires_at = None


def approve(post, operator, remark=None):
    """审核通过，并结束本次指派。"""
    duration = _assignment_duration_ms(post)
    assignee = post.assignee_id
    post.audit_status = AUDIT_APPROVED
    post.audit_remark = remark
    post.audited_by = operator.id
    post.audited_at = datetime.now()
    _clear_assignment(post)
    _write_audit_log(post, AUDIT_ACTION_APPROVE, actor_id=operator.id,
                     assignee_id=assignee, remark=remark, duration_ms=duration)
    return post


def reject(post, operator, remark=None):
    """审核拒绝，并结束本次指派。"""
    duration = _assignment_duration_ms(post)
    assignee = post.assignee_id
    post.audit_status = AUDIT_REJECTED
    post.audit_remark = remark or '内容不符合平台规范'
    post.audited_by = operator.id
    post.audited_at = datetime.now()
    _clear_assignment(post)
    _write_audit_log(post, AUDIT_ACTION_REJECT, actor_id=operator.id,
                     assignee_id=assignee, remark=remark, duration_ms=duration)
    return post


# ---------------------------------------------------------------------------
# 审核指派 / 认领（先到先得）
# ---------------------------------------------------------------------------
def release_expired_assignments(post_type=None):
    """把已到期的认领退回公共池（懒执行，不需要定时任务）。

    在「待审列表」与「认领」前各调一次，保证用户看到的指派状态永远是最新的。
    管理员手动指派默认不设到期时间，因此不会被这里退回。
    """
    query = Post.query.filter(
        Post.assignee_id.isnot(None),
        Post.assignment_expires_at.isnot(None),
        Post.assignment_expires_at <= datetime.now(),
        Post.audit_status == AUDIT_PENDING,
    )
    if post_type:
        query = query.filter(Post.type == post_type)

    released = 0
    for post in query.all():
        previous = post.assignee_id
        _clear_assignment(post)
        _write_audit_log(post, AUDIT_ACTION_RELEASE, actor_id=None,
                         assignee_id=previous, remark='认领超时自动退回公共池')
        released += 1
    if released:
        db.session.commit()
    return released


def build_pending_query(post_type=None, scope=None, current_user_id=None, assignee_id=None):
    """待审列表查询。

    :param scope: 'mine' 只看我的 | 'pool' 公共池（无人认领）| None 全部
    :param current_user_id: 当前用户ID（scope='mine' 时用）
    :param assignee_id: 指定审核人（管理员用，可查某位审核员名下有多少）
    """
    query = pending_audit_query(post_type)
    if assignee_id is not None:
        return query.filter(Post.assignee_id == assignee_id)
    if scope == 'mine':
        return query.filter(Post.assignee_id == current_user_id)
    if scope in ('pool', 'unassigned'):
        return query.filter(Post.assignee_id.is_(None))
    return query


def assign(post, assignee, operator, remark=None, ttl_hours=None):
    """管理员把帖子指派 / 改派给某位审核员（assignee=None 表示收回公共池）。

    管理员指派默认**不设到期时间**（ttl_hours=None），由管理员手动改派；
    传 ttl_hours 则会像自助认领一样到期自动退回。

    注意：管理员指派**可以覆盖审核员已认领的帖子** —— 这是刻意的设计，
    "认领"只约束审核员之间，不约束管理员；每次覆盖都会记一条 assign 流水，
    上一任审核员在流水里留痕，事后可查（谁被谁改派过）。
    """
    previous = post.assignee_id
    remark = remark or None

    if assignee is None:
        _clear_assignment(post)
        _write_audit_log(post, AUDIT_ACTION_RELEASE, actor_id=operator.id,
                         assignee_id=previous, remark=remark or '管理员收回至公共池')
        return post

    post.assignee_id = assignee.id
    post.assigned_by = operator.id
    post.assigned_at = datetime.now()
    post.assignment_expires_at = (
        datetime.now() + timedelta(hours=ttl_hours) if ttl_hours else None
    )
    _write_audit_log(post, AUDIT_ACTION_ASSIGN, actor_id=operator.id,
                     assignee_id=assignee.id,
                     assign_source=ASSIGN_SOURCE_ADMIN,
                     remark=remark or (f'由 {previous} 改派' if previous else None))
    return post


def claim(post, operator, ttl_hours=None):
    """审核员自助认领（**先到先得**，并发安全）。

    用一条带条件的原子 UPDATE 抢占：
        UPDATE posts SET assignee_id=:me ... WHERE id=:id AND assignee_id IS NULL
    行数为 0 说明已被别人抢走 —— 数据库的行锁天然实现"第一个写入的赢"，
    不需要额外的排队表或定时任务。

    :return: (ok, message)  ok=False 表示已被他人认领
    """
    from sqlalchemy import update as sa_update

    ttl = ttl_hours or ASSIGNMENT_CLAIM_TTL_HOURS
    now = datetime.now()
    expires = now + timedelta(hours=ttl)

    result = db.session.execute(
        sa_update(Post)
        .where(
            Post.id == post.id,
            Post.assignee_id.is_(None),          # ← 关键条件：只有公共池能被抢
            Post.audit_status == AUDIT_PENDING,  # ← 已审完的不能再抢
            Post.is_deleted.is_(False),
        )
        .values(
            assignee_id=operator.id,
            assigned_by=operator.id,
            assigned_at=now,
            assignment_expires_at=expires,
        )
    )
    if result.rowcount == 0:
        db.session.rollback()
        return False, '该帖子已被其他审核员认领'

    db.session.commit()
    db.session.refresh(post)
    _write_audit_log(post, AUDIT_ACTION_CLAIM, actor_id=operator.id,
                     assignee_id=operator.id, assign_source=ASSIGN_SOURCE_SELF,
                     remark=f'{ttl} 小时内未处理将自动退回公共池', commit=True)
    return True, '认领成功'


def release(post, operator, remark=None):
    """审核员放弃认领：退回公共池（不能放弃别人的）。"""
    previous = post.assignee_id
    _clear_assignment(post)
    _write_audit_log(post, AUDIT_ACTION_RELEASE, actor_id=operator.id,
                     assignee_id=previous, remark=remark or '审核员主动放弃')
    return post


def count_pending_by_assignee():
    """按审核人统计待审数量（管理端分配面板用）。"""
    rows = (
        db.session.query(Post.assignee_id, db.func.count(Post.id))
        .filter(Post.audit_status == AUDIT_PENDING, Post.is_deleted.is_(False))
        .group_by(Post.assignee_id)
        .all()
    )
    return {assignee_id: count for assignee_id, count in rows}


def pending_audit_query(post_type=None):
    return base_query(post_type).filter(Post.audit_status == AUDIT_PENDING)


# ---------------------------------------------------------------------------
# 扩展字段校验
# ---------------------------------------------------------------------------
#: ext_json 最大字节数，防止把 ext 当数据库用
MAX_EXT_JSON_BYTES = 4096


def normalize_ext(value):
    """校验模块扩展字段：必须是 JSON 对象、可序列化、体积受限。"""
    if value in (None, '', {}):
        return {}
    if not isinstance(value, dict):
        raise ValidationError('扩展字段 ext 必须是 JSON 对象')
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        raise ValidationError('扩展字段 ext 含有无法序列化的数据') from None
    if len(encoded.encode('utf-8')) > MAX_EXT_JSON_BYTES:
        raise ValidationError(f'扩展字段 ext 不能超过 {MAX_EXT_JSON_BYTES} 字节')
    return value


def validate_module_ext(module_code, value):
    """先做通用 ext 校验，再按模块做差异化校验。"""
    ext = normalize_ext(value)
    if module_code == MODULE_SECOND_HAND:
        if ext.get('price') in (None, ''):
            raise ValidationError('二手交易必须填写价格 price')
        try:
            price = float(ext['price'])
        except (TypeError, ValueError):
            raise ValidationError('二手交易价格必须是数字') from None
        if price < 0:
            raise ValidationError('二手交易价格不能为负数')
        ext['price'] = round(price, 2)

        for field in ('condition', 'trade_type'):
            field_value = ext.get(field)
            if field_value in (None, ''):
                continue
            if not isinstance(field_value, str):
                raise ValidationError(f'二手交易字段 {field} 必须是字符串')
            if len(field_value) > 32:
                raise ValidationError(f'二手交易字段 {field} 不能超过 32 字')
        original = ext.get('original_price')
        if original not in (None, ''):
            try:
                ext['original_price'] = round(float(original), 2)
            except (TypeError, ValueError):
                raise ValidationError('二手交易原价必须是数字') from None

    if module_code == MODULE_GROUP_BUY:
        # 目标人数：必填整数 1-999
        target = ext.get('target_count')
        if target in (None, ''):
            raise ValidationError('拼单必须填写目标人数 target_count')
        try:
            target = int(target)
        except (TypeError, ValueError):
            raise ValidationError('目标人数必须是整数') from None
        if not (1 <= target <= 999):
            raise ValidationError('目标人数需在 1-999 之间')
        ext['target_count'] = target

        # 当前人数：必填整数 0-999（允许大于目标人数，由单主自行判断）
        current = ext.get('current_count')
        if current in (None, ''):
            raise ValidationError('拼单必须填写当前人数 current_count')
        try:
            current = int(current)
        except (TypeError, ValueError):
            raise ValidationError('当前人数必须是整数') from None
        if not (0 <= current <= 999):
            raise ValidationError('当前人数需在 0-999 之间')
        ext['current_count'] = current

        # 开始日期：必填，YYYY-MM-DD
        start = ext.get('start_date')
        if start in (None, ''):
            raise ValidationError('拼单必须填写开始日期 start_date')
        if not isinstance(start, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', start):
            raise ValidationError('开始日期格式应为 YYYY-MM-DD')
        try:
            datetime.strptime(start, '%Y-%m-%d')
        except ValueError:
            raise ValidationError('开始日期不是有效日期') from None
        ext['start_date'] = start
    return ext


def contact_required(module_code):
    """拼单 / 日常的联系方式选填，其余模块必填。"""
    return module_code not in (MODULE_GROUP_BUY, MODULE_DAILY)


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------
def save_post(post, media=None, ext=None, commit=True):
    """保存帖子，媒体与扩展字段以 JSON 存储。

    media 会先经过 `canonical_media_list` 裁剪，只落库统一约定的媒体字段，
    避免上传接口返回的 `user_dir` 等调试字段混进 `posts.media`。
    """
    from ..utils.uploads import canonical_media_list

    if media is not None:
        media = canonical_media_list(media)
        post.media = json.dumps(media, ensure_ascii=False) if media else None
    if ext is not None:
        ext = validate_module_ext(post.type, ext)
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
        contact=validate_contact(data.get('contact'), required=contact_required(post_type)),
        status=POST_ONGOING,
    )
    # 只有**真正的管理员**发帖默认直接通过。
    # ⚠️ 这里刻意用 is_admin 而不是 is_staff：审核员（auditor）的帖子必须走审核，
    # 否则"来审别人帖子的人"自己的帖子却跳过审核（详见 docs/USER_FIELDS.md 的 R3）。
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

    from ..models import PostAuditLog

    for item in overflow:
        # 审核流水先删：post_audit_logs.post_id 是 NOT NULL，留着会破坏引用完整性
        PostAuditLog.query.filter_by(post_id=item.id).delete(synchronize_session=False)
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
    'normalize_ext', 'validate_module_ext', 'MAX_EXT_JSON_BYTES',
    # 审核指派 / 认领
    'assign', 'claim', 'release', 'build_pending_query',
    'release_expired_assignments', 'count_pending_by_assignee',
]
