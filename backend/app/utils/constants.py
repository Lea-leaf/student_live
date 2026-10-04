# -*- coding: utf-8 -*-
"""常量与枚举定义。

集中管理所有状态值，避免在业务代码里散落魔法字符串。
前端可通过 `GET /api/v1/common/enums` 一次性拿到全部字典。
"""

# ---------------------------------------------------------------------------
# 用户角色
#
# 【当前实际使用的三个等级】
#   user     普通用户    —— 无后台权限
#   auditor  内容审核员  —— 受限后台角色（内容处置 + 管理普通用户）
#   admin    管理员      —— 最高级，通配全部后台能力
#
# `admin` 就是最高等级（早期曾预留 `super_admin` 作为"更高一级"，已彻底移除：
# 它与 admin 从来没有任何实际差异，只会造成两套口径不一致）。
# ---------------------------------------------------------------------------
ROLE_USER = 'user'
ROLE_ADMIN = 'admin'
ROLE_AUDITOR = 'auditor'

#: 可被分配的角色（**唯一权威名单**）。
#: 调整角色接口只接受这里列出的值，前端下拉框也由它下发 ——
#: 所以「把某个角色从这里注释掉」= 该角色不可再被分配，但预留代码原样保留。
ROLES = (ROLE_USER, ROLE_ADMIN, ROLE_AUDITOR)

ROLE_LABELS = {
    ROLE_USER: '普通用户',
    ROLE_ADMIN: '管理员',
    ROLE_AUDITOR: '内容审核员',
}

# ---------------------------------------------------------------------------
# 【预留角色 · 未启用】以后需要时把名字加回上面的 ROLES 即可启用
#
# 启用步骤（三步，不需要改数据库）：
#   1. 把 ROLE_XXX 加进 ROLES 与 ROLE_LABELS 与 ADMIN_ROLES；
#   2. 在下方 ROLE_PERMISSIONS 里给它分配能力（已预置初稿）；
#   3. 前端无需改动 —— 角色下拉框与菜单都由后端下发。
#
# 三者当前都**没有任何账号**，且不在 ROLES 里，因此不可能被分配。
# ---------------------------------------------------------------------------
# ROLE_USER_ADMIN = 'user_admin'        # 用户管理员：只管用户，不碰内容
# ROLE_MODULE_ADMIN = 'module_admin'    # 模块管理员：只管模块配置
# ROLE_MODERATOR = 'moderator'          # 版主：类似审核员，另加举报处理权重

#: 预留角色的中文名（启用时合并进 ROLE_LABELS）
RESERVED_ROLE_LABELS = {
    'user_admin': '用户管理员',
    'module_admin': '模块管理员',
    'moderator': '版主',
}

#: 具备后台访问权限的角色集合（= 「能不能进后台」，不含普通用户）
ADMIN_ROLES = (ROLE_ADMIN, ROLE_AUDITOR)

#: 真正的管理员（最高级）。
#: 用途：只有管理员的帖子免审核、只有管理员能改他人正文、
#: 只有管理员不受"后台角色账号保护"约束。
TRUE_ADMIN_ROLES = (ROLE_ADMIN,)

# ---------------------------------------------------------------------------
# 后台能力（RBAC 的最小实现：角色 → 能力集合）
#
# 为什么要有这一层：`ADMIN_ROLES` 只回答"能不能进后台"，回答不了"进去能做什么"。
# 早期只有 user / admin 两级时两者等价，引入 auditor 后必须拆开，
# 否则审核员会直接拿到全部管理员权限（详见 docs/USER_FIELDS.md）。
#
# 新增角色 / 调整权限只改这张表，不需要动任何视图代码。
# ---------------------------------------------------------------------------
CAP_ALL = '*'                       # 通配：管理员持有，自动覆盖以后新增的能力

