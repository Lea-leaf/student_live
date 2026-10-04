# -*- coding: utf-8 -*-
"""管理员移交回归测试（系统只允许存在一个管理员）。

覆盖需求：
- 管理员不能直接改自己的角色（让位必须走移交流程）；
- 不能把别人直接改成管理员（换人只能走移交）；
- 移交第一阶段：接班人立刻是管理员但**冻结**（用不了任何后台功能），
  发起人仍是管理员、功能照常，随时可撤销；
- 撤销后接班人的管理员身份被收回，发起人不受影响；
- 24 小时到期后（用手工改时间模拟）自动落地：发起人变普通用户、接班人解冻上任；
- 全程时间以北京时间（UTC+8）为准。
"""

from datetime import timedelta

from tests.conftest import auth_header, login


def _reload(app, user_id):
    from app.models import User

    with app.app_context():
        return User.query.get(user_id)


def _user_id(app, student_id):
    from app.models import User

    with app.app_context():
        return User.query.filter_by(student_id=student_id).first().id


def _create_pending_post(app, user_id, title='待审帖子'):
    """造一条待审核帖子（用于验证冻结期仍能审核）。"""
    from app.extensions import db
    from app.models import Post

    with app.app_context():
        post = Post(type='lost_found', user_id=user_id, title=title,
                    contact='微信 pending123', audit_status='pending')
        db.session.add(post)
        db.session.commit()
        return post.id


