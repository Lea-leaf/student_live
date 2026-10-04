# -*- coding: utf-8 -*-
"""管理端 - 举报处理。

用户提交举报（/api/v1/reports），管理员在这里处理：
可选择「忽略」「删除帖子」「封禁用户」等动作。
"""

from datetime import datetime

from flask import Blueprint, request

from ..extensions import db
from ..models import Post, Report, User
from ..models.base import paginate
from ..utils.auth import admin_required, current_user
from ..utils.constants import CAP_REPORT_HANDLE, REPORT_HANDLED, REPORT_PENDING, REPORT_REJECTED
from ..utils.helpers import current_page_args, keyword_arg
from ..utils.logger import write_operation_log
from ..utils.notification_service import send
from ..utils.response import error, paginated, success
from ..utils.validators import ValidationError, as_error, clean_text, get_json
from ..modules import posts_service as svc

bp = Blueprint('admin_reports', __name__, url_prefix='/reports')


@bp.get('')
@admin_required(capability=CAP_REPORT_HANDLE)
def list_reports():
    """举报列表。参数：page / size / status / keyword。"""
    try:
        page, size = current_page_args()
        keyword = keyword_arg()
        status = (request.args.get('status') or '').strip()
        query = Report.query
        if status:
            query = query.filter(Report.status == status)
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(db.or_(Report.reason.like(like), Report.detail.like(like)))
        query = query.order_by(Report.id.desc())
        items, total, page, size = paginate(query, page, size)

        data = []
        for report in items:
            item = report.to_dict()
            item['post'] = report.post.to_brief() if report.post else None
            item['target_user'] = (
                User.query.get(report.target_user_id).to_brief() if report.target_user_id else None
            )
            data.append(item)
        return paginated(data, total, page, size, extra={'pending': Report.query.filter_by(status=REPORT_PENDING).count()})
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:report_id>/handle')
@admin_required(capability=CAP_REPORT_HANDLE)
def handle_report(report_id):
    """处理举报。

    请求体：
        {
            "status": "handled" | "rejected",     # handled=举报成立, rejected=驳回
            "remark": "处理说明",
            "action": "none" | "delete_post" | "ban_user"   # 可选的联动动作
        }

    权限：审核员也能处置举报（含删帖 / 封禁被举报人），
    但联动封禁**只能作用于普通用户** —— 审核员不能借举报流程处置其他后台角色，
    否则等于绕过 user 模块的"只能管普通用户"限制。
    """
    try:
        operator = current_user()
        report = Report.query.get(report_id)
        if report is None:
            raise ValidationError('举报记录不存在', 5001)
        if report.status != REPORT_PENDING:
            return error('该举报已处理', 5001)

        payload = get_json()
        status = (payload.get('status') or REPORT_HANDLED).strip()
        if status not in (REPORT_HANDLED, REPORT_REJECTED):
            raise ValidationError('status 只能是 handled / rejected')
        remark = clean_text(payload.get('remark'), 255, '处理说明')
        action = (payload.get('action') or 'none').strip()

        # 联动动作
        action_result = None
        if action == 'delete_post' and report.post_id:
            post = Post.query.get(report.post_id)
            if post and not post.is_deleted:
                svc.soft_delete(post, operator=operator)
                action_result = '帖子已删除并移入回收站'
        elif action == 'ban_user':
            target_id = report.target_user_id or (report.post.user_id if report.post else None)
            if target_id:
                target = User.query.get(target_id)
                if target and target.id == operator.id:
                    action_result = '不能封禁自己，已跳过'
                elif target and not operator.is_admin and target.is_staff:
                    action_result = '审核员只能封禁普通用户，已跳过'
                elif target and not target.is_admin:
                    target.ban(reason=f'被举报：{report.reason}', operator_id=operator.id)
                    action_result = '被举报用户已封禁'

        report.status = status
        report.handled_by = operator.id
        report.handled_at = datetime.now()
        report.handle_remark = remark
        db.session.commit()

        write_operation_log('handle_report', module='reports', target_type='report',
                            target_id=report.id, detail={'status': status, 'action': action})
        # 通知举报人
        send(report.reporter_id,
             '你的举报已处理' if status == REPORT_HANDLED else '你的举报已驳回',
             f'举报原因：{report.reason}；处理结果：{remark or "无补充说明"}',
             notify_type='system', ref_id=report.id)
        return success({'report': report.to_dict(), 'action_result': action_result}, msg='处理完成')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
