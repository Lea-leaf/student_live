# -*- coding: utf-8 -*-
"""统一响应封装。

所有接口一律返回：
    {
        "code": 0,          # 0 = 成功，非 0 = 业务错误码
        "msg": "success",
        "data": {}          # 业务数据，可为 dict / list / None
        }

HTTP 状态码策略：业务错误默认仍返回 200，由前端按 `code` 判断，
这样前端拦截器逻辑最简单；同时也支持携带真实 HTTP 状态码（见 error 处理）。
"""

from flask import jsonify

# ---------------------------------------------------------------------------
# 业务错误码（后续模块按段位扩展，避免冲突）
#   0          成功
#   1xxx       通用 / 参数
#   2xxx       认证与权限
#   3xxx       用户
#   4xxx       帖子（各模块共用）
#   5xxx       互动（评论/私信/收藏/举报/通知）
#   6xxx       文件上传
#   9xxx       系统
# ---------------------------------------------------------------------------
CODE_OK = 0
CODE_FAIL = 1
CODE_PARAM_ERROR = 1001
CODE_NOT_FOUND = 1002
CODE_METHOD_NOT_ALLOWED = 1003
CODE_TOO_MANY_REQUESTS = 1004

CODE_UNAUTHORIZED = 2001          # 未登录 / token 无效
CODE_TOKEN_EXPIRED = 2002         # token 过期
CODE_FORBIDDEN = 2003             # 已登录但无权限
CODE_ACCOUNT_BANNED = 2004        # 账号被封禁
CODE_CAPTCHA_ERROR = 2005         # 验证码错误
CODE_PASSWORD_ERROR = 2006        # 账号或密码错误

CODE_USER_EXISTS = 3001           # 学号已注册
CODE_USER_NOT_FOUND = 3002

CODE_POST_NOT_FOUND = 4001
CODE_POST_CLOSED = 4002           # 该状态不允许查看详情
CODE_POST_AUDIT_DONE = 4003       # 已审核，不能重复审核
CODE_POST_STATUS_INVALID = 4004   # 非法状态流转

CODE_REPORT_HANDLED = 5001
CODE_NOTIFY_NOT_FOUND = 5002

CODE_UPLOAD_TYPE_ERROR = 6001
CODE_UPLOAD_TOO_LARGE = 6002
CODE_UPLOAD_FAILED = 6003

CODE_SERVER_ERROR = 9001
CODE_DB_ERROR = 9002

#: 错误码 → 默认中文提示
CODE_MESSAGES = {
    CODE_OK: 'success',
    CODE_FAIL: '操作失败',
    CODE_PARAM_ERROR: '参数错误',
    CODE_NOT_FOUND: '资源不存在',
    CODE_METHOD_NOT_ALLOWED: '请求方法不被允许',
    CODE_TOO_MANY_REQUESTS: '请求过于频繁，请稍后再试',
    CODE_UNAUTHORIZED: '请先登录',
    CODE_TOKEN_EXPIRED: '登录已过期，请重新登录',
    CODE_FORBIDDEN: '没有权限执行该操作',
    CODE_ACCOUNT_BANNED: '账号已被封禁，请联系管理员',
    CODE_CAPTCHA_ERROR: '验证码错误或已过期',
    CODE_PASSWORD_ERROR: '学号或密码错误',
    CODE_USER_EXISTS: '该学号已注册',
    CODE_USER_NOT_FOUND: '用户不存在',
    CODE_POST_NOT_FOUND: '帖子不存在',
    CODE_POST_CLOSED: '该信息已结束，无法查看详情',
    CODE_POST_AUDIT_DONE: '该帖子已审核，请勿重复操作',
    CODE_POST_STATUS_INVALID: '当前状态不允许该操作',
    CODE_REPORT_HANDLED: '该举报已处理',
    CODE_NOTIFY_NOT_FOUND: '通知不存在',
    CODE_UPLOAD_TYPE_ERROR: '不支持的文件类型',
    CODE_UPLOAD_TOO_LARGE: '文件超出大小限制',
    CODE_UPLOAD_FAILED: '文件上传失败',
    CODE_SERVER_ERROR: '服务器内部错误',
    CODE_DB_ERROR: '数据库操作失败',
}


def success(data=None, msg='success', code=CODE_OK, http_status=200):
    """成功响应。"""
    return jsonify({'code': code, 'msg': msg, 'data': data if data is not None else {}}), http_status


def error(msg=None, code=CODE_FAIL, data=None, http_status=200):
    """失败响应。msg 为空时按错误码取默认中文提示。"""
    if msg is None:
        msg = CODE_MESSAGES.get(code, '操作失败')
    return jsonify({'code': code, 'msg': msg, 'data': data if data is not None else {}}), http_status


def page_data(items, total, page, size, extra=None):
    """分页数据体，配合 success() 使用。"""
    data = {
        'list': items,
        'total': total,
        'page': page,
        'size': size,
        'pages': (total + size - 1) // size if size else 0,
    }
    if extra:
        data.update(extra)
    return data


def paginated(items, total, page, size, extra=None):
    """分页响应（等价于 success(page_data(...))）。"""
    return success(page_data(items, total, page, size, extra))