CAP_DASHBOARD_VIEW = 'dashboard.view'
CAP_POST_AUDIT = 'post.audit'       # 审核帖子（通过 / 拒绝）
CAP_POST_VIEW = 'post.view'         # 查看内容列表 / 详情
CAP_POST_MANAGE = 'post.manage'     # 删帖 / 置顶 / 改业务状态 / 编辑他人正文
CAP_COMMENT_VIEW = 'comment.view'
CAP_COMMENT_MANAGE = 'comment.manage'   # 删除评论（物理删除）
CAP_USER_VIEW = 'user.view'         # 用户列表（能搜到人即可，支撑封禁操作）
CAP_USER_DETAIL = 'user.detail'     # 用户详情 / 发帖记录 / 登录与操作日志（敏感明细）
CAP_USER_MANAGE = 'user.manage'     # 封禁 / 解封 / 重置密码 / 备注 / 建号
CAP_USER_ROLE = 'user.role'         # 调整角色（任命审核员）；管理员专有，审核员没有
CAP_ADMIN_HANDOVER = 'admin.handover'   # 管理员移交（系统只允许一个管理员）
CAP_MODULE_MANAGE = 'module.manage'
CAP_LOG_VIEW = 'log.view'
CAP_TRASH_VIEW = 'trash.view'
CAP_TRASH_MANAGE = 'trash.manage'   # 还原 / 彻底删除 / 清理
CAP_REPORT_HANDLE = 'report.handle'
CAP_CONFIG_MANAGE = 'config.manage'
CAP_MEDIA_CLEAN = 'media.clean'     # 清理磁盘孤儿文件（破坏性）

#: 角色 → 能力集合。审核员按需求「管理普通用户 + 管内容，但不碰系统结构」收窄。
ROLE_PERMISSIONS = {
    # 管理员 = 最高等级，持通配能力。
    # 用通配而不是逐项列举：以后新增能力会自动覆盖到管理员，不会漏。
    ROLE_ADMIN: {CAP_ALL},
    # 内容审核员：审核台 + 内容管理 + 评论管理 + 举报处理 + 概览 + 用户列表 + 封禁普通用户；
    # 明确不给：模块管理、系统配置、日志、回收站、媒体清理、改角色、重置密码、
    #           看用户详情 / 发帖记录（需求原文："不可以重置密码、看详情与发帖记录"）。
    ROLE_AUDITOR: {
        CAP_DASHBOARD_VIEW, CAP_POST_AUDIT, CAP_POST_VIEW, CAP_POST_MANAGE,
        CAP_COMMENT_VIEW, CAP_COMMENT_MANAGE,
        CAP_USER_VIEW, CAP_USER_MANAGE,
        CAP_REPORT_HANDLE,
    },
    ROLE_USER: set(),
    # ------------------------------------------------------------------
    # 【预留角色 · 未启用】能力初稿先放这里，启用时把它加进 ROLES / ROLE_LABELS /
    # ADMIN_ROLES 即可生效（键名与上面 RESERVED_ROLE_LABELS 对应）。
    # 注意：角色不在 ROLES 里就无法被分配，所以这几项现在是"放着不生效"。
    # ------------------------------------------------------------------
    'user_admin': {CAP_DASHBOARD_VIEW, CAP_USER_VIEW, CAP_USER_MANAGE, CAP_LOG_VIEW},
    'module_admin': {CAP_DASHBOARD_VIEW, CAP_POST_AUDIT, CAP_POST_VIEW, CAP_MODULE_MANAGE},
    'moderator': {CAP_DASHBOARD_VIEW, CAP_POST_AUDIT, CAP_POST_VIEW,
                  CAP_COMMENT_VIEW, CAP_COMMENT_MANAGE, CAP_REPORT_HANDLE},
}

