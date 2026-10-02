# -*- coding: utf-8 -*-
"""图形验证码服务。

需求待定项：注册验证码形式 → 默认「图形验证码占位」。
实现为「服务端生成文本 + SVG 图形」，零第三方依赖（不装 Pillow 也能跑）：

    GET  /api/v1/auth/captcha   → {captcha_id, svg, expires_in}

扩展点：想换成短信/邮箱验证码，只需保留 `verify()` 接口不变，
       把 `issue()` 换成「随机码 + 短信网关调用」即可。
"""

import base64
import random
import threading
import time
import uuid

#: 验证码字符集（去掉了 0/O/1/I 等易混淆字符）
CHARS = 'ABCDEFGHJKLMNPQRSTUVWXY3456789'
TTL_SECONDS = 300          # 5 分钟有效
MAX_ITEMS = 2000           # 内存中最多保留的验证码数量，防止无限增长

_STORE = {}
_LOCK = threading.Lock()


def _gc_locked():
    """清理过期项（需在持锁状态下调用）。"""
    now = time.time()
    expired = [k for k, v in _STORE.items() if v['expire_at'] < now]
    for key in expired:
        _STORE.pop(key, None)
    # 仍然过多则按过期时间淘汰最早的
    if len(_STORE) > MAX_ITEMS:
        for key, _ in sorted(_STORE.items(), key=lambda kv: kv[1]['expire_at'])[: len(_STORE) - MAX_ITEMS]:
            _STORE.pop(key, None)


def issue(length=4):
    """生成一个新验证码，返回 (captcha_id, code)。"""
    code = ''.join(random.choice(CHARS) for _ in range(length))
    captcha_id = uuid.uuid4().hex
    with _LOCK:
        _gc_locked()
        _STORE[captcha_id] = {'code': code, 'expire_at': time.time() + TTL_SECONDS}
    return captcha_id, code


def verify(captcha_id, code, consume=True):
    """校验验证码。校验成功后默认立即失效（一次性）。"""
    if not captcha_id or not code:
        return False
    with _LOCK:
        item = _STORE.get(captcha_id)
        if not item:
            return False
        if item['expire_at'] < time.time():
            _STORE.pop(captcha_id, None)
            return False
        ok = str(code).strip().upper() == item['code']
        if ok and consume:
            _STORE.pop(captcha_id, None)
    return ok


def render_svg(code, width=120, height=40):
    """把验证码渲染成 SVG（带简单干扰线，够毕设用）。"""
    rnd = random.Random(code)
    chars = []
    char_width = width // max(len(code), 1)
    for index, char in enumerate(code):
        x = char_width * index + char_width / 2
        y = height / 2 + rnd.randint(-6, 6)
        rotate = rnd.randint(-28, 28)
        color = '#%02x%02x%02x' % (rnd.randint(20, 120), rnd.randint(20, 120), rnd.randint(20, 120))
        chars.append(
            f'<text x="{x:.0f}" y="{y:.0f}" font-size="24" font-family="Arial,Helvetica,sans-serif" '
            f'font-weight="bold" fill="{color}" text-anchor="middle" '
            f'transform="rotate({rotate} {x:.0f} {y:.0f})">{char}</text>'
        )
    lines = []
    for _ in range(4):
        lines.append(
            '<path d="M{} {} L{} {}" stroke="#{:02x}{:02x}{:02x}" stroke-width="1" opacity="0.6"/>'.format(
                rnd.randint(0, width), rnd.randint(0, height),
                rnd.randint(0, width), rnd.randint(0, height),
                rnd.randint(120, 200), rnd.randint(120, 200), rnd.randint(120, 200),
            )
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#f5f7fa"/>'
        + ''.join(lines) + ''.join(chars) + '</svg>'
    )
    return svg


def issue_svg():
    """生成验证码并返回前端需要的完整结构。"""
    from flask import current_app

    captcha_id, code = issue()
    svg = render_svg(code)
    debug_code = None
    # 仅在调试模式下回传明文验证码，方便前端联调；生产环境恒为 None
    try:
        if current_app.config.get('CAPTCHA_DEBUG', False):
            debug_code = code
    except RuntimeError:
        pass
    return {
        'captcha_id': captcha_id,
        'svg': svg,
        # data URI 方便前端直接放进 <img src>
        'image': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii'),
        'expires_in': TTL_SECONDS,
        'debug_code': debug_code,
    }


__all__ = ['issue', 'verify', 'render_svg', 'issue_svg']
