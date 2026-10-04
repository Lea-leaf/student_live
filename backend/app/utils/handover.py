# -*- coding: utf-8 -*-
"""管理员移交（唯一的"换管理员"机制）。

## 为什么需要单独一个模块

需求：**系统里只允许存在一个管理员**。管理员要把权限让出去，
不能简单地"把自己降级" —— 那样后台就没人能任命角色了（谁也进不去管理入口）。
所以改成**两阶段移交 + 24 小时反悔期**：

    阶段一（0 ~ 24 小时）：A 指定 B 接管
        - B 立刻获得管理员身份，但**冻结**：用不了任何后台功能（只有普通用户能力）
        - A 仍是管理员，功能照常，随时可以撤销
    阶段二（24 小时后首次请求时自动落地）：
        - A 降为普通用户，B 解除冻结、正式上任

时序图：

    t=0                      A 发起移交                 B 显示「管理员（待上任）」
    t=0 ~ 24h         A 随时撤销 / 随时改用移交功能     B 冻结，C 是普通用户
    t=24h（懒执行）    A → 普通用户                      B 冻结解除，正式管理员

## 「懒执行」是什么意思

没有定时任务。24 小时到点后，**任何人下一次访问后台接口时**才发现并落地这次移交
（`finalize_due_handover()`）。好处是不引入调度器 / 不写 crontab；
代价是"到点的那一刻"不会有人自动生效，需要有人打开后台页面。

## 为什么隐藏其他管理员占位记录

发起移交时，**除了 B 之外的所有管理员都会被降为普通用户**
（正常只有 A 一个，所以这是一次"防御性清理"）。
这样"只允许一个管理员"是**系统强制**的，而不是靠约定 ——
即使历史上手工造出过多个管理员，也会在移交时自动收敛成一个。

## 北京时间

所有判定统一用 `now_beijing()`（UTC+8 固定偏移）。
不用 `zoneinfo`：精简环境里可能没有 tzdata 包，而中国不实行夏令时，
固定偏移拿到的就是标准北京时间，且零依赖。
"""

from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..utils.constants import ROLE_ADMIN, ROLE_LABELS, ROLE_USER, STATUS_ACTIVE
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import CODE_FORBIDDEN, error
from ..utils.validators import ValidationError

#: 北京时间 = UTC+8 固定偏移（中国不实行夏令时，无需 tzdata）
BEIJING_TZ = timezone(timedelta(hours=8))

#: 反悔期：24 小时
HANDOVER_WINDOW_HOURS = 24