#: 中文字典：能力 → 名称（下发给前端做菜单与按钮渲染）
CAPABILITY_LABELS = {
    CAP_DASHBOARD_VIEW: '查看概览',
    CAP_POST_AUDIT: '审核内容',
    CAP_POST_VIEW: '查看内容',
    CAP_POST_MANAGE: '管理内容',
    CAP_COMMENT_VIEW: '查看评论',
    CAP_COMMENT_MANAGE: '删除评论',
    CAP_USER_VIEW: '查看用户',
    CAP_USER_DETAIL: '查看用户明细',
    CAP_USER_MANAGE: '管理用户',
    CAP_USER_ROLE: '调整角色',
    CAP_ADMIN_HANDOVER: '管理员移交',
    CAP_MODULE_MANAGE: '模块管理',
    CAP_LOG_VIEW: '查看日志',
    CAP_TRASH_VIEW: '查看回收站',
    CAP_TRASH_MANAGE: '回收站管理',
    CAP_REPORT_HANDLE: '处理举报',
    CAP_CONFIG_MANAGE: '系统配置',
    CAP_MEDIA_CLEAN: '媒体清理',
}


def role_capabilities(role):
    """取某角色的能力集合（未知角色回落到空集，安全默认）。"""
    return set(ROLE_PERMISSIONS.get(role, set()))


def has_capability(role, capability):
    """判断角色是否具备某项能力。"""
    caps = ROLE_PERMISSIONS.get(role)
    if not caps:
        return False
    return CAP_ALL in caps or capability in caps


def capabilities_of(role):
    """把角色能力展开成具体清单（通配展开为全部能力，便于前端渲染）。"""
    caps = ROLE_PERMISSIONS.get(role) or set()
    if CAP_ALL in caps:
        return sorted(c for c in CAPABILITY_LABELS)
    return sorted(caps)


# ---------------------------------------------------------------------------
# 审核指派（管理员指定审核员；审核员可自助认领）
# ---------------------------------------------------------------------------
#: 认领后的自动退回时长（小时）：超时未审核自动退回公共池，避免帖子卡在某人名下
ASSIGNMENT_CLAIM_TTL_HOURS = 24

#: 审核流水动作
AUDIT_ACTION_ASSIGN = 'assign'      # 管理员指派 / 改派
AUDIT_ACTION_CLAIM = 'claim'        # 审核员自助认领
AUDIT_ACTION_RELEASE = 'release'    # 放弃认领 / 超时自动退回
AUDIT_ACTION_APPROVE = 'approve'    # 审核通过
AUDIT_ACTION_REJECT = 'reject'      # 审核拒绝
AUDIT_ACTIONS = (AUDIT_ACTION_ASSIGN, AUDIT_ACTION_CLAIM, AUDIT_ACTION_RELEASE,
                 AUDIT_ACTION_APPROVE, AUDIT_ACTION_REJECT)
AUDIT_ACTION_LABELS = {
    AUDIT_ACTION_ASSIGN: '指派',
    AUDIT_ACTION_CLAIM: '认领',
    AUDIT_ACTION_RELEASE: '退回',
    AUDIT_ACTION_APPROVE: '通过',
    AUDIT_ACTION_REJECT: '拒绝',
}
#: 指派来源
ASSIGN_SOURCE_ADMIN = 'admin'
ASSIGN_SOURCE_SELF = 'self'

STATUS_ACTIVE = 'active'
STATUS_BANNED = 'banned'
USER_STATUSES = (STATUS_ACTIVE, STATUS_BANNED)
USER_STATUS_LABELS = {STATUS_ACTIVE: '正常', STATUS_BANNED: '已封禁'}

# ---------------------------------------------------------------------------
# 帖子：审核状态 / 业务状态
# ---------------------------------------------------------------------------
AUDIT_PENDING = 'pending'
AUDIT_APPROVED = 'approved'
AUDIT_REJECTED = 'rejected'
AUDIT_STATUSES = (AUDIT_PENDING, AUDIT_APPROVED, AUDIT_REJECTED)
AUDIT_STATUS_LABELS = {AUDIT_PENDING: '待审核', AUDIT_APPROVED: '已通过', AUDIT_REJECTED: '已拒绝'}

POST_ONGOING = 'ongoing'
POST_CLAIMED = 'claimed'
POST_CLOSED = 'closed'
POST_EXPIRED = 'expired'
POST_STATUSES = (POST_ONGOING, POST_CLAIMED, POST_CLOSED, POST_EXPIRED)
POST_STATUS_LABELS = {
    POST_ONGOING: '进行中',
    POST_CLAIMED: '已认领',
    POST_EXPIRED: '已过期',
    POST_CLOSED: '已关闭',
}

