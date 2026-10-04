# -*- coding: utf-8 -*-
"""管理端 - 模块管理。

需求：模块可启用 / 禁用 / 排序 / 配置，且「其他」模块可由后台新增。

实现关键：模块不是代码，而是 `modules` 表里的数据行；
帖子通过 `posts.type = modules.code` 关联，因此新增模块无需改表、无需改代码，
前端导航会通过 `GET /api/v1/common/modules` 自动拿到启用中的模块。
"""

from flask import Blueprint

from ..extensions import db
from ..models import Module, Post
from ..utils.auth import admin_required, current_user
from ..utils.constants import CAP_MODULE_MANAGE
from ..utils.logger import write_operation_log
from ..utils.response import error, success
from ..utils.validators import (
    ValidationError,
    as_error,
    clean_text,
    get_bool,
    get_int,
    get_json,
)

bp = Blueprint('admin_modules', __name__, url_prefix='/modules')


def _get_module_or_404(module_id):
    module = Module.query.get(module_id)
    if module is None:
        raise ValidationError('模块不存在')
    return module


@bp.get('')
@admin_required(capability=CAP_MODULE_MANAGE)
def list_modules():
    """全部模块（含禁用），附带各模块帖子数。"""
    modules = Module.query.order_by(Module.sort_order.asc(), Module.id.asc()).all()
    counts = {
        code: count for code, count in
        db.session.query(Post.type, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(False))
        .group_by(Post.type).all()
    }
    pending = {
        code: count for code, count in
        db.session.query(Post.type, db.func.count(Post.id))
        .filter(Post.is_deleted.is_(False), Post.audit_status == 'pending')
        .group_by(Post.type).all()
    }
    data = []
    for module in modules:
        item = module.to_dict()
        item['post_count'] = counts.get(module.code, 0)
        item['pending_count'] = pending.get(module.code, 0)
        data.append(item)
    return success({'list': data, 'total': len(data)})


@bp.post('')
@admin_required(capability=CAP_MODULE_MANAGE)
def create_module():
    """新增模块（对应需求「其他（后台可新增）」）。

    请求体：
        {
            "code": "other",              # 必填，唯一，作为 posts.type
            "name": "其他",
            "icon": "MoreFilled",
            "description": "其他生活互助信息",
            "sort_order": 50,
            "enabled": true,
            "config": {"audit": true}     # 可选，模块级配置
        }
    """
    import json
    import re

    try:
        payload = get_json()
        code = clean_text(payload.get('code'), 64, '模块标识', required=True)
        if not re.match(r'^[a-z][a-z0-9_]{1,63}$', code):
            raise ValidationError('模块标识只能是小写字母、数字和下划线，且以字母开头')
        if Module.query.filter_by(code=code).first():
            raise ValidationError('该模块标识已存在')

        config = payload.get('config')
        module = Module(
            code=code,
            name=clean_text(payload.get('name'), 64, '模块名称', required=True),
            icon=clean_text(payload.get('icon'), 64, '图标') or 'Grid',
            description=clean_text(payload.get('description'), 255, '模块简介'),
            sort_order=get_int('sort_order', 100),
            enabled=get_bool('enabled', True) if 'enabled' in payload else True,
            is_system=False,
            config=json.dumps(config, ensure_ascii=False) if isinstance(config, (dict, list)) else config,
        )
        db.session.add(module)
        db.session.commit()
        write_operation_log('create_module', module='modules', target_type='module',
                            target_id=module.id, detail={'code': code})
        return success(module.to_dict(), msg='模块已创建，启用后前端即可看到')
    except ValidationError as exc:
        return as_error(exc)


@bp.put('/<int:module_id>')
@admin_required(capability=CAP_MODULE_MANAGE)
def update_module(module_id):
    """修改模块名称 / 图标 / 简介 / 排序 / 配置 / 允许角色。"""
    import json

    try:
        module = _get_module_or_404(module_id)
        payload = get_json()
        if 'name' in payload:
            module.name = clean_text(payload.get('name'), 64, '模块名称', required=True)
        if 'icon' in payload:
            module.icon = clean_text(payload.get('icon'), 64, '图标')
        if 'description' in payload:
            module.description = clean_text(payload.get('description'), 255, '模块简介')
        if 'sort_order' in payload:
            module.sort_order = get_int('sort_order', module.sort_order)
        if 'allow_roles' in payload:
            module.allow_roles = clean_text(payload.get('allow_roles'), 255, '允许角色')
        if 'config' in payload:
            config = payload.get('config')
            module.config = json.dumps(config, ensure_ascii=False) if isinstance(config, (dict, list)) else config
        db.session.commit()
        write_operation_log('update_module', module='modules', target_type='module',
                            target_id=module.id, detail=payload)
        return success(module.to_dict(), msg='模块已更新')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/<int:module_id>/toggle')
@admin_required(capability=CAP_MODULE_MANAGE)
def toggle_module(module_id):
    """启用 / 禁用模块。禁用后前端导航不再展示，但历史帖子保留。"""
    try:
        module = _get_module_or_404(module_id)
        payload = get_json(required=False)
        if 'enabled' in payload:
            module.enabled = bool(payload.get('enabled'))
        else:
            module.enabled = not module.enabled
        db.session.commit()
        write_operation_log('toggle_module', module='modules', target_type='module',
                            target_id=module.id, detail={'enabled': module.enabled})
        return success(module.to_dict(), msg='模块已启用' if module.enabled else '模块已禁用')
    except ValidationError as exc:
        return as_error(exc)


@bp.post('/reorder')
@admin_required(capability=CAP_MODULE_MANAGE)
def reorder_modules():
    """批量排序：{"items": [{"id": 1, "sort_order": 10}, ...]}"""
    try:
        payload = get_json()
        items = payload.get('items') or []
        if not isinstance(items, list) or not items:
            raise ValidationError('items 不能为空')
        updated = 0
        for item in items:
            module = Module.query.get(item.get('id'))
            if module is None:
                continue
            module.sort_order = int(item.get('sort_order', module.sort_order))
            updated += 1
        db.session.commit()
        write_operation_log('reorder_modules', module='modules', detail={'updated': updated})
        return success({'updated': updated}, msg='排序已保存')
    except (ValidationError, TypeError, ValueError) as exc:
        return as_error(exc)


@bp.delete('/<int:module_id>')
@admin_required(capability=CAP_MODULE_MANAGE)
def delete_module(module_id):
    """删除模块。

    约束：内置模块不可删；模块下仍有帖子时不可删（避免孤儿数据）。
    """
    try:
        module = _get_module_or_404(module_id)
        if module.is_system:
            return error('系统内置模块不允许删除，可将其禁用')
        post_count = Post.query.filter_by(type=module.code, is_deleted=False).count()
        if post_count:
            return error(f'该模块下还有 {post_count} 条帖子，请先迁移或清理后再删除')
        db.session.delete(module)
        db.session.commit()
        write_operation_log('delete_module', module='modules', target_type='module',
                            target_id=module_id, detail={'code': module.code})
        return success(msg='模块已删除')
    except ValidationError as exc:
        return as_error(exc)


__all__ = ['bp']
