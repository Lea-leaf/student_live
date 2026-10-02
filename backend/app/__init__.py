# -*- coding: utf-8 -*-
"""应用工厂。

职责：
1. 加载配置（开发 / 测试 / 生产）；
2. 初始化扩展（SQLAlchemy / Migrate / CORS）；
3. 注册蓝图（业务模块 + 管理端 + 文件访问）；
4. 注册全局错误处理（保证任何异常都返回统一 JSON 结构）；
5. 注册 CLI 命令（init-db / seed / create-admin）。

启动方式：
    python run.py                     # 开发
    flask --app run:app run           # 或用 flask 命令
"""

import os
import traceback

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .config import config_map
from .extensions import cors, db, migrate


def create_app(config_name=None):
    """创建 Flask 应用。"""
    config_name = config_name or os.getenv('FLASK_CONFIG', 'development')
    app = Flask(__name__, static_folder=None)

    # ---- 配置 ----
    config_class = config_map.get(config_name, config_map['default'])
    app.config.from_object(config_class)
    app.config['CONFIG_NAME'] = config_name

    # 确保上传目录、日志目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)

    # ---- 日志 ----
    from .utils.logger import setup_logging

    setup_logging(app)

    # ---- 扩展 ----
    _init_extensions(app)

    # ---- 蓝图 ----
    _register_blueprints(app)

    # ---- 错误处理 ----
    _register_error_handlers(app)

    # ---- CLI ----
    _register_commands(app)

    app.logger.info('%s 启动完成（配置：%s）', app.config['APP_NAME'], config_name)
    return app


# ---------------------------------------------------------------------------
# 内部：扩展初始化
# ---------------------------------------------------------------------------
def _init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)

    origins = app.config.get('CORS_ORIGINS', '*')
    if origins != '*':
        origins = [item.strip() for item in str(origins).split(',') if item.strip()]
    cors.init_app(
        app,
        resources={r'/api/*': {'origins': origins}},
        supports_credentials=app.config.get('CORS_SUPPORTS_CREDENTIALS', True),
        allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
        expose_headers=['Content-Disposition'],
    )

    # 让 SQLite 也支持外键约束（MySQL 天然支持）
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, 'connect')
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        if dbapi_connection.__class__.__module__.startswith('sqlite3'):
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()


# ---------------------------------------------------------------------------
# 内部：蓝图注册
# ---------------------------------------------------------------------------
def _register_blueprints(app):
    from .admin import register_admin_blueprints
    from .modules import register_module_blueprints

    register_module_blueprints(app)
    register_admin_blueprints(app)

    # 文件访问（上传的图片/视频）
    from .utils.uploads import send_upload_file

    prefix = app.config.get('API_PREFIX', '/api/v1')

    @app.get(f'{prefix}/files/<path:rel_path>')
    def serve_file(rel_path):  # noqa: ANN001
        """访问上传的文件。"""
        return send_upload_file(rel_path)

    @app.get('/')
    def index():  # noqa: ANN001
        """根路径：给出接口信息，方便快速自检。"""
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': {
                'app': app.config['APP_NAME'],
                'api_prefix': prefix,
                'docs': 'docs/API.md',
                'health': f'{prefix}/common/health',
                'version': '1.0.0',
            },
        })


# ---------------------------------------------------------------------------
# 内部：错误处理
# ---------------------------------------------------------------------------
def _register_error_handlers(app):
    from .utils.response import (
        CODE_METHOD_NOT_ALLOWED,
        CODE_NOT_FOUND,
        CODE_PARAM_ERROR,
        CODE_SERVER_ERROR,
        CODE_UPLOAD_TOO_LARGE,
        error,
    )

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):  # noqa: ANN001
        """把 HTTP 异常也统一成 {code,msg,data}。"""
        code = CODE_PARAM_ERROR
        if exc.code == 404:
            code = CODE_NOT_FOUND
        elif exc.code == 405:
            code = CODE_METHOD_NOT_ALLOWED
        elif exc.code in (401, 403):
            code = exc.code * 10 + 1
        return error(exc.description or exc.name, code, http_status=exc.code or 400)

    @app.errorhandler(413)
    def handle_too_large(exc):  # noqa: ANN001
        """上传体积超限。"""
        limit_mb = app.config.get('MAX_CONTENT_LENGTH', 0) // 1024 // 1024
        return error(f'上传文件过大（上限 {limit_mb}MB）', CODE_UPLOAD_TOO_LARGE, http_status=413)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):  # noqa: ANN001
        """兜底异常：记录堆栈 + 回滚事务 + 返回统一结构。"""
        db.session.rollback()
        app.logger.error('未处理异常：%s\n%s', exc, traceback.format_exc())
        detail = str(exc) if app.config.get('DEBUG') else None
        return error(
            f'服务器内部错误：{detail}' if detail else '服务器内部错误，请稍后重试',
            CODE_SERVER_ERROR,
            http_status=500,
        )

    @app.after_request
    def add_common_headers(response):  # noqa: ANN001
        """统一响应头：便于前端排查请求链路。"""
        response.headers['X-App'] = 'school-life-platform'
        if request.method == 'OPTIONS':
            response.headers['Access-Control-Max-Age'] = '86400'
        return response


# ---------------------------------------------------------------------------
# 内部：CLI 命令
# ---------------------------------------------------------------------------
def _register_commands(app):
    import click

    @app.cli.command('init-db')
    @click.option('--drop', is_flag=True, help='先删除所有表（危险）')
    def init_db(drop):
        """创建全部数据表 + 写入默认模块与配置。"""
        from .models import Module, default_modules
        from .utils.config_service import init_default_configs

        if drop:
            db.drop_all()
            click.echo('已删除全部数据表')
        db.create_all()
        click.echo('数据表创建完成')

        created = 0
        for item in default_modules():
            if Module.query.filter_by(code=item['code']).first():
                continue
            db.session.add(Module(**item))
            created += 1
        db.session.commit()
        click.echo(f'模块初始化完成（新增 {created} 个）')

        count = init_default_configs()
        click.echo(f'系统配置初始化完成（新增 {count} 项）')

    @app.cli.command('create-admin')
    @click.option('--student-id', prompt='学号', help='管理员学号')
    @click.option('--password', prompt='密码', hide_input=True, confirmation_prompt=True, help='管理员密码')
    @click.option('--nickname', default='系统管理员', help='昵称')
    def create_admin(student_id, password, nickname):
        """创建（或升级）一个管理员账号。"""
        from .models import User
        from .utils.constants import ROLE_ADMIN, STATUS_ACTIVE

        user = User.query.filter_by(student_id=student_id).first()
        if user:
            user.role = ROLE_ADMIN
            user.status = STATUS_ACTIVE
            user.set_password(password)
            click.echo(f'已把 {student_id} 升级为管理员')
        else:
            user = User(student_id=student_id, username=student_id, nickname=nickname,
                        role=ROLE_ADMIN, status=STATUS_ACTIVE)
            user.set_password(password)
            db.session.add(user)
            click.echo(f'已创建管理员 {student_id}')
        db.session.commit()

    @app.cli.command('seed')
    @click.option('--reset', is_flag=True, help='清空业务数据后重新生成')
    def seed(reset):
        """生成演示数据（学生、管理员、帖子）。"""
        from .utils.seed import run_seed

        run_seed(reset=reset)


__all__ = ['create_app']
