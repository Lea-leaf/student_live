# -*- coding: utf-8 -*-
"""认证模块测试：注册、登录、权限、封禁、密码。"""

from tests.conftest import auth_header, login


def test_captcha_and_register(client):
    """验证码 → 注册 → 自动登录。"""
    captcha = client.get('/api/v1/auth/captcha').get_json()
    assert captcha['code'] == 0
    captcha_id = captcha['data']['captcha_id']
    code = captcha['data']['debug_code']
    assert captcha_id and code, '开发环境应回传明文验证码便于测试'

    response = client.post('/api/v1/auth/register', json={
        'student_id': '20219999',
        'password': '123456',
        'confirm_password': '123456',
        'nickname': '新同学',
        'captcha_id': captcha_id,
        'captcha': code,
    })
    body = response.get_json()
    assert body['code'] == 0, body
    assert body['data']['access_token']
    assert body['data']['user']['student_id'] == '20219999'
    assert 'password_hash' not in body['data']['user']


def test_register_wrong_captcha(client):
    captcha = client.get('/api/v1/auth/captcha').get_json()['data']
    response = client.post('/api/v1/auth/register', json={
        'student_id': '20219998',
        'password': '123456',
        'captcha_id': captcha['captcha_id'],
        'captcha': 'XXXX',
    })
    assert response.get_json()['code'] == 2005


def test_register_duplicate_student_id(client, student):
    captcha = client.get('/api/v1/auth/captcha').get_json()['data']
    response = client.post('/api/v1/auth/register', json={
        'student_id': '20210001',
        'password': '123456',
        'captcha_id': captcha['captcha_id'],
        'captcha': captcha['debug_code'],
    })
    assert response.get_json()['code'] == 3001


def test_login_success_and_me(client, student_token):
    me = client.get('/api/v1/auth/me', headers=auth_header(student_token)).get_json()
    assert me['code'] == 0
    assert me['data']['student_id'] == '20210001'
    assert me['data']['is_admin'] is False


def test_login_wrong_password(client, student):
    response = client.post('/api/v1/auth/login', json={'student_id': '20210001', 'password': 'bad'})
    assert response.get_json()['code'] == 2006


def test_me_without_token(client):
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 401
    assert response.get_json()['code'] == 2001


def test_banned_user_cannot_login(client, app, student):
    """封禁后无法登录，且已签发的 token 也失效。"""
    from app.extensions import db
    from app.models import User

    token = login(client, '20210001', '123456')
    with app.app_context():
        user = User.query.get(student)
        user.ban(reason='测试封禁')
        db.session.commit()

    response = client.post('/api/v1/auth/login', json={'student_id': '20210001', 'password': '123456'})
    assert response.get_json()['code'] == 2004

    me = client.get('/api/v1/auth/me', headers=auth_header(token))
    assert me.get_json()['code'] == 2004


def test_change_password(client, student_token):
    response = client.put('/api/v1/auth/password', headers=auth_header(student_token), json={
        'old_password': '123456',
        'new_password': 'newpass123',
    })
    assert response.get_json()['code'] == 0
    # 新密码可登录
    assert login(client, '20210001', 'newpass123')


def test_change_password_wrong_old(client, student_token):
    response = client.put('/api/v1/auth/password', headers=auth_header(student_token), json={
        'old_password': 'wrong',
        'new_password': 'newpass123',
    })
    assert response.get_json()['code'] == 2006


def test_security_notice(client):
    body = client.get('/api/v1/auth/security-notice').get_json()
    assert body['code'] == 0
    assert body['data']['enabled'] is True
    assert '敏感' in body['data']['text']
