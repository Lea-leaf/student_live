# -*- coding: utf-8 -*-
"""内容审核员（auditor）权限矩阵与审核指派回归测试。

覆盖三类问题（对应 docs/USER_FIELDS.md 的 P5 / P6 / P7 与审计 #2 的 D2 / D3）：

1. **角色与权限**：审核员能进后台，但**拿不到管理员特权**
   （改系统配置、重置密码、改角色、模块管理、日志、回收站、媒体清理一律 403）；
2. **内容处置**：审核员能审帖 / 删帖 / 置顶 / 删评论 / 处理举报，
   但**不能改他人正文**，也**不能审自己的帖子**；
3. **指派与认领**：管理员可指派 / 改派 / 收回；审核员可自助认领，
   并发下**先到先得**（第二个人拿到 4005），认领超时自动退回公共池。
"""

from tests.conftest import auth_header, login


def _create_post(app, user_id, title='待审帖子', audit_status='pending'):
    from app.extensions import db
    from app.models import Post

    with app.app_context():
        post = Post(type='lost_found', user_id=user_id, title=title,
                    contact='微信 test123', audit_status=audit_status)
        db.session.add(post)
        db.session.commit()
        return post.id


def _user_id(app, student_id):
    from app.models import User

    with app.app_context():
        return User.query.filter_by(student_id=student_id).first().id


# ---------------------------------------------------------------------------
# 1. 角色标识与能力
# ---------------------------------------------------------------------------
def test_admin_and_auditor_are_distinguishable(app, auditor, admin, student):
    """身份标识：审核员能进后台（is_staff）但不是管理员（is_admin）。"""
    from app.models import User

    with app.app_context():
        aud = User.query.get(auditor)
        adm = User.query.get(admin)
        stu = User.query.get(student)

        assert aud.is_staff is True and aud.is_admin is False
        assert adm.is_staff is True and adm.is_admin is True
        assert stu.is_staff is False and stu.is_admin is False

        # 序列化里带身份标识与能力清单，前端据此渲染徽章与菜单
        data = aud.to_dict()
        assert data['identity'] == 'staff'
        assert data['role_label'] == '内容审核员'
        assert 'post.audit' in data['capabilities']
        assert 'config.manage' not in data['capabilities']
        assert 'user.role' not in data['capabilities']

        assert stu.to_dict()['identity'] == 'user'
        assert stu.to_dict()['capabilities'] == []


def test_auditor_capability_matrix():
    """能力表本身：审核员有内容处置权，没有系统管理权。"""
    from app.utils.constants import (
        CAP_COMMENT_MANAGE,
        CAP_CONFIG_MANAGE,
        CAP_LOG_VIEW,
        CAP_MEDIA_CLEAN,
        CAP_MODULE_MANAGE,
        CAP_POST_AUDIT,
        CAP_POST_MANAGE,
        CAP_REPORT_HANDLE,
        CAP_TRASH_MANAGE,
        CAP_USER_DETAIL,
        CAP_USER_MANAGE,
        CAP_USER_ROLE,
        CAP_USER_VIEW,
        has_capability,
    )

    granted = (CAP_POST_AUDIT, CAP_POST_MANAGE, CAP_COMMENT_MANAGE,
               CAP_REPORT_HANDLE, CAP_USER_VIEW, CAP_USER_MANAGE)
    denied = (CAP_CONFIG_MANAGE, CAP_MODULE_MANAGE, CAP_LOG_VIEW,
              CAP_TRASH_MANAGE, CAP_MEDIA_CLEAN, CAP_USER_DETAIL)

    for cap in granted:
        assert has_capability('auditor', cap) is True, cap
    for cap in denied:
        assert has_capability('auditor', cap) is False, cap

    # 管理员是最高等级，持通配能力：以上全部都有（含审核员没有的那些）
    for cap in granted + denied:
        assert has_capability('admin', cap) is True, cap

    # 改角色（任命审核员）是管理员专有 —— 审核员没有（需求原文）
    from app.utils.constants import CAP_USER_ROLE

    assert has_capability('admin', CAP_USER_ROLE) is True
    assert has_capability('auditor', CAP_USER_ROLE) is False


