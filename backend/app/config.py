# -*- coding: utf-8 -*-
"""应用配置。

三级配置：
    BaseConfig       公共默认值
    DevelopmentConfig 本地开发（SQLite）
    ProductionConfig  部署（MySQL，通过环境变量注入）

约定：所有可调参数都能用环境变量覆盖，避免写死；
      数据库地址、密钥等敏感项一律走 .env，不进 Git。
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

# 读取 backend/.env（若存在）
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(BASE_DIR, '.env'))


def _bool(key, default=False):
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _int(key, default):
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


class BaseConfig:
    """公共配置。"""

    # ---- 基础 ----
    APP_NAME = os.getenv('APP_NAME', '校园生活平台')
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
    DEBUG = False
    TESTING = False
    JSON_AS_ASCII = False  # Flask 3 已移除该配置，保留常量供旧代码兼容
    JSON_SORT_KEYS = False

    # ---- 接口 ----
    API_PREFIX = os.getenv('API_PREFIX', '/api/v1')

    # ---- 数据库 ----
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', '')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,   # 断线自动重连，MySQL 部署时很有用
        'pool_recycle': 3600,
    }

    # ---- JWT ----
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=_int('JWT_EXPIRE_HOURS', 24))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int('JWT_REFRESH_EXPIRE_DAYS', 7))
    JWT_ISSUER = os.getenv('JWT_ISSUER', 'school-life-platform')

    # ---- CORS ----
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
    CORS_SUPPORTS_CREDENTIALS = True

    # ---- 上传 ----
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))
    MAX_CONTENT_LENGTH = _int('MAX_CONTENT_MB', 50) * 1024 * 1024  # 需求默认 50MB
    ALLOWED_EXTENSIONS = set(
        os.getenv('ALLOWED_EXTENSIONS', 'jpg,jpeg,png,gif,webp,mp4,mov').replace(' ', '').split(',')
    )
    IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
    VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'webm', 'mkv'}

    # ---- 分页 ----
    DEFAULT_PAGE_SIZE = _int('DEFAULT_PAGE_SIZE', 10)
    MAX_PAGE_SIZE = _int('MAX_PAGE_SIZE', 100)

    # ---- 日志 ----
    LOG_DIR = os.getenv('LOG_DIR', os.path.join(BASE_DIR, 'app', 'logs'))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_MAX_BYTES = _int('LOG_MAX_BYTES', 5 * 1024 * 1024)
    LOG_BACKUP_COUNT = _int('LOG_BACKUP_COUNT', 5)

    # ---- 业务开关（可被 system_configs 表覆盖，表优先） ----
    POST_AUDIT_ENABLED = _bool('POST_AUDIT_ENABLED', True)
    REGISTER_CAPTCHA_ENABLED = _bool('REGISTER_CAPTCHA_ENABLED', True)
    #: 是否在验证码接口里回传明文（仅开发调试用，生产必须为 False）
    CAPTCHA_DEBUG = _bool('CAPTCHA_DEBUG', False)
    RECYCLE_RETENTION_COUNT = _int('RECYCLE_RETENTION_COUNT', 10)
    GUEST_CAN_LIST = _bool('GUEST_CAN_LIST', True)
    GUEST_CAN_DETAIL = _bool('GUEST_CAN_DETAIL', False)
    SECURITY_NOTICE_ENABLED = _bool('SECURITY_NOTICE_ENABLED', True)


class DevelopmentConfig(BaseConfig):
    """本地开发：默认 SQLite。"""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or 'sqlite:///' + os.path.join(BASE_DIR, 'school_life.db')
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    #: 开发环境回传验证码明文，方便前端联调；生产环境为 False
    CAPTCHA_DEBUG = _bool('CAPTCHA_DEBUG', True)


class TestingConfig(BaseConfig):
    """单元测试：内存库，每次跑都是干净的。"""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    #: 测试里需要读到明文验证码，否则无法走通注册流程
    CAPTCHA_DEBUG = True


class ProductionConfig(BaseConfig):
    """部署：MySQL + PyMySQL 驱动。

    示例 DATABASE_URL:
        mysql+pymysql://user:password@127.0.0.1:3306/school_life?charset=utf8mb4
    """

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or (
        'mysql+pymysql://root:root@127.0.0.1:3306/school_life?charset=utf8mb4'
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20,
    }


#: 名称 → 配置类，供 create_app(config_name) 使用
config_map = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
