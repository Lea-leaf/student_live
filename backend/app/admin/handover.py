# -*- coding: utf-8 -*-
"""管理端 - 管理员移交。

## 为什么单独一个蓝图

需求：**系统里只允许存在一个管理员**。所以"换管理员"不是简单地改个角色，
而是一套两阶段流程（详见 `app/utils/handover.py`）：

    第一阶段（0 ~ 24 小时）：A 指定 B 接管
        - B 立刻获得管理员身份，但**冻结**：用不了任何后台功能
        - A 仍是管理员、功能照常，随时可以撤销
    第二阶段（24 小时后自动落地）：
        - A 降为普通用户，B 解除冻结、正式上任

时间以**北京时间**为准（UTC+8 固定偏移）。

接口一览（前缀 `/api/v1/admin/handover`）：
    GET  /status     当前移交状态（发起人 / 接班人视角）+ 可选接任者名单
    POST /           发起移交   {"user_id": 12, "reason": "毕业交接"}
    POST /cancel     撤销移交（发起人随时可撤销）
    POST /finalize   立即结算已到期的移交（演示 / 排障用，正常无需调用）
"""

from flask import Blueprint

from ..utils import handover as ho
from ..utils.auth import admin_required, current_user
from ..utils.constants import CAP_ADMIN_HANDOVER
from ..utils.response import error, success
from ..utils.validators import ValidationError, as_error, get_json

bp = Blueprint('admin_handover', __name__, url_prefix='/handover')


def _get_user_or_400(user_id):
    from ..models import User

    user = User.query.get(user_id)
    if user is None:
        raise ValidationError('用户不存在', 3002)
    return user


@bp.get('/status')
@admin_required(capability=CAP_ADMIN_HANDOVER)
def handover_status():
    """当前移交状态。

    返回里同时包含：
    - `handover_role`：`initiator`（我是发起人，仍是管理员）/ `target`（我是接班人，冻结中）；
    - `handover_deadline`：到期时间（北京时间）；
    - `candidates`：**可选接任者** = 除自己以外的全部正常账号
      （不是"现有管理员列表" —— 系统只允许一个管理员，那样排除自己后永远是空的）；
    - `server_now`：服务器当前北京时间 —— 前端用它校准倒计时，避免依赖本机时钟。
    """
    operator = current_user()
    initiator, target = ho.find_pending_handover()
    status = ho.pending_status(operator)
    status['window_hours'] = ho.HANDOVER_WINDOW_HOURS
    status['server_now'] = ho.now_beijing().strftime('%Y-%m-%d %H:%M:%S')
    status['candidates'] = [user.to_brief() for user in ho.list_candidates(operator)]
    status['can_cancel'] = bool(
        initiator and target and (initiator.id == operator.id or operator.is_admin)
    )
    return success(status)


@bp.post('')
@admin_required(capability=CAP_ADMIN_HANDOVER)
def start_handover():
    """发起管理员移交。

    请求体：{"user_id": 12, "reason": "毕业交接"}
    """
    try:
        operator = current_user()
        payload = get_json()
        target_id = payload.get('user_id')
        if not target_id:
            raise ValidationError('请选择接管管理员权限的用户')
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            raise ValidationError('user_id 必须是整数') from None

        target = _get_user_or_400(target_id)
        deadline = ho.transfer_admin(operator, target, reason=payload.get('reason'))
        return success(
            {
                'handover_to': target.to_brief(),
                'effective_at': deadline.strftime('%Y-%m-%d %H:%M:%S'),
                'window_hours': ho.HANDOVER_WINDOW_HOURS,
            },
            msg=f'已发起移交。{deadline.strftime("%m-%d %H:%M")}（北京时间）前可随时撤销，'
                f'到期后你变为普通用户、对方正式上任',
        )
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/cancel')
@admin_required(capability=CAP_ADMIN_HANDOVER)
def cancel_handover():
    """撤销（反悔）移交：接班人还原为普通用户，发起人保持管理员。"""
    try:
        operator = current_user()
        payload = get_json(required=False) or {}
        initiator = ho.cancel_transfer(operator, force=bool(payload.get('force')))
        if initiator is None:
            return error('当前没有进行中的管理员移交')
        return success(msg='已撤销移交，你仍是管理员')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/finalize')
@admin_required(capability=CAP_ADMIN_HANDOVER)
def finalize_handover():
    """立即结算已到期的移交（正常不需要调用 —— 后台接口每次访问都会自动结算）。"""
    done, initiator, target = ho.finalize_due_handover()
    if not done:
        return error('当前没有已到期的移交需要结算')
    return success(
        {'from': initiator.student_id, 'to': target.student_id},
        msg=f'移交已生效：{initiator.student_id} 已变为普通用户，{target.student_id} 已成为管理员',
    )


__all__ = ['bp']