#: 列表可见的状态（已关闭只在「我的发布 / 后台」可见）
POST_LIST_VISIBLE_STATUSES = (POST_ONGOING, POST_CLAIMED, POST_EXPIRED)
#: 详情可点击的状态（已认领/已过期/已关闭都不可再进详情）
POST_DETAIL_VISIBLE_STATUSES = (POST_ONGOING,)

# ---------------------------------------------------------------------------
# 模块（帖子 type）
# ---------------------------------------------------------------------------
MODULE_LOST_FOUND = 'lost_found'
MODULE_SECOND_HAND = 'second_hand'
MODULE_GROUP_BUY = 'group_buy'
MODULE_ERRAND = 'errand'
MODULE_DAILY = 'daily'
MODULE_OTHER = 'other'

#: 兜底模块：管理员可自由新增模块，未登记的自定义 type 也能工作
DEFAULT_MODULE_CODE = MODULE_LOST_FOUND

#: 模块差异化状态文案：数据库状态值不变，只在对应模块下换显示标签。
#: 每个模块的字典都要覆盖该模块可能出现的全部状态，避免漏状态时显示英文原值。
MODULE_STATUS_LABELS = {
    MODULE_SECOND_HAND: {
        POST_ONGOING: '在售中',
        POST_CLAIMED: '已售出',
        POST_EXPIRED: '已过期',
        POST_CLOSED: '已下架',
    },
    MODULE_GROUP_BUY: {
        POST_ONGOING: '招募中',
        POST_CLAIMED: '已结束',
        POST_CLOSED: '已取消',
        POST_EXPIRED: '已过期',     # 保留兜底（该模块不会主动用到）
    },
    MODULE_ERRAND: {
        POST_ONGOING: '进行中',
        POST_CLAIMED: '已完成',
        POST_CLOSED: '已取消',
        POST_EXPIRED: '已过期',
    },
    MODULE_DAILY: {
        POST_ONGOING: '正常',
        POST_CLOSED: '已关闭',
        POST_CLAIMED: '已关闭',     # 日常不使用该状态，兜底避免出现英文
        POST_EXPIRED: '已过期',
    },
}

#: 每模块允许的业务状态子集（用于表单下拉与筛选器）。
#: 未登记的模块  回落到全局 POST_STATUSES（保持向后兼容）。
MODULE_ALLOWED_STATUSES = {
    MODULE_GROUP_BUY: (POST_ONGOING, POST_CLAIMED, POST_CLOSED),
    MODULE_ERRAND: (POST_ONGOING, POST_CLAIMED, POST_CLOSED, POST_EXPIRED),
    MODULE_DAILY: (POST_ONGOING, POST_CLOSED),
    MODULE_LOST_FOUND: (POST_ONGOING, POST_CLAIMED, POST_CLOSED, POST_EXPIRED),
}

#: 按模块覆盖「详情可查看的状态」。
#: 未列出的模块沿用上面的全局默认；这里列出的模块允许这些状态看详情。
#: 说明：失物招领的设计是"已认领/已过期/已关闭就不再展示详情"，
#: 但拼单/跑腿/日常是"流程结束后仍需要回看信息"，因此覆盖为全部状态可见。
MODULE_DETAIL_VISIBLE_STATUSES = {
    MODULE_GROUP_BUY: POST_STATUSES,     # 全部状态可看详情
    MODULE_ERRAND: POST_STATUSES,
    MODULE_DAILY: POST_STATUSES,
}

#: 按模块覆盖「列表可见的状态」（拼单"已取消"不进公开列表，与'已关闭'一致）
MODULE_LIST_VISIBLE_STATUSES = {
    MODULE_GROUP_BUY: (POST_ONGOING, POST_CLAIMED),
    MODULE_ERRAND: POST_STATUSES,
    MODULE_DAILY: (POST_ONGOING, POST_CLOSED),
}

