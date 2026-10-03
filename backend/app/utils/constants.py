# -*- coding: utf-8 -*-
"""常量与枚举定义。

集中管理所有状态值，避免在业务代码里散落魔法字符串。
前端可通过 `GET /api/v1/common/enums` 一次性拿到全部字典。
"""

# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
ROLE_USER = 'user'
ROLE_ADMIN = 'admin'
# 预留：RBAC 多级管理员（参见需求文档「管理员分级思路」）
ROLE_SUPER_ADMIN = 'super_admin'
ROLE_AUDITOR = 'auditor'
ROLE_USER_ADMIN = 'user_admin'
ROLE_MODULE_ADMIN = 'module_admin'
ROLE_MODERATOR = 'moderator'

ROLES = (ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_AUDITOR,
         ROLE_USER_ADMIN, ROLE_MODULE_ADMIN, ROLE_MODERATOR)
ROLE_LABELS = {
    ROLE_USER: '普通用户',
    ROLE_ADMIN: '管理员',
    ROLE_SUPER_ADMIN: '超级管理员',
    ROLE_AUDITOR: '内容审核员',
    ROLE_USER_ADMIN: '用户管理员',
    ROLE_MODULE_ADMIN: '模块管理员',
    ROLE_MODERATOR: '版主',
}
#: 当前具备后台访问权限的角色集合（后续扩展只需改这里）
ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_AUDITOR,
               ROLE_USER_ADMIN, ROLE_MODULE_ADMIN, ROLE_MODERATOR)

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
MODULE_OTHER = 'other'

#: 兜底模块：管理员可自由新增模块，未登记的自定义 type 也能工作
DEFAULT_MODULE_CODE = MODULE_LOST_FOUND

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
