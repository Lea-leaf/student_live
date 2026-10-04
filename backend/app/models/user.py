# -*- coding: utf-8 -*-
"""用户模型。"""

from datetime import datetime

from ..extensions import db
from ..utils.constants import (
    ADMIN_ROLES,
    DEFAULT_MODULE_CODE,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_USER,
    STATUS_ACTIVE,
    STATUS_BANNED,
    USER_STATUS_LABELS,
)
from .base import BaseModel


class User(BaseModel):
    """学生 / 管理员账号。

    说明：
    - 登录账号为学号 `student_id`（需求：学号 + 验证码注册）；
      `username` 保留为可选的昵称式账号，便于后续扩展邮箱/手机号登录。
    - `role` 当前仅使用 user / admin 两值，但已经按 RBAC 预留了常量集合，
      未来分级只需扩展 `utils/constants.py` 中的 ADMIN_ROLES。
    """

    __tablename__ = 'users'

    username = db.Column(db.String(64), unique=True, nullable=False, index=True, comment='登录名（默认=学号）')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    role = db.Column(db.String(32), nullable=False, default=ROLE_USER, index=True, comment='角色')
    status = db.Column(db.String(16), nullable=False, default=STATUS_ACTIVE, index=True, comment='账号状态')
    student_id = db.Column(db.String(32), unique=True, nullable=False, index=True, comment='学号')
    nickname = db.Column(db.String(64), nullable=True, comment='昵称')
    avatar = db.Column(db.String(255), nullable=True, comment='头像地址')
    email = db.Column(db.String(128), nullable=True, comment='邮箱（预留）')
    phone = db.Column(db.String(32), nullable=True, comment='手机号（预留）')
    ban_reason = db.Column(db.String(255), nullable=True, comment='封禁原因')
    banned_at = db.Column(db.DateTime, nullable=True, comment='封禁时间')
    banned_by = db.Column(db.Integer, nullable=True, comment='封禁操作人ID')
    last_login_at = db.Column(db.DateTime, nullable=True, comment='最后登录时间')
    last_login_ip = db.Column(db.String(64), nullable=True, comment='最后登录IP')
    login_count = db.Column(db.Integer, nullable=False, default=0, comment='累计登录次数')
    post_count = db.Column(db.Integer, nullable=False, default=0, comment='发帖计数（冗余，便于统计）')
    remark = db.Column(db.String(255), nullable=True, comment='管理员备注')

    # ---- 管理员移交（系统只允许一个管理员，"换人"走这套两阶段流程）----
    #: 发起人视角：准备把管理员权限交给谁
    handover_to_id = db.Column(db.Integer, nullable=True, index=True, comment='管理员权限拟移交给谁')
    #: 发起时间（北京时间）
    handover_at = db.Column(db.DateTime, nullable=True, comment='移交发起时间（北京时间）')
    #: 落地时间 = 发起时间 + 24 小时；到点后由后台请求懒执行完成切换
    handover_effective_at = db.Column(db.DateTime, nullable=True, index=True,
                                      comment='移交生效时间（北京时间）')
    #: 接班人视角：不为空表示"已是管理员但处于冻结期"，期间没有任何后台能力
    handover_freeze_at = db.Column(db.DateTime, nullable=True, index=True,
                                   comment='待上任冻结开始时间；非空即冻结中')
    #: 冻结前的原角色。冻结期按这个角色赋予能力（审核员继续审核，工作不停），
    #: 撤销移交时也按它准确恢复（否则"原本是审核员"的人撤销后会掉成普通用户）。
    handover_prev_role = db.Column(db.String(32), nullable=True,
                                   comment='接管前的原角色，用于冻结期授权与撤销时恢复')

    # 关联：帖子 / 评论 / 通知 / 收藏
    posts = db.relationship('Post', backref='author', lazy='dynamic', foreign_keys='Post.user_id')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')

    # ------------------------------------------------------------------
    # 密码
    # ------------------------------------------------------------------
    def set_password(self, raw_password):
        """设置密码（Werkzeug scrypt 哈希，自带随机盐）。"""
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """校验明文密码。"""
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, raw_password)

    # ------------------------------------------------------------------
    # 权限
    # ------------------------------------------------------------------
    @property
    def is_staff(self):
        """是否具备**后台访问权限**（能不能进管理端）。

        这是早期 `is_admin` 的语义，改名保留给路由守卫与菜单渲染使用。
        注意：能进后台 ≠ 是管理员 —— 审核员、版主同样能进。
        """
        return self.role in ADMIN_ROLES

    @property
    def is_admin(self):
        """是否为**真正的管理员**（最高等级，通配全部后台能力）。

        ⚠️ 与 `is_staff` 的区别（历史坑，详见 docs/USER_FIELDS.md）：
        早期 `is_admin` 等同于「在 ADMIN_ROLES 里」，导致审核员一旦被创建
        就自动获得全部管理员权限（发帖免审、可编辑他人正文、可改系统配置）。
        现在收紧为「真正的管理员」，受限后台角色不再享有管理员特权。

        ⚠️ **冻结中的待上任管理员不算管理员**：他还没正式上任，
        不该享有"发帖免审核""可编辑他人正文"这类特权 ——
        否则等于交接完成前就先把管理员权力用上了。
        这一条同时堵住了"只在路由层拦截"的漏洞：`build_post` / `can_edit`
        这些**不在后台路由里**的判断点也会跟着正确。
        """
        if self.is_frozen:
            return False
        from ..utils.constants import TRUE_ADMIN_ROLES

        return self.role in TRUE_ADMIN_ROLES

    @property
    def capabilities(self):
        """当前可用的后台能力清单（前端据此渲染菜单与按钮）。

        ⚠️ 冻结中的待上任管理员：**按他原来的角色**给能力。
        例如原本是审核员，冻结期仍可进审核台审帖、删评论 —— 交接不该让他停工；
        只是拿不到管理员那些项（配置 / 模块 / 角色 / 回收站…）。
        """
        from ..utils.constants import capabilities_of

        if self.is_frozen:
            return capabilities_of(self.handover_prev_role)
        return capabilities_of(self.role)

    def has_capability(self, capability):
        """是否具备某项后台能力（冻结中按原角色判定）。"""
        from ..utils.constants import has_capability

        if self.is_frozen:
            return has_capability(self.handover_prev_role, capability)
        return has_capability(self.role, capability)

    @property
    def is_banned(self):
        return self.status == STATUS_BANNED

    @property
    def is_frozen(self):
        """是否为**冻结中的待上任管理员**。

        冻结期（默认 24 小时）内他已经是管理员身份，但**按原角色**工作、
        且拿不到任何管理员特权（`is_admin` 为假）。这样：
        - 原本是审核员 → 继续审核，工作不停；
        - 原本是普通用户 → 就是个普通用户，没有后台；
        - 交接生效前系统里始终只有原管理员一个人能动管理员功能。
        """
        return bool(self.role == ROLE_ADMIN and self.handover_freeze_at)

    def is_owner_of(self, obj):
        """是否为某资源的属主。"""
        return getattr(obj, 'user_id', None) == self.id

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------
    def ban(self, reason=None, operator_id=None):
        """封禁账号。"""
        self.status = STATUS_BANNED
        self.ban_reason = reason
        self.banned_at = datetime.now()
        self.banned_by = operator_id

    def unban(self):
        """解封账号。"""
        self.status = STATUS_ACTIVE
        self.ban_reason = None
        self.banned_at = None
        self.banned_by = None

    def mark_login(self, ip=None):
        """记录一次成功登录。"""
        self.last_login_at = datetime.now()
        self.last_login_ip = ip
        self.login_count = (self.login_count or 0) + 1

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def to_dict(self, exclude=None, extra=None, with_sensitive=False):
        """序列化用户。

        ⚠️ `with_sensitive=False`（默认）时**必须显式排除**邮箱与手机号：
        `BaseModel.to_dict()` 会遍历全部列，只加 `exclude` 是拦不住的
        （早期写法只做了 `if with_sensitive: data['email'] = ...`，
        看起来像"按需下发"，实际两个字段一直都在响应里）。
        """
        exclude = set(exclude or ())
        exclude.add('password_hash')
        if not with_sensitive:
            exclude.update(('email', 'phone'))
        data = super().to_dict(exclude=exclude, extra=extra)
        data['role_label'] = ROLE_LABELS.get(self.role, self.role)
        data['status_label'] = USER_STATUS_LABELS.get(self.status, self.status)
        data['is_admin'] = self.is_admin
        data['is_staff'] = self.is_staff
        #: 身份标识：前端据此显示「管理员 / 内容审核员 / 普通用户」徽章并渲染菜单
        data['identity'] = 'staff' if self.is_staff else 'user'
        data['capabilities'] = self.capabilities
        #: 交接状态：前端据此显示「交接中」提示，但**身份仍按原角色显示** ——
        #: 对外看到的身份要等于他实际能用的权限，避免"挂着管理员头衔却什么都干不了"。
        data['is_frozen'] = self.is_frozen
        data['handover_pending'] = self.is_frozen
        if self.is_frozen:
            prev = self.handover_prev_role or ROLE_USER
            data['role_label'] = ROLE_LABELS.get(prev, prev)
            data['previous_role'] = prev
        data['display_name'] = self.nickname or self.username or self.student_id
        return data

    def to_brief(self):
        """帖子/评论中展示的用户摘要（不含任何敏感信息）。

        带上 `role` / `role_label`：前端需要在帖子、评论旁显示「管理员 / 审核员」身份标识，
        让用户看得出这条内容是谁在处理。这里只暴露角色名，不暴露任何权限能力。
        """
        return {
            'id': self.id,
            'student_id': self.student_id,
            'nickname': self.nickname,
            'username': self.username,
            'avatar': self.avatar,
            'role': self.role,
            'role_label': ROLE_LABELS.get(self.role, self.role),
            'is_staff': self.is_staff,
            'display_name': self.nickname or self.username or self.student_id,
        }

    def __repr__(self):
        return f'<User {self.student_id} role={self.role} status={self.status}>'


__all__ = ['User', 'DEFAULT_MODULE_CODE', 'STATUS_ACTIVE', 'STATUS_BANNED']