# ---------------------------------------------------------------------------
# 通知
# ---------------------------------------------------------------------------
NOTIFY_AUDIT = 'audit'
NOTIFY_COMMENT = 'comment'
NOTIFY_MESSAGE = 'message'
NOTIFY_LIKE = 'like'
NOTIFY_MENTION = 'mention'
NOTIFY_SYSTEM = 'system'
NOTIFY_TYPES = (NOTIFY_AUDIT, NOTIFY_COMMENT, NOTIFY_MESSAGE, NOTIFY_LIKE,
                NOTIFY_MENTION, NOTIFY_SYSTEM)
NOTIFY_TYPE_LABELS = {
    NOTIFY_AUDIT: '审核',
    NOTIFY_COMMENT: '评论',
    NOTIFY_MESSAGE: '私信',
    NOTIFY_LIKE: '点赞',
    NOTIFY_MENTION: '提到我',
    NOTIFY_SYSTEM: '系统',
}

# ---------------------------------------------------------------------------
# 私信消息类型
# ---------------------------------------------------------------------------
MESSAGE_TEXT = 'text'
MESSAGE_IMAGE = 'image'
MESSAGE_VOICE = 'voice'
MESSAGE_VIDEO = 'video'
MESSAGE_TYPES = (MESSAGE_TEXT, MESSAGE_IMAGE, MESSAGE_VOICE, MESSAGE_VIDEO)
MESSAGE_TYPE_LABELS = {
    MESSAGE_TEXT: '文字',
    MESSAGE_IMAGE: '图片',
    MESSAGE_VOICE: '语音',
    MESSAGE_VIDEO: '视频',
}

# ---------------------------------------------------------------------------
# 举报 / 日志
# ---------------------------------------------------------------------------
REPORT_PENDING = 'pending'
REPORT_HANDLED = 'handled'
REPORT_REJECTED = 'rejected'
REPORT_STATUSES = (REPORT_PENDING, REPORT_HANDLED, REPORT_REJECTED)
REPORT_STATUS_LABELS = {REPORT_PENDING: '待处理', REPORT_HANDLED: '已处理', REPORT_REJECTED: '已驳回'}

LOG_TYPE_LOGIN = 'login'
LOG_TYPE_OPERATION = 'operation'
LOG_TYPE_ERROR = 'error'
LOG_TYPES = (LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, LOG_TYPE_ERROR)

RETENTION_SOFT_DELETE = 'soft_delete'
RETENTION_FORCE = 'force'

# ---------------------------------------------------------------------------
# 系统配置默认值（可被 system_configs 表中的记录覆盖）
# ---------------------------------------------------------------------------
DEFAULT_CONFIGS = {
    # 通用
    'site_name': '校园生活平台',
    'site_notice': '欢迎使用校园生活平台，请勿发布违法违规信息。',
    'api_prefix': '/api/v1',
    # 安全公告（首次使用/发布前弹出）
    'security_notice_enabled': '1',
    'security_notice_text': (
        '1. 请勿上传身份证、银行卡、家庭住址等敏感隐私信息；\n'
        '2. 平台管理员可查看所有用户发布的信息；\n'
        '3. 联系方式公开可见，请自行判断风险。'
    ),
    # 审核相关
    'post_audit_enabled': '1',          # 1=发帖需管理员审核后公开
    'register_captcha_enabled': '1',    # 1=注册需要图形验证码
    # 回收站
    'recycle_retention_count': '10',    # 回收站默认保留最近 N 条
    'recycle_retention_mode': RETENTION_FORCE,  # 超出数量后的处理方式：force=彻底删除
    # 上传
    'upload_allowed_ext': 'jpg,jpeg,png,gif,webp,mp4,mov,mp3,wav,m4a,ogg,webm',
    'upload_max_mb_image': '10',
    'upload_max_mb_video': '50',        # 需求默认 50MB
    'upload_max_mb_audio': '5',         # 语音（评论 / 私信）默认 5MB
    # 分页
    'page_default_size': '10',
    'page_max_size': '100',
    # 游客权限
    'guest_can_list': '1',              # 游客可浏览列表
    'guest_can_detail': '0',            # 游客不可查看详情
}