def test_role_structure_is_three_tiers():
    """角色结构收敛成三层：user / auditor / admin（super_admin 已移除）。"""
    from app.utils.constants import (
        ADMIN_ROLES,
        RESERVED_ROLE_LABELS,
        ROLE_ADMIN,
        ROLE_AUDITOR,
        ROLE_LABELS,
        ROLES,
        ROLE_USER,
        TRUE_ADMIN_ROLES,
    )

    assert ROLES == (ROLE_USER, ROLE_ADMIN, ROLE_AUDITOR), ROLES
    assert set(ROLE_LABELS) == {ROLE_USER, ROLE_ADMIN, ROLE_AUDITOR}
    assert ADMIN_ROLES == (ROLE_ADMIN, ROLE_AUDITOR)
    assert TRUE_ADMIN_ROLES == (ROLE_ADMIN,)

    # super_admin 已彻底移除：不再是角色、没有中文名、不可能是后台角色
    assert 'super_admin' not in ROLES
    assert 'super_admin' not in ROLE_LABELS
    assert 'super_admin' not in ADMIN_ROLES
    assert 'super_admin' not in TRUE_ADMIN_ROLES

    # 三个预留角色只存在于"预留说明"里，不在可分配名单中
    assert set(RESERVED_ROLE_LABELS) == {'user_admin', 'module_admin', 'moderator'}
    for reserved in RESERVED_ROLE_LABELS:
        assert reserved not in ROLES, reserved


def test_reserved_roles_cannot_be_assigned(client, admin_token, student):
    """预留角色虽有能力初稿，但不在 ROLES 里 → 接口拒绝分配。"""
    for reserved in ('moderator', 'user_admin', 'module_admin', 'super_admin'):
        body = client.post(f'/api/v1/admin/users/{student}/role',
                           json={'role': reserved},
                           headers=auth_header(admin_token)).get_json()
        assert body['code'] == 1001, f'{reserved} -> {body}'
        assert '角色取值非法' in body['msg'], body


