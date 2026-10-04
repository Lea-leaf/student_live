# -*- coding: utf-8 -*-
"""管理端包。

管理端接口统一前缀 `/api/v1/admin`，与用户端业务模块完全分离，
便于后续独立部署或做权限网关。

子模块：
    dashboard  管理员首页统计（含媒体存储用量）
    users      用户管理（列表/详情/封禁/重置密码/角色/彻底删除）
    posts      内容管理（全模块帖子/审核/删除/置顶）
    comments   评论管理（列表/删除）
    modules    模块管理（启停/排序/配置）
    logs       日志管理（操作日志/登录日志）
    trash      回收站（软删除帖子/彻底删除时清理磁盘文件）
    reports    举报处理
    configs    系统配置
"""

from . import (comments, configs, dashboard, handover, logs, modules, posts,
               reports, trash, users)

#: 管理端蓝图注册表。
#: 顺序有讲究：posts 蓝图里定义了 /posts/<post_id> 这类动态段路由，
#: 若它排在 trash 前面，/admin/trash/<id> 会被 /admin/posts/<id> 的规则优先匹配，
#: 因此把路径更「具体」的蓝图排在前面（Flask 按注册顺序匹配）。
ADMIN_BLUEPRINTS = [
    dashboard.bp,
    comments.bp,
    modules.bp,
    trash.bp,
    reports.bp,
    configs.bp,
    logs.bp,
    handover.bp,      # /admin/handover/*（固定路径，不会被 users 的动态段吃掉）
    users.bp,
    posts.bp,
]


def register_admin_blueprints(app):
    """注册管理端蓝图（API 前缀 + /admin + 蓝图自身前缀）。"""
    prefix = app.config.get('API_PREFIX', '/api/v1')
    for blueprint in ADMIN_BLUEPRINTS:
        full_prefix = f'{prefix}/admin{blueprint.url_prefix or ""}'
        app.register_blueprint(blueprint, url_prefix=full_prefix)
        app.logger.debug('注册管理端蓝图：%s -> %s', blueprint.name, full_prefix)
    return [bp.name for bp in ADMIN_BLUEPRINTS]


__all__ = ['register_admin_blueprints', 'ADMIN_BLUEPRINTS']