def now_beijing():
    """当前北京时间（naive datetime，与库中其它时间字段存储口径一致）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def handover_deadline(started_at):
    """移交落地时间 = 发起时间 + 24 小时。"""
    return started_at + timedelta(hours=HANDOVER_WINDOW_HOURS)


def freeze_active(user):
    """该账号当前是否处于"待上任冻结"状态。"""
    return bool(user.handover_freeze_at)


def is_frozen_admin(user):
    """是否为冻结中的待上任管理员（身份是管理员，但没有后台能力）。"""
    return bool(user.role == ROLE_ADMIN and user.handover_freeze_at)


def find_pending_handover():
    """找出当前进行中的移交（返回 (发起人, 接班人)，没有则 (None, None)）。

    正常情况下移交最多只有一条（因为发起时会把其他管理员清掉）。
    """
    from ..models import User

    candidates = (
        User.query.filter(User.role == ROLE_ADMIN, User.handover_at.isnot(None))
        .order_by(User.handover_at.desc())
        .all()
    )
    for initiator in candidates:
        target = User.query.get(initiator.handover_to_id) if initiator.handover_to_id else None
        if target and target.role == ROLE_ADMIN:
            return initiator, target
    return None, None


def pending_status(user):
    """给前端用的移交状态快照。"""
    if user.handover_freeze_at:
        # 自己是接班人：等 24 小时后上任
        initiator, _ = find_pending_handover()
        return {
            'handover_pending': True,
            'handover_role': 'target',
            'handover_at': initiator.handover_at.strftime('%Y-%m-%d %H:%M:%S')
            if initiator and initiator.handover_at else None,
            'handover_deadline': user.handover_effective_at.strftime('%Y-%m-%d %H:%M:%S')
            if user.handover_effective_at else None,
            'handover_from': initiator.to_brief() if initiator else None,
        }

    if user.handover_to_id:
        # 自己是发起人：期间仍是管理员，可随时撤销
        from ..models import User

        target = User.query.get(user.handover_to_id)
        return {
            'handover_pending': True,
            'handover_role': 'initiator',
            'handover_at': user.handover_at.strftime('%Y-%m-%d %H:%M:%S')
            if user.handover_at else None,
            'handover_deadline': user.handover_effective_at.strftime('%Y-%m-%d %H:%M:%S')
            if user.handover_effective_at else None,
            'handover_to': target.to_brief() if target else None,
        }

    return {'handover_pending': False}


def list_admins(exclude_id=None):
    """当前管理员列表（排查 / 展示用）。"""
    from ..models import User

    query = User.query.filter(User.role == ROLE_ADMIN, User.status == STATUS_ACTIVE)
    if exclude_id:
        query = query.filter(User.id != exclude_id)
    return query.order_by(User.id.asc()).all()


def list_candidates(operator):
    """可选接任者：**除自己以外的全部正常账号**。

    ⚠️ 这里刻意不是"现有管理员列表"：系统只允许一个管理员，
    如果只在管理员里选，排除自己之后永远是空列表 —— 那就没人能接任了。
    接任者的语义是"一个当前不是管理员的正常账号，被选中后升为管理员"。

    排除：
    - 自己（不能移交给自己）；
    - 已封禁账号（不能接管）；
    - 已经是管理员的账号（只可能是历史残留，避免重复移交）。
    """
    from ..models import User

    return (
        User.query
        .filter(User.id != operator.id,
                User.status == STATUS_ACTIVE,
                User.role != ROLE_ADMIN)
        .order_by(User.id.asc())
        .all()
    )


def finalize_due_handover():
    """把已到期的移交落地（懒执行：后台接口每次访问时调用）。

    :return: (finalized: bool, initiator, target)

    落地动作（按顺序，保证任何时候都至少有一个可用管理员）：
        1. 接班人解除冻结（先给权限，再收权限，避免中间出现"零管理员"窗口）；
        2. 发起人降为普通用户并清空移交字段。
    """
    initiator, target = find_pending_handover()
    if not initiator or not target or not initiator.handover_effective_at:
        return False, None, None
    if now_beijing() < initiator.handover_effective_at:
        return False, initiator, target

    from ..models import User

    # 1) 先解除接班人的冻结并确保其在线状态正常
    target.handover_freeze_at = None
    target.handover_at = None
    target.handover_to_id = None
    target.handover_effective_at = None
    target.handover_prev_role = None
    if target.status != STATUS_ACTIVE:
        target.status = STATUS_ACTIVE

    # 发起人降级
    initiator.role = ROLE_USER
    initiator.handover_to_id = None
    initiator.handover_at = None
    initiator.handover_effective_at = None
    initiator.handover_freeze_at = None
    initiator.handover_prev_role = None

    # 3) 兜底：把任何残留的其它管理员一并降级（"只允许一个管理员"）
    leftovers = User.query.filter(
        User.role == ROLE_ADMIN, User.id.notin_([target.id])
    ).all()
    for extra in leftovers:
        extra.role = ROLE_USER
        extra.handover_to_id = None
        extra.handover_at = None
        extra.handover_effective_at = None
        extra.handover_freeze_at = None
        extra.handover_prev_role = None

    try:
        db.session.commit()
    except Exception:  # noqa: BLE001 - 并发下另一方已落地，忽略即可
        db.session.rollback()
        return False, None, None

    write_operation_log('admin_handover_done', module='users', target_type='user',
                        target_id=initiator.id,
                        detail={'from': initiator.student_id,
                                'to': target.student_id,
                                'leftovers_demoted': len(leftovers)})
    from_name = initiator.nickname or initiator.student_id
    send(target.id, '你已成为管理员',
         f'管理员权限已由 {from_name} 移交给你，现在可以正常使用后台功能。',
         notify_type='system')
    send(initiator.id, '管理员权限已移交',
         f'你已不再是管理员，账号已变为普通用户。接任者：{target.student_id}。',
         notify_type='system')
    return True, initiator, target


def transfer_admin(operator, target, reason=None):
    """发起管理员移交（第一阶段）：目标立刻获得管理员身份并被冻结 24 小时。"""
    from ..models import User

    if target is None:
        raise ValidationError('请选择接管管理员权限的用户')
    if target.id == operator.id:
        raise ValidationError('不能把管理员权限移交给自己')
    if target.is_banned:
        raise ValidationError('该账号已被封禁，不能接管管理员权限')
    if target.role == ROLE_ADMIN:
        raise ValidationError('该账号已经是管理员，无需移交')

    # 同一时间只允许一条进行中的移交
    pending_initiator, pending_target = find_pending_handover()
    if pending_initiator and pending_initiator.id != operator.id:
        raise ValidationError(
            f'已存在进行中的移交（{pending_initiator.student_id} → '
            f'{pending_target.student_id if pending_target else "?"}），请先撤销'
        )

    started = now_beijing()
    deadline = handover_deadline(started)

    # 防御性清理：把其他管理员降为普通用户，保证"管理员只有一个"
    others = User.query.filter(User.role == ROLE_ADMIN,
                              User.id.notin_([operator.id, target.id])).all()
    for extra in others:
        extra.role = ROLE_USER
        extra.handover_to_id = None
        extra.handover_at = None
        extra.handover_effective_at = None
        extra.handover_freeze_at = None

    # 接班人：立刻是管理员，但冻结到 deadline
    # 先记住他原来的角色：冻结期按原角色授权（审核员继续审核），撤销时按它恢复
    target.handover_prev_role = target.role
    target.role = ROLE_ADMIN
    target.handover_freeze_at = started
    target.handover_at = None
    target.handover_to_id = None
    target.handover_effective_at = None

    # 发起人：仍是管理员（功能照常），记录移交信息
    operator.handover_to_id = target.id
    operator.handover_at = started
    operator.handover_effective_at = deadline
    operator.handover_freeze_at = None

    db.session.commit()
    write_operation_log('admin_handover_start', module='users', target_type='user',
                        target_id=target.id,
                        detail={'to': target.student_id,
                                'effective_at': deadline.strftime('%Y-%m-%d %H:%M:%S'),
                                'reason': reason,
                                'others_demoted': len(others)})

    deadline_text = deadline.strftime('%Y-%m-%d %H:%M')
    send(target.id, '管理员权限待接手',
         f'{operator.student_id} 将管理员权限移交给你。为安全起见，'
         f'{deadline_text}（北京时间）之前你的后台功能处于冻结状态，'
         f'期间对方可随时撤销；到期后自动生效。',
         notify_type='system')
    send(operator.id, '已发起管理员移交',
         f'接任者：{target.student_id}。在 {deadline_text}（北京时间）之前你仍是管理员，'
         f'可随时撤销；到期未撤销则你变为普通用户。',
         notify_type='system')
    return deadline


def cancel_transfer(operator, force=False):
    """撤销移交（第二阶段的"反悔"）。发起人可撤销；管理员也可对冻结账号强制撤销。"""
    initiator, target = find_pending_handover()
    if not initiator or not target:
        raise ValidationError('当前没有进行中的管理员移交')

    if not force and initiator.id != operator.id:
        return error('只有发起移交的管理员可以撤销', CODE_FORBIDDEN, http_status=403)

    # 接班人：**恢复到接管前的角色**（原本是审核员就还原成审核员，
    # 不能一律降成普通用户 —— 那等于撤销一次就白白丢掉原有身份）
    restored_role = target.handover_prev_role or ROLE_USER
    target.role = restored_role
    target.handover_freeze_at = None
    target.handover_at = None
    target.handover_to_id = None
    target.handover_effective_at = None
    target.handover_prev_role = None

    # 发起人清空移交信息，保持管理员身份
    initiator.handover_to_id = None
    initiator.handover_at = None
    initiator.handover_effective_at = None
    initiator.handover_freeze_at = None
    initiator.handover_prev_role = None

    db.session.commit()
    write_operation_log('admin_handover_cancel', module='users', target_type='user',
                        target_id=target.id,
                        detail={'to': target.student_id, 'forced': force,
                                'restored_role': restored_role})
    send(target.id, '管理员移交已撤销',
         f'该次管理员权限移交已被撤销，你的账号已恢复为'
         f'「{ROLE_LABELS.get(restored_role, restored_role)}」。',
         notify_type='system')
    send(initiator.id, '管理员移交已撤销', '你仍是管理员，权限未发生变化。', notify_type='system')
    return initiator


__all__ = [
    'BEIJING_TZ', 'HANDOVER_WINDOW_HOURS',
    'now_beijing', 'handover_deadline', 'freeze_active', 'is_frozen_admin',
    'find_pending_handover', 'pending_status', 'list_admins', 'list_candidates',
    'finalize_due_handover', 'transfer_admin', 'cancel_transfer',
]