def test_admin_can_appoint_auditor(client, admin_token, student):
    """管理员可以任命审核员（这是「管理员指定审核员」的入口）。"""
    body = client.post(f'/api/v1/admin/users/{student}/role',
                       json={'role': 'auditor'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0, body
    assert body['data']['role'] == 'auditor'
    assert body['data']['role_label'] == '内容审核员'
    assert body['data']['is_staff'] is True and body['data']['is_admin'] is False
    assert 'post.audit' in body['data']['capabilities']

    # 能改回去
    back = client.post(f'/api/v1/admin/users/{student}/role',
                       json={'role': 'user'},
                       headers=auth_header(admin_token)).get_json()
    assert back['code'] == 0, back
    assert back['data']['is_staff'] is False


def test_admin_cannot_demote_self(client, admin_token, admin):
    """管理员不能取消自己的管理员权限（否则谁也进不去后台）。"""
    body = client.post(f'/api/v1/admin/users/{admin}/role',
                       json={'role': 'user'},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '自己' in body['msg']


def test_admin_can_manage_other_admin(client, admin_token, app):
    """管理员之间完全平级：可以互相处置（不再有"上级才能动下级"的假限制）。"""
    from tests.conftest import _create_user
    from app.utils.constants import ROLE_ADMIN

    other_admin = _create_user(app, 'admin2', 'admin123', role=ROLE_ADMIN, nickname='管理员二号')

    # 可以封禁另一个管理员
    banned = client.post(f'/api/v1/admin/users/{other_admin}/ban',
                         json={'reason': '测试平级处置'},
                         headers=auth_header(admin_token)).get_json()
    assert banned['code'] == 0, banned
    assert banned['data']['status'] == 'banned'

    # 可以解封
    assert client.post(f'/api/v1/admin/users/{other_admin}/unban',
                       headers=auth_header(admin_token)).get_json()['code'] == 0

    # 可以重置另一个管理员的密码
    assert client.post(f'/api/v1/admin/users/{other_admin}/reset-password',
                       json={}, headers=auth_header(admin_token)).get_json()['code'] == 0

    # 但不能重置自己的密码（避免绕开"需校验原密码"的改密流程）
    body = client.post(f'/api/v1/admin/users/{_user_id(app, "admin")}/reset-password',
                       json={}, headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body


def test_module_permission_decorator_is_reserved_not_wired():
    """预留设施现状：装饰器存在但零调用，表也没有写入接口（P8 未关闭）。"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / 'app'
    call_sites = []
    for path in root.rglob('*.py'):
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if 'module_permission_required(' in line and 'def ' not in line:
                call_sites.append(f'{path.name}:{lineno}')
    assert call_sites == [], f'预留装饰器被接上了，需要同步更新文档：{call_sites}'


# ---------------------------------------------------------------------------
# 2. 审核员能进后台，但进不了系统管理类接口
# ---------------------------------------------------------------------------
def test_auditor_can_reach_content_endpoints(client, auditor_token, sample_post):
    """审核员可访问：审核台、内容列表、评论、举报、概览。"""
    for url in ('/api/v1/admin/dashboard/overview',
                '/api/v1/admin/posts/pending',
                '/api/v1/admin/posts',
                '/api/v1/admin/comments',
                '/api/v1/admin/reports',
                '/api/v1/admin/users'):
        body = client.get(url, headers=auth_header(auditor_token)).get_json()
        assert body['code'] == 0, f'{url} -> {body}'


def test_auditor_blocked_from_system_endpoints(client, auditor_token):
    """审核员一律 403：系统配置、模块、日志、回收站、改角色、重置密码、用户明细。"""
    blocked = [
        ('get', '/api/v1/admin/configs'),
        ('put', '/api/v1/admin/configs'),
        ('post', '/api/v1/admin/configs/reset'),
        ('get', '/api/v1/admin/modules'),
        ('post', '/api/v1/admin/modules'),
        ('get', '/api/v1/admin/logs/operations'),
        ('get', '/api/v1/admin/logs/logins'),
        ('get', '/api/v1/admin/trash'),
        ('get', '/api/v1/admin/trash/stats'),
        ('post', '/api/v1/admin/trash/cleanup'),
        # 媒体用量涉及全体用户的磁盘路径，属系统级信息，审核员看不到
        ('get', '/api/v1/admin/dashboard/media'),
        ('post', '/api/v1/admin/dashboard/media/clean'),
    ]
    for method, url in blocked:
        response = getattr(client, method)(url, headers=auth_header(auditor_token))
        assert response.status_code == 403, f'{method.upper()} {url}'
        assert response.get_json()['code'] == 2003, f'{method.upper()} {url}'


def test_auditor_cannot_touch_user_details_or_roles(client, auditor_token, admin_token,
                                                    student, admin):
    """审核员能看用户详情的**基础资料**，但拿不到敏感字段，也不能改角色 / 重置密码。

    需求原文："不可以重置密码、看详情与发帖记录" —— 这里落实为权限分层：
    - `user.view`（审核员有）：详情接口可用，但**不下发**邮箱 / 手机号；
    - `user.detail`（仅管理员）：发帖记录 / 登录日志 / 媒体清单 / 重置密码 / 备注 / 建号 / 删除。
    """
    # 详情页可打开，但敏感字段被剔除
    detail = client.get(f'/api/v1/admin/users/{student}',
                        headers=auth_header(auditor_token))
    assert detail.status_code == 200, detail.get_json()
    body = detail.get_json()
    assert body['code'] == 0, body
    assert body['data']['user']['student_id'] == '20210001'
    assert 'email' not in body['data']['user'], body['data']['user']
    assert 'phone' not in body['data']['user'], body['data']['user']
    # 基础统计仍然可见
    assert 'post_total' in body['data']['stats']

    # 管理员看同一个接口时才有敏感字段
    admin_view = client.get(f'/api/v1/admin/users/{student}',
                            headers=auth_header(admin_token)).get_json()
    assert 'email' in admin_view['data']['user'], admin_view['data']['user']

    # 以下仍然一律 403：敏感明细与特权操作
    blocked = [
        ('get', f'/api/v1/admin/users/{student}/posts'),
        ('get', f'/api/v1/admin/users/{student}/logs'),
        ('get', f'/api/v1/admin/users/{student}/media'),
        ('post', f'/api/v1/admin/users/{student}/reset-password'),
        ('post', f'/api/v1/admin/users/{student}/remark'),
        ('post', f'/api/v1/admin/users/{student}/role'),
        ('post', '/api/v1/admin/users'),
        ('delete', f'/api/v1/admin/users/{student}'),
    ]
    for method, url in blocked:
        response = getattr(client, method)(url, json={}, headers=auth_header(auditor_token))
        assert response.status_code == 403, f'{method.upper()} {url}'
        assert response.get_json()['code'] == 2003, f'{method.upper()} {url}'


# ---------------------------------------------------------------------------
# 3. 审核员只能封禁普通用户
# ---------------------------------------------------------------------------
def test_auditor_can_ban_ordinary_user(client, auditor_token, student, student_token):
    """审核员可以封禁普通用户（需求：「管理普通用户」）。"""
    body = client.post(f'/api/v1/admin/users/{student}/ban',
                       json={'reason': '发布违规内容'},
                       headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 0, body
    assert body['data']['status'] == 'banned'
    # 封禁即时生效
    assert client.get('/api/v1/auth/me',
                      headers=auth_header(student_token)).get_json()['code'] == 2004


def test_auditor_cannot_ban_staff(client, auditor_token, auditor2, admin):
    """审核员不能封禁其他审核员 / 管理员（同级与上级都不可处置）。"""
    for target in (auditor2, admin):
        body = client.post(f'/api/v1/admin/users/{target}/ban',
                           json={'reason': '越权测试'},
                           headers=auth_header(auditor_token)).get_json()
        assert body['code'] == 2003, body


def test_auditor_batch_ban_skips_staff(client, auditor_token, student, auditor2):
    """批量封禁里同样跳过后台角色，只封普通用户。"""
    body = client.post('/api/v1/admin/users/batch/ban',
                       json={'user_ids': [student, auditor2], 'reason': '批量测试'},
                       headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 0, body
    assert body['data']['affected'] == 1
    assert auditor2 in body['data']['skipped']


# ---------------------------------------------------------------------------
# 4. 审核员的内容处置权与边界
# ---------------------------------------------------------------------------
def test_auditor_can_audit_and_delete_post(client, auditor_token, student, sample_post):
    """审核员能通过 / 拒绝帖子，也能删帖、置顶、改业务状态。"""
    # 先造一条待审帖（sample_post 是已通过的）
    pending_id = _create_post(client.application, student, title='审核员待审帖')

    body = client.post(f'/api/v1/admin/posts/{pending_id}/audit',
                       json={'audit_status': 'approved', 'remark': '内容合规'},
                       headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 0, body
    assert body['data']['audit_status'] == 'approved'

    # 置顶 + 改状态
    assert client.post(f'/api/v1/admin/posts/{sample_post}/top',
                       json={'is_top': True},
                       headers=auth_header(auditor_token)).get_json()['code'] == 0
    assert client.post(f'/api/v1/admin/posts/{sample_post}/status',
                       json={'status': 'closed'},
                       headers=auth_header(auditor_token)).get_json()['code'] == 0

    # 删帖（软删除进回收站）
    assert client.delete(f'/api/v1/admin/posts/{sample_post}',
                         headers=auth_header(auditor_token)).get_json()['code'] == 0


def test_auditor_cannot_edit_post_content(client, auditor_token, sample_post, admin_token):
    """审核员不能改他人正文（改内容属发布者权利），管理员可以。"""
    body = client.put(f'/api/v1/admin/posts/{sample_post}',
                      json={'contact': '微信 hacker'},
                      headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 2003, body

    ok = client.put(f'/api/v1/admin/posts/{sample_post}',
                    json={'contact': '微信 adminfix'},
                    headers=auth_header(admin_token)).get_json()
    assert ok['code'] == 0, ok


def test_admin_post_is_not_audited_but_auditor_post_is(client, admin_token, auditor_token, app):
    """发帖免审只给真正的管理员；审核员的帖子必须走审核。"""
    payload = {'type': 'lost_found', 'title': '免审测试', 'contact': '微信 abc123'}

    admin_body = client.post('/api/v1/lost_found/posts', json=payload,
                             headers=auth_header(admin_token)).get_json()
    assert admin_body['code'] == 0, admin_body
    assert admin_body['data']['audit_status'] == 'approved'

    auditor_body = client.post('/api/v1/lost_found/posts', json=payload,
                               headers=auth_header(auditor_token)).get_json()
    assert auditor_body['code'] == 0, auditor_body
    assert auditor_body['data']['audit_status'] == 'pending'


def test_cannot_audit_own_post(client, auditor_token, auditor, admin_token, app):
    """禁止自审：谁都不能审自己的帖子（审核员与管理员的帖子都拦住）。"""
    own_post = _create_post(app, auditor, title='审核员自己的帖子')

    body = client.post(f'/api/v1/admin/posts/{own_post}/audit',
                       json={'audit_status': 'approved'},
                       headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 2003, body
    assert '自己' in body['msg']

    # 换另一个审核员 / 管理员来审就可以
    assert client.post(f'/api/v1/admin/posts/{own_post}/audit',
                       json={'audit_status': 'approved'},
                       headers=auth_header(admin_token)).get_json()['code'] == 0

    # 管理员的帖子自己也不能审
    admin_id = _user_id(app, 'admin')
    admin_post = _create_post(app, admin_id, title='管理员自己的帖子')
    body2 = client.post(f'/api/v1/admin/posts/{admin_post}/audit',
                        json={'audit_status': 'approved'},
                        headers=auth_header(admin_token)).get_json()
    assert body2['code'] == 2003, body2


def test_auditor_cannot_delete_comment_via_user_api(client, auditor_token, student, sample_post, app):
    """审核员不能借用户端接口无限删评论（P6 修复点）。"""
    from app.extensions import db
    from app.models import Comment

    with app.app_context():
        comment = Comment(post_id=sample_post, user_id=student, content='一条普通评论')
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id

    # 审核员在用户端调用：按"只能撤回自己 5 分钟内的评论"规则处理
    body = client.delete(f'/api/v1/comments/{comment_id}',
                         headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 2003, body

    # 但走管理端接口就可以删（有操作日志与权限校验）
    ok = client.delete(f'/api/v1/admin/comments/{comment_id}',
                       headers=auth_header(auditor_token)).get_json()
    assert ok['code'] == 0, ok


# ---------------------------------------------------------------------------
# 5. 指派 / 认领 / 改派 / 收回
# ---------------------------------------------------------------------------
def test_admin_assign_and_reassign_and_recall(client, admin_token, auditor, auditor2,
                                              student, app):
    """管理员可指派、改派、收回；非管理员不能指派。"""
    post_id = _create_post(app, student, title='待指派帖子')
    url = f'/api/v1/admin/posts/{post_id}/assign'

    body = client.post(url, json={'assignee_id': auditor},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 0, body

    detail = client.get(f'/api/v1/admin/posts/{post_id}',
                        headers=auth_header(admin_token)).get_json()['data']
    assert detail['assignee_id'] == auditor
    assert detail['assignee']['student_id'] == 'auditor'

    # 改派给第二个审核员
    body2 = client.post(url, json={'assignee_id': auditor2},
                        headers=auth_header(admin_token)).get_json()
    assert body2['code'] == 0, body2

    # 收回公共池
    body3 = client.post(url, json={'assignee_id': None},
                        headers=auth_header(admin_token)).get_json()
    assert body3['code'] == 0, body3
    detail3 = client.get(f'/api/v1/admin/posts/{post_id}',
                         headers=auth_header(admin_token)).get_json()['data']
    assert detail3['assignee_id'] is None


def test_assign_requires_admin(client, auditor_token, auditor2, student, app):
    """审核员之间不能互相指派（只有管理员能指派）。"""
    post_id = _create_post(app, student, title='审核员越权指派')
    body = client.post(f'/api/v1/admin/posts/{post_id}/assign',
                       json={'assignee_id': auditor2},
                       headers=auth_header(auditor_token)).get_json()
    assert body['code'] == 2003, body


def test_assign_rejects_author_and_non_auditor(client, admin_token, auditor, student, app):
    """不能把帖子指派给作者本人（自审），也不能指派给没有审核权限的普通用户。"""
    post_id = _create_post(app, student, title='指派校验')
    url = f'/api/v1/admin/posts/{post_id}/assign'

    # 普通用户没有审核能力 → 直接拒绝
    body = client.post(url, json={'assignee_id': student},
                       headers=auth_header(admin_token)).get_json()
    assert body['code'] == 1001, body
    assert '审核权限' in body['msg']

    # 把帖子作者设成审核员后，仍然不能指派给他（禁止自审）
    from app.extensions import db
    from app.models import User

    with app.app_context():
        User.query.get(student).role = 'auditor'
        db.session.commit()

    body2 = client.post(url, json={'assignee_id': student},
                        headers=auth_header(admin_token)).get_json()
    assert body2['code'] == 1001, body2
    assert '自审' in body2['msg']


def test_claim_is_first_come_first_served(client, auditor_token, auditor2_token,
                                         student, app):
    """先到先得：第一个认领成功，第二个收到 4005「已被认领」。"""
    post_id = _create_post(app, student, title='抢单测试')
    url = f'/api/v1/admin/posts/{post_id}/claim'

    first = client.post(url, headers=auth_header(auditor_token)).get_json()
    assert first['code'] == 0, first
    assert first['data']['assignee_id'] == _user_id(app, 'auditor')

    second = client.post(url, headers=auth_header(auditor2_token)).get_json()
    assert second['code'] == 4005, second
    assert '已被' in second['msg']


def test_claim_sets_expiry_and_release_returns_to_pool(client, auditor_token, student, app):
    """认领会带 24 小时到期时间；放弃认领后回到公共池。"""
    post_id = _create_post(app, student, title='到期与放弃')
    claim = client.post(f'/api/v1/admin/posts/{post_id}/claim',
                        headers=auth_header(auditor_token)).get_json()
    assert claim['code'] == 0, claim
    assert claim['data']['assignment_expires_at'] is not None

    released = client.post(f'/api/v1/admin/posts/{post_id}/release',
                           headers=auth_header(auditor_token)).get_json()
    assert released['code'] == 0, released
    assert released['data']['assignee_id'] is None


def test_expired_claim_returns_to_pool(client, auditor_token, auditor2_token, student, app):
    """认领超时后自动回到公共池，其他人可以再认领。"""
    from datetime import datetime, timedelta

    from app.extensions import db
    from app.models import Post

    post_id = _create_post(app, student, title='超时退回')
    assert client.post(f'/api/v1/admin/posts/{post_id}/claim',
                       headers=auth_header(auditor_token)).get_json()['code'] == 0

    # 手工把到期时间改到过去，模拟「认领后一直没处理」
    with app.app_context():
        post = Post.query.get(post_id)
        post.assignment_expires_at = datetime.now() - timedelta(hours=1)
        db.session.commit()

    # 待审列表触发懒执行：退回公共池
    listing = client.get('/api/v1/admin/posts/pending?scope=pool',
                         headers=auth_header(auditor2_token)).get_json()
    ids = [row['id'] for row in listing['data']['list']]
    assert post_id in ids

    # 第二个人现在能认领了
    again = client.post(f'/api/v1/admin/posts/{post_id}/claim',
                        headers=auth_header(auditor2_token)).get_json()
    assert again['code'] == 0, again
    assert again['data']['assignee_id'] == _user_id(app, 'auditor2')


def test_auditor_can_only_audit_own_or_pool(client, auditor_token, auditor2_token,
                                            admin_token, student, auditor2, app):
    """审批归属：已指派给别人的帖子，其他审核员审不了（管理员不受限）。"""
    post_id = _create_post(app, student, title='归属校验')
    assert client.post(f'/api/v1/admin/posts/{post_id}/claim',
                       headers=auth_header(auditor_token)).get_json()['code'] == 0

    body = client.post(f'/api/v1/admin/posts/{post_id}/audit',
                       json={'audit_status': 'approved'},
                       headers=auth_header(auditor2_token)).get_json()
    assert body['code'] == 4005, body

    # 管理员可以直接审（需求：管理员仍可直接审帖，不强制先指派）
    ok = client.post(f'/api/v1/admin/posts/{post_id}/audit',
                     json={'audit_status': 'approved'},
                     headers=auth_header(admin_token)).get_json()
    assert ok['code'] == 0, ok


def test_pending_scope_filters(client, auditor_token, student, app):
    """待审列表支持 mine / pool 过滤，并返回 stats。"""
    pool_post = _create_post(app, student, title='公共池帖子')
    mine_post = _create_post(app, student, title='我的帖子')
    assert client.post(f'/api/v1/admin/posts/{mine_post}/claim',
                       headers=auth_header(auditor_token)).get_json()['code'] == 0

    mine = client.get('/api/v1/admin/posts/pending?scope=mine',
                      headers=auth_header(auditor_token)).get_json()
    assert mine['data']['stats']['mine'] == 1
    assert [row['id'] for row in mine['data']['list']] == [mine_post]

    pool = client.get('/api/v1/admin/posts/pending?scope=pool',
                      headers=auth_header(auditor_token)).get_json()
    assert pool_post in [row['id'] for row in pool['data']['list']]
    assert mine_post not in [row['id'] for row in pool['data']['list']]


# ---------------------------------------------------------------------------
# 6. 审核流水与工作量统计
# ---------------------------------------------------------------------------
def test_audit_logs_trace_the_whole_lifecycle(client, admin_token, auditor_token,
                                              auditor2_token, auditor, student, app):
    """流水账：指派 → 改派 → 认领 → 通过，每一步都留痕。"""
    post_id = _create_post(app, student, title='流水测试')
    client.post(f'/api/v1/admin/posts/{post_id}/assign',
                json={'assignee_id': auditor}, headers=auth_header(admin_token))
    client.post(f'/api/v1/admin/posts/{post_id}/assign',
                json={'assignee_id': _user_id(app, 'auditor2')},
                headers=auth_header(admin_token))
    client.post(f'/api/v1/admin/posts/{post_id}/release',
                headers=auth_header(admin_token))
    client.post(f'/api/v1/admin/posts/{post_id}/claim',
                headers=auth_header(auditor_token))
    client.post(f'/api/v1/admin/posts/{post_id}/audit',
                json={'audit_status': 'approved', 'remark': 'ok'},
                headers=auth_header(auditor_token))

    logs = client.get(f'/api/v1/admin/posts/{post_id}/audit-logs',
                      headers=auth_header(admin_token)).get_json()
    assert logs['code'] == 0, logs
    actions = [row['action'] for row in logs['data']['list']]
    assert actions == ['assign', 'assign', 'release', 'claim', 'approve'], actions

    # 每条流水都能翻译出操作人与被指派人（身份可追溯）
    claim_row = [r for r in logs['data']['list'] if r['action'] == 'claim'][0]
    assert claim_row['assignee']['student_id'] == 'auditor'
    assert claim_row['assign_source'] == 'self'

    approve_row = logs['data']['list'][-1]
    assert approve_row['duration_ms'] is not None


def test_audit_assignees_panel(client, admin_token, auditor_token, auditor, student, app):
    """分配面板：管理员能拿到审核员名单与各自待审数；审核员拿到空列表。"""
    post_id = _create_post(app, student, title='面板测试')
    client.post(f'/api/v1/admin/posts/{post_id}/assign',
                json={'assignee_id': auditor}, headers=auth_header(admin_token))

    panel = client.get('/api/v1/admin/posts/audit-assignees',
                       headers=auth_header(admin_token)).get_json()
    assert panel['code'] == 0, panel
    rows = panel['data']['list']
    assert any(row['student_id'] == 'auditor' for row in rows)
    assert panel['data']['pending_by_assignee'].get(str(auditor)) == 1

    # 审核员不需要知道同事的负载
    aud_panel = client.get('/api/v1/admin/posts/audit-assignees',
                           headers=auth_header(auditor_token)).get_json()
    assert aud_panel['data']['list'] == []


# ---------------------------------------------------------------------------
# 7. 回归：普通用户仍然进不了后台
# ---------------------------------------------------------------------------
def test_ordinary_user_still_blocked(client, student_token, sample_post):
    """引入审核员后，普通用户的后台门禁不能松动。"""
    for url in ('/api/v1/admin/dashboard/overview', '/api/v1/admin/users',
                '/api/v1/admin/posts', '/api/v1/admin/posts/pending',
                '/api/v1/admin/comments', '/api/v1/admin/reports'):
        response = client.get(url, headers=auth_header(student_token))
        assert response.status_code == 403, url
        assert response.get_json()['code'] == 2003, url


def test_auditor_login_flow(client, auditor, auditor_token):
    """审核员能正常登录，并在 /auth/me 拿到身份标识与能力清单。"""
    token = login(client, 'auditor', 'audit123')
    me = client.get('/api/v1/auth/me', headers=auth_header(token)).get_json()
    assert me['code'] == 0, me
    assert me['data']['role'] == 'auditor'
    assert me['data']['role_label'] == '内容审核员'
    assert me['data']['is_staff'] is True
    assert me['data']['is_admin'] is False
    assert 'post.audit' in me['data']['capabilities']