# ---------------------------------------------------------------------------
# 1. 单管理员的硬约束
# ---------------------------------------------------------------------------
def test_admin_cannot_change_own_role(client, admin_token, admin):
    """管理员不能直接修改自己的角色 —— 让位必须走移交。"""
    body = client.post(f'/api/v1/admin/users/{admin}/role',
                       json={'role': 'user'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '管理员移交' in body['msg'], body

    # 降成审核员也一样拒绝
    body2 = client.post(f'/api/v1/admin/users/{admin}/role',
                        json={'role': 'auditor'},
                        headers=auth_header(admin_token)).get_json()
    assert body2['code'] == 1001, body2
    assert '管理员移交' in body2['msg'], body2


def test_cannot_promote_other_to_admin(client, admin_token, student):
    """不能把别人直接改成管理员 —— 换人只能走移交。"""
    body = client.post(f'/api/v1/admin/users/{student}/role',
                       json={'role': 'admin'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '只允许存在一个管理员' in body['msg'], body


def test_cannot_delete_admin_account(client, admin_token, admin, app):
    """管理员账号不能被删除（否则会出现"零管理员"）。"""
    body = client.delete(f'/api/v1/admin/users/{admin}',
                         json={'confirm_student_id': 'admin'},
                         headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '不能删除自己' in body['msg'] or '管理员移交' in body['msg'], body


def test_auditor_cannot_reach_handover(client, auditor_token, student):
    """审核员没有移交能力（`admin.handover`），四个接口全部 403。"""
    for method, url in (
        ('get', '/api/v1/admin/handover/status'),
        ('post', '/api/v1/admin/handover'),
        ('post', '/api/v1/admin/handover/cancel'),
        ('post', '/api/v1/admin/handover/finalize'),
    ):
        response = getattr(client, method)(url, json={}, headers=auth_header(auditor_token))
        assert response.status_code == 403, f'{method.upper()} {url}'
        assert response.get_json()['code'] == 2003


# ---------------------------------------------------------------------------
# 2. 第一阶段：发起移交 + 接班人冻结
# ---------------------------------------------------------------------------
def test_handover_start_freezes_target_but_not_initiator(client, admin_token, student, app):
    """发起移交后：目标成为「待上任管理员」，但**按原角色**工作、拿不到管理员特权。"""
    student_token = login(client, '20210001', '123456')

    body = client.post('/api/v1/admin/handover',
                       json={'user_id': student, 'reason': '毕业交接'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0, body
    assert body['data']['handover_to']['student_id'] == '20210001'
    assert body['data']['effective_at'], body

    # 目标：role 变成 admin，但冻结中 —— is_admin 为假、按原角色（普通用户）给能力
    target = _reload(app, student)
    assert target.role == 'admin'
    assert target.is_frozen is True
    assert target.is_admin is False, '冻结中不算管理员（否则发帖会免审核）'
    assert target.capabilities == [], '普通用户接管 → 冻结期没有后台能力'
    assert target.handover_prev_role == 'user', '必须记住原角色以便撤销时恢复'

    me = client.get('/api/v1/auth/me',
                    headers=auth_header(student_token)).get_json()['data']
    assert me['is_admin'] is False
    assert me['is_frozen'] is True
    assert me['capabilities'] == []
    # 身份徽章显示"原身份"，不是"管理员" —— 对外看到的要等于他实际能用的权限
    assert me['role_label'] == '普通用户', me['role_label']

    # 普通用户接管：冻结期进不了后台
    frozen = client.get('/api/v1/admin/dashboard/overview',
                        headers=auth_header(student_token))
    assert frozen.status_code == 403, frozen.get_json()

    # 发起人：仍是管理员，功能照常
    assert _reload(app, _user_id(app, 'admin')).is_frozen is False
    ok = client.get('/api/v1/admin/dashboard/overview',
                    headers=auth_header(admin_token)).get_json()
    assert ok['code'] == 0, ok

    # 状态接口能报出这件事
    status = client.get('/api/v1/admin/handover/status',
                        headers=auth_header(admin_token)).get_json()['data']
    assert status['handover_pending'] is True
    assert status['handover_role'] == 'initiator'
    assert status['handover_to']['student_id'] == '20210001'
    assert status['window_hours'] == 24
    assert status['server_now'], '必须下发服务器北京时间供前端校准'


def test_frozen_auditor_keeps_auditing(client, admin_token, auditor, student2, app):
    """⚠️ 关键场景：接任者原本是**审核员**时，冻结期他必须还能审核。

    这是"一刀切 403"会造成的工作停摆 —— 交接不该让他停工。
    """
    auditor_token = login(client, 'auditor', 'audit123')

    # 冻结前：审核员能进审核台
    assert client.get('/api/v1/admin/posts/pending',
                      headers=auth_header(auditor_token)).get_json()['code'] == 0

    client.post('/api/v1/admin/handover', json={'user_id': auditor},
                headers=auth_header(admin_token))

    target = _reload(app, auditor)
    assert target.is_frozen is True
    assert target.handover_prev_role == 'auditor'
    assert target.is_admin is False, '冻结中不算管理员'

    # 冻结期：审核能力保留（工作不停），管理员能力被收回
    assert target.has_capability('post.audit') is True
    assert target.has_capability('comment.manage') is True
    assert target.has_capability('config.manage') is False
    assert target.has_capability('user.role') is False
    assert target.has_capability('module.manage') is False

    me = client.get('/api/v1/auth/me', headers=auth_header(auditor_token)).get_json()['data']
    assert me['role_label'] == '内容审核员', '徽章显示原身份，不是管理员'
    assert 'post.audit' in me['capabilities']
    assert 'config.manage' not in me['capabilities']

    # 真的还能用：审核台可访问、能审帖
    pending = client.get('/api/v1/admin/posts/pending',
                         headers=auth_header(auditor_token)).get_json()
    assert pending['code'] == 0, pending

    post_id = _create_pending_post(app, student2)
    audited = client.post(f'/api/v1/admin/posts/{post_id}/audit',
                          json={'audit_status': 'approved', 'remark': '交接期照常审核'},
                          headers=auth_header(auditor_token)).get_json()
    assert audited['code'] == 0, audited

    # 但系统管理类接口一律进不去
    for url in ('/api/v1/admin/configs', '/api/v1/admin/modules', '/api/v1/admin/logs/operations'):
        resp = client.get(url, headers=auth_header(auditor_token))
        assert resp.status_code == 403, f'{url} -> {resp.get_json()}'


def test_frozen_target_post_still_needs_audit(client, admin_token, student, app):
    """冻结期他发的帖子**仍要走审核** —— 还没正式上任，不该有管理员特权。"""
    client.post('/api/v1/admin/handover', json={'user_id': student},
                headers=auth_header(admin_token))
    student_token = login(client, '20210001', '123456')

    posted = client.post('/api/v1/lost_found/posts',
                         json={'type': 'lost_found', 'title': '交接期发的帖子',
                               'contact': '微信 frozen_test'},
                         headers=auth_header(student_token)).get_json()
    assert posted['code'] == 0, posted
    assert posted['data']['audit_status'] == 'pending', '冻结中不得免审核'
    # 他自己也不能审（禁止自审）
    assert posted['data']['user_id'] == student


def test_cancel_restores_previous_role(client, admin_token, auditor, admin, app):
    """撤销移交要**恢复到接管前的角色**，不能一律降成普通用户。"""
    client.post('/api/v1/admin/handover', json={'user_id': auditor},
                headers=auth_header(admin_token))
    assert _reload(app, auditor).handover_prev_role == 'auditor'

    cancelled = client.post('/api/v1/admin/handover/cancel',
                            headers=auth_header(admin_token)).get_json()
    assert cancelled['code'] == 0, cancelled

    target = _reload(app, auditor)
    assert target.role == 'auditor', '原本是审核员就必须还原成审核员'
    assert target.is_frozen is False
    assert target.handover_prev_role is None
    assert target.has_capability('post.audit') is True
    assert target.has_capability('config.manage') is False

    # 发起人不受影响
    assert _reload(app, admin).role == 'admin'


def test_handover_rejects_self_and_banned(client, admin_token, admin, student, app):
    """不能移交给自己；被封禁的账号不能接管。"""
    body = client.post('/api/v1/admin/handover',
                       json={'user_id': admin},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '自己' in body['msg']

    # 封禁目标后再移交
    client.post(f'/api/v1/admin/users/{student}/ban',
                json={'reason': '测试'}, headers=auth_header(admin_token))
    body2 = client.post('/api/v1/admin/handover',
                        json={'user_id': student},
                        headers=auth_header(admin_token)).get_json()
    assert body2['code'] == 1001, body2
    assert '封禁' in body2['msg']


# ---------------------------------------------------------------------------
# 3. 撤销（反悔期）
# ---------------------------------------------------------------------------
def test_handover_cancel_restores_everything(client, admin_token, student, admin, app):
    """撤销后：接班人回到普通用户、解除冻结；发起人仍是管理员。"""
    client.post('/api/v1/admin/handover', json={'user_id': student},
                headers=auth_header(admin_token))

    cancelled = client.post('/api/v1/admin/handover/cancel',
                            headers=auth_header(admin_token)).get_json()
    assert cancelled['code'] == 0, cancelled

    target = _reload(app, student)
    assert target.role == 'user'
    assert target.is_frozen is False
    assert target.capabilities == []

    initiator = _reload(app, admin)
    assert initiator.role == 'admin'
    assert initiator.handover_to_id is None
    assert initiator.handover_effective_at is None

    # 取消后可以重新发起
    again = client.post('/api/v1/admin/handover', json={'user_id': student},
                        headers=auth_header(admin_token)).get_json()
    assert again['code'] == 0, again

    status = client.get('/api/v1/admin/handover/status',
                        headers=auth_header(admin_token)).get_json()['data']
    assert status['handover_pending'] is True


def test_cancel_without_pending_handover(client, admin_token):
    body = client.post('/api/v1/admin/handover/cancel',
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body  # ValidationError → 参数错误码
    assert '没有进行中' in body['msg']


# ---------------------------------------------------------------------------
# 4. 第二阶段：24 小时到期自动落地
# ---------------------------------------------------------------------------
def test_handover_finalizes_after_24h(client, admin_token, student, app):
    """到期后：发起人变普通用户，接班人解冻上任（懒执行，无需定时任务）。"""
    from app.utils import handover as ho

    client.post('/api/v1/admin/handover', json={'user_id': student},
                headers=auth_header(admin_token))

    # 把生效时间改到过去，模拟"24 小时已过"
    from app.extensions import db

    with app.app_context():
        from app.models import User

        initiator = User.query.get(_user_id(app, 'admin'))
        initiator.handover_effective_at = ho.now_beijing() - timedelta(minutes=1)
        db.session.commit()

    # 任意一次后台接口访问都会触发结算（这里用接班人的请求）
    student_token = login(client, '20210001', '123456')
    settled = client.get('/api/v1/admin/dashboard/overview',
                         headers=auth_header(student_token)).get_json()
    assert settled['code'] == 0, settled

    # 接班人已解冻、正式上任
    target = _reload(app, student)
    assert target.role == 'admin'
    assert target.is_frozen is False
    assert 'user.role' in target.capabilities

    # 发起人已降为普通用户，且旧 token 再也进不了后台
    initiator = _reload(app, _user_id(app, 'admin'))
    assert initiator.role == 'user'
    assert initiator.is_admin is False
    assert initiator.handover_to_id is None

    denied = client.get('/api/v1/admin/dashboard/overview',
                        headers=auth_header(admin_token))
    assert denied.status_code == 403, denied.get_json()


def test_handover_finalize_endpoint_requires_due(client, admin_token, student):
    """未到期时手动结算应被拒绝（它是演示/排障用的兜底入口）。"""
    client.post('/api/v1/admin/handover', json={'user_id': student},
                headers=auth_header(admin_token))
    body = client.post('/api/v1/admin/handover/finalize',
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1, body
    assert '没有已到期' in body['msg']


def test_handover_converges_to_single_admin(client, admin_token, student, app):
    """即使库里被手工造出多个管理员，发起移交时也会收敛成一个。"""
    from app.extensions import db
    from app.models import User
    from tests.conftest import _create_user

    extra_admin = _create_user(app, 'admin9', 'admin123', role='admin', nickname='历史残留管理员')
    with app.app_context():
        assert User.query.filter_by(role='admin').count() == 2

    client.post('/api/v1/admin/handover', json={'user_id': student},
                headers=auth_header(admin_token))

    # 残留管理员被降为普通用户，只剩发起人与接班人
    assert _reload(app, extra_admin).role == 'user'
    with app.app_context():
        admins = {u.student_id for u in User.query.filter_by(role='admin').all()}
    assert admins == {'admin', '20210001'}, admins


# ---------------------------------------------------------------------------
# 5. 北京时间
# ---------------------------------------------------------------------------
def test_handover_candidates_are_not_admins(client, admin_token, student, auditor, app):
    """可选接任者必须是"非管理员"的账号。

    ⚠️ 这是一个曾经踩过的设计错误：最初把候选写成"现有管理员列表（排除自己）"，
    而系统只允许一个管理员 —— 排除自己后**永远是空列表**，谁都移交不了。
    接任者的正确语义是"从普通用户 / 审核员里挑一个，选中后升为管理员"。
    """
    status = client.get('/api/v1/admin/handover/status',
                        headers=auth_header(admin_token)).get_json()['data']
    values = {item['id'] for item in status['candidates']}

    assert student in values, '普通用户应当可以作为接任者'
    assert auditor in values, '审核员也应当可以作为接任者'
    assert _user_id(app, 'admin') not in values, '不能把自己列为接任者'
    assert len(values) >= 2, f'候选列表不应为空（当前 {values}）'

    # 候选里不能出现已经是管理员的账号
    for item in status['candidates']:
        assert item['role'] != 'admin', item

    # 可以把审核员作为接任者发起移交
    body = client.post('/api/v1/admin/handover', json={'user_id': auditor},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0, body

    # 不能移交给已经是管理员的账号（历史残留场景）
    client.post('/api/v1/admin/handover/cancel', headers=auth_header(admin_token))
    from tests.conftest import _create_user

    other_admin = _create_user(app, 'admin8', 'admin123', role='admin', nickname='另一管理员')
    dup = client.post('/api/v1/admin/handover', json={'user_id': other_admin},
                      headers=auth_header(admin_token)).get_json()
    assert dup['code'] == 1001, dup
    assert '已经是管理员' in dup['msg']


def test_beijing_time_helpers():
    """时间口径：UTC+8 固定偏移，且与 UTC 相差 8 小时。"""
    from datetime import datetime, timezone

    from app.utils import handover as ho

    now_bj = ho.now_beijing()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    offset_hours = round((now_bj - now_utc).total_seconds() / 3600, 1)
    assert offset_hours == 8.0, offset_hours

    start = ho.now_beijing()
    deadline = ho.handover_deadline(start)
    assert (deadline - start) == timedelta(hours=24)
    assert ho.HANDOVER_WINDOW_HOURS == 24
