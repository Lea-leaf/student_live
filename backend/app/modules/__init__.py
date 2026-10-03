# -*- coding: utf-8 -*-
"""业务模块包。

模块化约定（新增一个功能模块的标准流程）：
    1. 在 `app/modules/<module_name>/routes.py` 中定义 `bp = Blueprint(...)`；
    2. 在 `app/models/module.py::default_modules()` 里登记模块元数据
       （code / name / icon / 排序 / 是否默认启用）；
    3. 在本文件 `MODULE_BLUEPRINTS` 中追加一行映射。

这样后台「模块管理」一启用，前端导航与新模块接口就同时可用，
不需要改动其他任何地方 —— 满足「方便后续加新功能」的要求。
"""

from . import (
    auth,
    comments,
    common,
    favorites,
    likes,
    lost_found,
    messages,
    notifications,
    reports,
)

#: 模块标识 → 蓝图。键与 `modules.code` 保持一致，便于按模块做权限与统计。
MODULE_BLUEPRINTS = {
    'auth': auth.bp,
    'common': common.bp,
    'lost_found': lost_found.bp,
    'comments': comments.bp,
    'messages': messages.bp,
    'likes': likes.bp,
    'favorites': favorites.bp,
    'reports': reports.bp,
    'notifications': notifications.bp,
}

#: 已实现完整业务的模块（其余为占位，接口返回明确的「待开放」）
IMPLEMENTED_MODULES = (
    'auth', 'common', 'lost_found', 'favorites', 'reports', 'notifications',
    'comments', 'messages', 'likes',
)


def register_module_blueprints(app):
    """把所有业务模块蓝图注册到应用。

    注意：Flask 注册蓝图时若显式传 url_prefix，会「替换」蓝图自身的 url_prefix，
    因此这里要把 API 前缀与蓝图前缀拼起来，否则 /auth、/lost_found 等段会丢失。
    """
    prefix = app.config.get('API_PREFIX', '/api/v1')
    for name, blueprint in MODULE_BLUEPRINTS.items():
        full_prefix = f'{prefix}{blueprint.url_prefix or ""}'
        app.register_blueprint(blueprint, url_prefix=full_prefix)
        app.logger.debug('注册模块蓝图：%s -> %s', name, full_prefix)
    return list(MODULE_BLUEPRINTS.keys())


__all__ = ['MODULE_BLUEPRINTS', 'IMPLEMENTED_MODULES', 'register_module_blueprints']
