# -*- coding: utf-8 -*-
"""pytest 公共夹具。

测试使用内存 SQLite（TestingConfig），每个测试函数独立建表/清表，
因此测试之间不会互相污染。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Module, User, default_modules  # noqa: E402
from app.utils.config_service import init_default_configs  # noqa: E402
from app.utils.constants import ROLE_ADMIN, ROLE_USER  # noqa: E402


@pytest.fixture()
def app():
    """测试应用：内存库 + 基础种子数据。"""
    application = create_app('testing')
    with application.app_context():
        db.create_all()
        for item in default_modules():
            db.session.add(Module(**item))
        db.session.commit()
        init_default_configs()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Flask 测试客户端。"""
    return app.test_client()


def _create_user(app, student_id, password, role=ROLE_USER, nickname=None):
    with app.app_context():
        user = User(student_id=student_id, username=student_id,
                    nickname=nickname or student_id, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture()
def student(app):
    """普通学生账号。"""
    return _create_user(app, '20210001', '123456')


@pytest.fixture()
def student2(app):
    """第二个学生账号（用于越权测试）。"""
    return _create_user(app, '20210002', '123456')


@pytest.fixture()
def admin(app):
    """管理员账号。"""
    return _create_user(app, 'admin', 'admin123', role=ROLE_ADMIN, nickname='管理员')


def login(client, student_id, password):
    """登录并返回 token。"""
    response = client.post('/api/v1/auth/login', json={'student_id': student_id, 'password': password})
    body = response.get_json()
    assert body['code'] == 0, body
    return body['data']['access_token']


def auth_header(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def student_token(client, student):
    return login(client, '20210001', '123456')


@pytest.fixture()
def student2_token(client, student2):
    return login(client, '20210002', '123456')


@pytest.fixture()
def admin_token(client, admin):
    return login(client, 'admin', 'admin123')


@pytest.fixture()
def sample_post(app, student):
    """一条已通过审核的失物招领帖子。"""
    from app.models import Post
    from app.utils.constants import AUDIT_APPROVED

    with app.app_context():
        post = Post(type='lost_found', user_id=student, title='测试丢伞',
                    content='图书馆丢的', contact='微信 test123',
                    audit_status=AUDIT_APPROVED)
        db.session.add(post)
        db.session.commit()
        return post.id
