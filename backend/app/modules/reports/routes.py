# -*- coding: utf-8 -*-
"""举报模块。

普通用户提交举报，管理员在后台处理（处理入口在 admin/reports）。
"""

from flask import Blueprint

from ...extensions import db
from ...models import Post, Report, User
from ...models.base import paginate
from ...utils.auth import token_required
from ...utils.constants import REPORT_PENDING
from ...utils.helpers import current_page_args
from ...utils.logger import write_operation_log
from ...utils.response import error, paginated, success
from ...utils.validators import ValidationError, as_error, clean_text, get_json

bp = Blueprint('reports', __name__, url_prefix='/reports')


@bp.post('')
@token_required
def create_report():
    """提交举报。

    请求体：
        {"post_id": 1, "reason": "虚假信息", "detail": "补充说明"}
    或举报用户：
        {"target_user_id": 2, "reason": "骚扰"}
    """
    from ...utils.auth import current_user

    try:
        user = current_user()
        payload = get_json()
        reason = clean_text(payload.get('reason'), 128, '举报原因', required=True)
        detail = clean_text(payload.get('detail'), 500, '补充说明')

        post_id = payload.get('post_id')
        target_user_id = payload.get('target_user_id')
        if not post_id and not target_user_id:
            raise ValidationError('请指定要举报的帖子或用户')

        if post_id:
            post = Post.query.get(int(post_id))
            if post is None or post.is_deleted:
                return error('举报的帖子不存在', 4001)
            if post.user_id == user.id:
                raise ValidationError('不能举报自己发布的信息')
        if target_user_id:
            if int(target_user_id) == user.id:
                raise ValidationError('不能举报自己')
            if User.query.get(int(target_user_id)) is None:
                return error('举报的用户不存在', 3002)

        # 防重复：同一人对同一目标只保留一条待处理举报
        duplicated = Report.query.filter_by(
            reporter_id=user.id, post_id=post_id, target_user_id=target_user_id, status=REPORT_PENDING
        ).first()
        if duplicated:
            return error('你已举报过该内容，管理员正在处理中')

        report = Report(
            reporter_id=user.id,
            post_id=post_id,
            target_user_id=target_user_id,
            reason=reason,
            detail=detail,
            status=REPORT_PENDING,
        )
        db.session.add(report)
        db.session.commit()
        write_operation_log('report', module='reports', target_type='post' if post_id else 'user',
                            target_id=post_id or target_user_id, detail={'reason': reason})
        return success(report.to_dict(), msg='举报已提交，管理员会尽快处理')
    except ValidationError as exc:
        return as_error(exc)


@bp.get('/my')
@token_required
def my_reports():
    """我的举报记录。"""
    from ...utils.auth import current_user

    try:
        page, size = current_page_args()
        query = Report.query.filter_by(reporter_id=current_user().id).order_by(Report.id.desc())
        items, total, page, size = paginate(query, page, size)
        return paginated([item.to_dict() for item in items], total, page, size)
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
