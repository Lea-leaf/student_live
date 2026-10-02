# -*- coding: utf-8 -*-
"""参数校验与清洗工具。

统一从 JSON / 表单 / 查询串里取值，减少视图里的重复判断；
所有清洗都是「先校验、再入库」，输出统一经过 XSS 处理。
"""

import html
import re

from .response import CODE_PARAM_ERROR, error

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
RE_STUDENT_ID = re.compile(r'^[A-Za-z0-9]{4,20}$')
RE_USERNAME = re.compile(r'^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$')
RE_PHONE = re.compile(r'^1[3-9]\d{9}$')
RE_EMAIL = re.compile(r'^[\w.+-]+@[\w-]+\.[\w.-]+$')
#: 联系方式的宽松校验：手机号、QQ、微信号、邮箱、纯文本
RE_CONTACT = re.compile(r'^[\w\-.@+ :：\u4e00-\u9fa5]{2,64}$')
RE_DANGEROUS = re.compile(
    r'(<\s*script|<\s*/\s*script|<\s*iframe|<\s*object|<\s*embed|javascript\s*:|on(error|load|click|mouseover)\s*=)',
    re.IGNORECASE,
)


class ValidationError(ValueError):
    """参数校验失败。携带错误码，便于视图直接转成统一响应。"""

    def __init__(self, message, code=CODE_PARAM_ERROR):
        super().__init__(message)
        self.message = message
        self.code = code


def as_error(exc):
    """把 ValidationError 转成统一响应。"""
    if isinstance(exc, ValidationError):
        return error(exc.message, exc.code)
    return error(str(exc), CODE_PARAM_ERROR)


# ---------------------------------------------------------------------------
# 取值
# ---------------------------------------------------------------------------
def get_json(required=True):
    """取请求 JSON 体。"""
    from flask import request

    data = request.get_json(silent=True)
    if data is None:
        if required:
            raise ValidationError('请求体必须是合法的 JSON')
        return {}
    if not isinstance(data, dict):
        raise ValidationError('请求体必须是 JSON 对象')
    return data


def get_param(name, source=None, default=None, required=False, strip=True):
    """从 JSON / 表单 / 查询串取一个参数。"""
    from flask import request

    value = None
    if source == 'json':
        value = get_json(required=False).get(name)
    elif source == 'form':
        value = request.form.get(name)
    elif source == 'args':
        value = request.args.get(name)
    else:
        payload = get_json(required=False)
        if name in payload:
            value = payload.get(name)
        elif name in request.form:
            value = request.form.get(name)
        elif name in request.args:
            value = request.args.get(name)

    if value is None:
        value = default
    if isinstance(value, str) and strip:
        value = value.strip()
    if required and (value is None or value == ''):
        raise ValidationError(f'缺少必填参数：{name}')
    return value


def get_int(name, default=0, minimum=None, maximum=None, source=None):
    value = get_param(name, source=source, default=default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'参数 {name} 必须是整数') from None
    if minimum is not None and value < minimum:
        raise ValidationError(f'参数 {name} 不能小于 {minimum}')
    if maximum is not None and value > maximum:
        raise ValidationError(f'参数 {name} 不能大于 {maximum}')
    return value


def get_bool(name, default=False, source=None):
    value = get_param(name, source=source, default=None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def get_list(name, source=None, default=None):
    """取数组参数（JSON 里为 list；表单/查询串里支持逗号分隔）。"""
    value = get_param(name, source=source, default=None)
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [item.strip() for item in str(value).split(',') if item.strip()]


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def clean_text(value, max_length=None, field='内容', required=False, allow_empty=True):
    """清洗文本：去 HTML 标签风险 + 长度校验。"""
    if value is None:
        value = ''
    value = str(value).strip()
    if required and not value:
        raise ValidationError(f'{field}不能为空')
    if not value and not allow_empty:
        raise ValidationError(f'{field}不能为空')
    if RE_DANGEROUS.search(value):
        raise ValidationError(f'{field}包含不允许的内容')
    if max_length and len(value) > max_length:
        raise ValidationError(f'{field}长度不能超过 {max_length} 个字符')
    return value


def clean_html(value, max_length=None):
    """转义 HTML，用于最终落库的富文本字段。"""
    text = clean_text(value, max_length=max_length)
    return html.escape(text, quote=False)


def validate_phone(value):
    if value and not RE_PHONE.match(str(value)):
        raise ValidationError('手机号格式不正确')
    return value


def validate_email(value):
    if value and not RE_EMAIL.match(str(value)):
        raise ValidationError('邮箱格式不正确')
    return value


def validate_student_id(value):
    value = clean_text(value, 20, '学号', required=True)
    if not RE_STUDENT_ID.match(value):
        raise ValidationError('学号只能是 4-20 位字母或数字')
    return value


def validate_username(value):
    value = clean_text(value, 20, '用户名', required=True)
    if not RE_USERNAME.match(value):
        raise ValidationError('用户名只能是 2-20 位中文、字母、数字或下划线')
    return value


def validate_password(value):
    value = str(value or '')
    if len(value) < 6:
        raise ValidationError('密码长度至少 6 位')
    if len(value) > 64:
        raise ValidationError('密码长度不能超过 64 位')
    return value


def validate_contact(value):
    """联系方式：必填且公开可见，做宽松格式校验。"""
    value = clean_text(value, 64, '联系方式', required=True)
    if not RE_CONTACT.match(value):
        raise ValidationError('联系方式格式不正确（支持手机号 / QQ / 微信 / 邮箱）')
    return value


def validate_enum(value, allowed, field='状态'):
    if value not in allowed:
        raise ValidationError(f'{field}取值非法，可选：{" / ".join(allowed)}')
    return value


def parse_datetime(value, field='时间'):
    """解析前端传来的时间字符串，支持多种常见格式。"""
    from datetime import datetime

    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace('T', ' ')
    if text.endswith('Z'):
        text = text[:-1]
    formats = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d %H:%M', '%Y/%m/%d')
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValidationError(f'{field}格式不正确，请使用 YYYY-MM-DD HH:mm:ss')


def parse_int_list(values, field='ID'):
    result = []
    for item in values or []:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise ValidationError(f'{field}必须是整数列表') from None
    return result


__all__ = [
    'ValidationError',
    'as_error',
    'get_json',
    'get_param',
    'get_int',
    'get_bool',
    'get_list',
    'clean_text',
    'clean_html',
    'validate_phone',
    'validate_email',
    'validate_student_id',
    'validate_username',
    'validate_password',
    'validate_contact',
    'validate_enum',
    'parse_datetime',
    'parse_int_list',
]
