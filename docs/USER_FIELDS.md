# 用户相关字段清单与问题成因分析

> **这份文档回答**：用户/权限相关的表到底有哪些字段？每个字段现在被谁用、怎么用？
> 为什么「管理员 / 普通用户 / 审核员」三级角色在**字段齐全**的情况下依然**区分不开**？
>
> ⚠️ **本文记录「修复前」的诊断结论（审计 #3，2026-10-05）**，用来解释问题是怎么产生的。
> **修复已于同日完成（v1.4）**，落地清单与验证结果见 [AUDIT.md 的「修复记录 #3」](AUDIT.md)。
> 第三节的成因与第四节的目标结构现已生效；第五节风险清单里 **R1 ~ R5 已关闭**，
> R6 / R7 / R8 / R9 仍开放。
>
> 与其它文档的分工：
> - `ER.md` —— 全部表结构（自动生成，只讲"长什么样"）
> - `AUDIT.md` —— 定期体检、待办跟踪与修复记录
> - **`USER_FIELDS.md`（本文）** —— 用户/权限字段的**逐个字段责任表** + **问题成因**（讲"为什么坏、坏在哪一行"）
> - `ROLE_SESSION_ANALYSIS.md` —— 角色适配性结论 + 同机多账户会话推演

---

## 〇、一页结论

| 判断 | 结论 |
|---|---|
| 用户表**字段数量**够不够？ | ✅ 够。`users` 20 列已覆盖身份、认证、角色、状态、统计、审计六类需求 |
| 用户表**缺字段**吗？ | ⚠️ 当时只缺 **2 个**：审核指派、令牌撤销 → 其中指派已加，`token_version` 仍缺（P9） |
| 那为什么三级角色不能用？ | ❌ **问题不在表，在代码**：`role` 存进去了，但**没有任何一行代码按它分流** |
| 最根本的一条成因 | **`User.is_admin` 一个布尔属性同时承担了「是不是后台用户」和「是不是管理员」两种语义** |
| 影响面 | 后端 **11 处**、前端 **9 处**，共 20 个判定点全部受影响 |

**一句话**：这不是"表没设计好"，是**"一个字段当了两个用"**。

> ### ✅ 修复状态（2026-10-05）
>
> 本文的成因分析**已全部落地修复**，现在读到的"问题"是历史诊断记录：
>
> | 本文的结论 | 现状 |
> |---|---|
> | `is_admin` 一个布尔承担两种语义 | ✅ 已拆成 `is_staff`（能不能进后台）/ `is_admin`（是不是管理员） |
> | 所有接口不区分角色 | ✅ 全部按 `capability` 归类 |
> | 缺少指派字段 / 流水表 | ✅ `posts` 加 4 列 + `post_audit_logs` 表 |
> | 角色口径有四套 | ✅ 收敛成三层（`super_admin` 已移除） |
> | 风险清单 R1 ~ R5 | ✅ 已关闭（R6/R7/R8/R9 仍开放） |
>
> 权威的完成度清单见 [README 第十节](../README.md)；详细修复记录见 [AUDIT.md](AUDIT.md)。

---

## 一、`users` 表字段逐项清单（20 列）

来源：`backend/app/models/user.py:31-47` + 基类 `models/base.py:20-24`。
数据库实际结构已核对 `docs/schema_sqlite.sql:89-119`，**与模型一致，无漂移**。

### 1.1 身份标识

| 字段 | 类型 | 可空 | 索引 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|---|
| `id` | Integer PK | 否 | PK | 主键 | 全局外键目标（`posts.user_id`、`comments.user_id`、`messages.sender_id`…） |
| `username` | String(64) | 否 | **唯一** | 登录名，注册时默认等于学号 | 登录支持 `student_id` 或 `username` 二选一（`auth/routes.py:177-179`） |
| `student_id` | String(32) | 否 | **唯一** | 学号，**事实上的主身份** | 上传目录按它分（`uploads/<学号>/<日期>/`）、帖子/评论对外展示它 |
| `nickname` | String(64) | 是 | — | 昵称 | `to_brief()` 优先展示它，无则回落 `username` → `student_id` |
| `avatar` | String(255) | 是 | — | 头像地址 | `to_brief()` 下发；`upload_files.owner_type` 支持 `'avatar'` |
| `email` | String(128) | 是 | — | 邮箱（**预留**） | 仅 `to_dict(with_sensitive=True)` 时下发，**无任何业务逻辑使用** |
| `phone` | String(32) | 是 | — | 手机号（**预留**） | 同上，**无业务逻辑使用** |

> 📌 **观察 1**：`student_id` 是唯一带**物理副作用**的字段 —— 它决定了 `uploads/` 目录名。
> 删除用户要整目录删除、上传要用它建目录，所以它**不能随便改**（当前也没有改学号的接口，这点是对的）。

### 1.2 认证凭据

| 字段 | 类型 | 可空 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|
| `password_hash` | String(255) | 否 | Werkzeug **scrypt** 哈希（自带随机盐） | `set_password()` / `check_password()`；`to_dict()` **强制排除**该字段（`user.py:121`） |
| `last_login_at` | DateTime | 是 | 最后登录时间 | `mark_login()` 写入；用户详情页展示 |
| `last_login_ip` | String(64) | 是 | 最后登录 IP | 同上 |
| `login_count` | Integer | 否 | 累计登录次数 | `mark_login()` **自增**；用户详情页展示 |

> 📌 **观察 2**：认证相关字段是**完整且正确**的 —— 密码哈希用工业级算法、敏感字段序列化时被排除、
> 登录信息有留痕。**这一组不是问题来源。**

### 1.3 角色与权限 ← **问题重灾区**

| 字段 | 类型 | 可空 | 索引 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|---|
| `role` | String(32) | 否 | 有 | 角色标识 | ⚠️ **写入路径齐全，读取路径只有"是不是后台"一种判断**（详见第三节） |

**`role` 字段的完整生命周期**：

| 阶段 | 位置 | 行为 | 评价 |
|---|---|---|---|
| 定义可选值 | `utils/constants.py:11-30` | 7 个常量 + `ROLE_LABELS` 中文名 | ✅ 完整，含 `auditor` = 「内容审核员」 |
| 注册赋值 | `auth/routes.py:145` | 硬编码 `role=ROLE_USER` | ✅ 正确（注册不能自选角色） |
| 后台创建时赋值 | `admin/users.py:263-267` | 校验 `role not in ROLES`；非超管不能建管理员 | ✅ 正确 |
| 后台改角色 | `admin/users.py:213-234` | `@super_admin_required`；校验取值；不能取消自己的管理员权限 | ✅ 正确 |
| 列表按角色筛选 | `admin/users.py:72-73` | `query.filter(User.role == role)` | ✅ 正确 |
| 签发 token 时带进 JWT | `utils/auth.py:58` | `'role': user.role` | ⚠️ **带了但从来没人读** |
| **读取分权** | `utils/auth.py:175` | `if not user.is_admin` | ❌ 只判断"是不是后台角色"，**7 个角色被压成 1 个布尔值**（现已按 `capability` 分流） |
| 在下拉框展示 | `common/routes.py:34` | `'role': _pairs(ROLE_LABELS)` | ✅ 前端能看到 6 个选项 |

> **核心矛盾**：`role` 能存 7 种值，**判定只有 2 种结果**。
> 管理后台的下拉框能让管理员把某人设成「内容审核员」，
> 但这个操作在系统行为上**唯一的效果是：此人也变成了管理员**。

### 1.4 账号状态

| 字段 | 类型 | 可空 | 索引 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|---|
| `status` | String(16) | 否 | 有 | `active` / `banned` | 每次请求校验（`auth.py:128`）→ 封禁**即时生效**，这是设计得对的地方 |
| `ban_reason` | String(255) | 是 | — | 封禁原因 | `ban()` 写入；登录时回显给被封者 |
| `banned_at` | DateTime | 是 | — | 封禁时间 | `ban()` 写入 |
| `banned_by` | Integer | 是 | — | 封禁操作人 ID | `ban()` 写入（**注意：这是裸整数，没有外键约束**） |

> 📌 **观察 3**：状态字段"每次请求校验"的做法**比 JWT 常见的坑要正确** ——
> 封禁用户立刻失效，不需要等 token 过期。这一组也不是问题来源。

### 1.5 统计与备注

| 字段 | 类型 | 可空 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|
| `post_count` | Integer | 否 | 发帖计数（冗余） | 用户列表排序用（`admin/users.py:81`）。**真正统计时仍走 `Post.query.count()`**（`users.py:99`），与 `recount.py` 的对账范围**不含此列** |
| `remark` | String(255) | 是 | 管理员备注 | `POST /admin/users/<id>/remark` 可改，用于记录沟通情况 |

### 1.6 审计痕迹

| 字段 | 类型 | 可空 | 业务语义 | 当前使用情况 |
|---|---|---|---|---|
| `created_at` | DateTime | 否 | 注册时间 | 基类自动维护 |
| `updated_at` | DateTime | 否 | 更新时间 | 基类 `onupdate` 自动维护 |

### 1.7 表级约束与索引

| 名称 | 类型 | 说明 |
|---|---|---|
| `PRIMARY KEY (id)` | 主键 | — |
| `ix_users_username` | **唯一**索引 | 登录名不重复 |
| `ix_users_student_id` | **唯一**索引 | 学号不重复 |
| `ix_users_role` | 普通索引 | 支持按角色筛选 |
| `ix_users_status` | 普通索引 | 支持按状态筛选 |

> 📌 **观察 4**：`role` 列**没有 CHECK 约束、没有数据库层枚举**。
> 好处是加角色不用改表；代价是**任何写错的值都会被静默接受**。
> 组合索引 `(role, status)` 也不存在 —— 但按 AUDIT #1 的 P4 判断，毕设规模无需加。

---

## 二、权限相关的**其它**用户字段（分散在三张表）

三级角色不只涉及 `users` 表，还有两处"用户 × 权限"的承载：

### 2.1 `admin_module_access` —— 管理员↔模块授权（**建了但完全没用**）

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | Integer **FK → users.id** | 管理员 |
| `module_code` | String(64) | 模块标识（对应 `modules.code`） |
| `permission` | String(32) | `manage` / `audit` / `read` |
| 约束 | `uq_admin_module UNIQUE(user_id, module_code)` | 一人一模块一条 |

**真实状态**：全仓库**只有一处读**（`utils/auth.py:241-243`），**零处写** ——
没有任何接口能往这张表插入授权。而那个唯一的读，还是在一个**从未被调用**的装饰器里。

### 2.2 `modules.allow_roles` —— 模块允许的角色（**存了但不校验**）

| 位置 | 行为 |
|---|---|
| `models/module.py:29` | 列定义：`String(255)`，"允许发布的角色，逗号分隔" |
| `admin/modules.py:127-128` | 管理员**能写入**这个值 |
| 业务代码 | **没有任何地方读它做校验** —— 写了等于没写 |

### 2.3 跨表引用 `users.id` 的字段（删用户时必须一起处理）

| 表 | 字段 | 外键 | 说明 |
|---|---|---|---|
| `posts` | `user_id` | ✅ FK | 发布者 |
| `posts` | `audited_by` | ❌ 裸整数 | 审核人（**只记最后一个**） |
| `posts` | `deleted_by` | ❌ 裸整数 | 删除人 |
| `comments` | `user_id` | ✅ FK | 评论人 |
| `comments` | `reply_to_user_id` | ❌ 裸整数 | 被回复人 |
| `messages` | `sender_id` / `receiver_id` | ✅ FK ×2 | 收发双方 |
| `favorites` / `post_likes` / `comment_likes` | `user_id` | ✅ FK | 交互主体 |
| `reports` | `reporter_id` / `target_user_id` / `handled_by` | 部分 FK | 举报人 / 被举报人 / 处理人 |
| `admin_module_access` | `user_id` | ✅ FK | 模块授权 |
| `upload_files` | `user_id` | ✅ FK | 上传者 |
| `operation_logs` | `user_id` | ❌ 裸整数 | 操作人（**刻意不加 FK**：日志要能被删除的用户留下快照，`purge_user` 只置 NULL） |
| `login_logs` | `user_id` | ❌ 裸整数 | 登录人（同上，另带 `username` 快照） |
| `users` | `banned_by` | ❌ 裸整数 | 封禁操作人 |

> 📌 **观察 5**：`audited_by` / `deleted_by` / `handled_by` / `banned_by` 都是**裸整数**。
> 这是有意为之（操作人注销后历史记录仍要保留），但也意味着**无法 JOIN 出"审核人姓名"**，
> 只能靠应用层二次查询（`admin/posts.py:133-137` 就是这么做的）。
> **这恰恰提示了 `assignee_id` 应该怎么设计**：跟 `audited_by` 保持同一种风格（裸整数 + 应用层翻译）。

---

## 三、问题成因分析（核心章节）

### 3.1 成因树：一个根因，两种表现

```
根因 ①：User.is_admin 语义混淆（一个布尔值承担两种含义）
   │   models/user.py:72-75 → return self.role in ADMIN_ROLES
   │   ADMIN_ROLES = (admin, super_admin, auditor, user_admin, module_admin, moderator)
   │
   ├─→ 表现 A：审核员 = 管理员（垂直越权）
   │     后端 11 处权限判定全部走 is_admin → auditor 直接拿到全部后台能力
   │     前端 9 处判定全部走 is_admin → auditor 看到完整管理端菜单
   │
   └─→ 表现 B：审核员发帖免审核（横向逻辑错误）
          posts_service.build_post:230  if user.is_admin or not audit_enabled
          → 一个"来审别人帖子"的角色，自己的帖子直接跳过审核

根因 ②：role 是裸字符串，没有任何"角色 → 能力"的映射表
   │   constants.py 只有 ROLES（有哪些角色），没有 ROLE_PERMISSIONS（角色能做什么）
   │
   └─→ 表现 C：加角色 = 加一个字符串，系统行为零变化
          admin/users.py:222 校验通过（role ∈ ROLES）→ 写入成功 → 什么也没发生

根因 ③：/admin 是一个"全有或全无"的门禁
   │   ADMIN_BLUEPRINTS 9 个蓝图、53 个接口，统一 @admin_required 无参
   │
   └─→ 表现 D：无法表达"审核员只能进审核台"
          模块级权限（admin_module_access + module_permission_required）已预留但未接线
```

### 3.2 根因 ①：`is_admin` 语义混淆 —— 问题的总开关

**定义**（`models/user.py:72-75`）：

```python
@property
def is_admin(self):
    """是否具备后台访问权限（管理员分级后依然成立）。"""
    return self.role in ADMIN_ROLES
```

**注释里那句"管理员分级后依然成立"就是这个 bug 的自我说明**：
它把「**能不能进后台**」和「**是不是管理员**」当成了同一件事。
在只有 `user` / `admin` 两级时这是成立的（能进后台 = 管理员）；
一旦引入 `auditor`，这个等式立刻失效 —— **审核员能进后台，但显然不是管理员**。

> ✅ **现已修正为**（`models/user.py`）：
> ```python
> @property
> def is_staff(self):        # 能不能进后台（原 is_admin 的语义）
>     return self.role in ADMIN_ROLES
>
> @property
> def is_admin(self):        # 是不是管理员（最高级）
>     if self.is_frozen:     # 交接冻结中不算管理员
>         return False
>     return self.role in TRUE_ADMIN_ROLES
> ```

**这个属性当时被 20 处代码消费，每一处都因此产生偏差**：

#### 后端 11 处（`backend/app`）

| # | 位置 | 代码 | 本意 | 引入 auditor 后的实际后果 | 严重度 |
|---|---|---|---|---|---|
| B1 | `utils/auth.py:175` | `if not user.is_admin:` | 拦住普通用户 | **53 个后台接口对 auditor 全开**（含 `PUT /admin/configs`、`reset-password`） | 🔴 |
| B2 | `admin/users.py:152` | `if user.is_admin and not operator.is_super_admin:` | 保护管理员账号不被封禁 | auditor **受这层保护**（普通管理员封不了他），但他本不该享有此保护 | 🟡 |
| B3 | `admin/users.py:195` | 同上（重置密码） | 保护管理员密码 | 同上 | 🟡 |
| B4 | `admin/users.py:306` | 同上（批量封禁） | 同上 | 同上 | 🟡 |
| B5 | `admin/users.py:405` | 同上（彻底删除） | 同上 | 同上 | 🟡 |
| B6 | `admin/users.py:224` | `if user.id == operator.id and role not in ADMIN_ROLES:` | 防止自己把自己降权 | auditor 也进 `ADMIN_ROLES`，语义偶然正确 | ⚪ |
| B7 | `modules/posts_service.py:62` | `if user and user.is_admin: return True` | 管理员可见一切帖子（含待审） | auditor 可见全部未过审帖子（**这个是合理的**，但他同时能看草稿态） | 🟡 |
| B8 | `modules/posts_service.py:73` | `if user.is_admin: return True` | 管理员可编辑任意帖子 | **auditor 可编辑任意帖子的标题/正文/联系方式** | 🔴 |
| B9 | `modules/posts_service.py:230` | `if user.is_admin or not audit_enabled:` | 管理员发帖免审 | **auditor 发帖免审** —— 审核者绕过审核 | 🔴 |
| B10 | `modules/lost_found/routes.py:189` | `data['can_audit'] = bool(user and user.is_admin ...)` | 下发"我能审吗" | 语义**偶然正确**（auditor 确实该能审），但也让 admin 在前台看到审核按钮 | ⚪ |
| B11 | `modules/lost_found/routes.py:306` | `if not user.is_admin and post_audit_enabled():` | 编辑后重新送审 | **auditor 编辑帖子不会重新送审** | 🔴 |

**另外 3 处"用对了但写法不统一"的地方**（值得注意，说明作者其实意识到要区分）：

| 位置 | 代码 | 说明 |
|---|---|---|
| `modules/lost_found/routes.py:106` | `elif show_all and user and user.is_admin:` | 与 B7 同义，重复实现 |
| `modules/lost_found/routes.py:184` | `if not user or (post.user_id != user.id and not user.is_admin):` | 浏览量不计数 |
| `modules/comments/routes.py:328` | `is_admin = user.role in ADMIN_ROLES` | ⚠️ **这里绕过了 `is_admin` 属性，直接查 `ADMIN_ROLES`** —— 效果相同，但**同一个判断在仓库里有两种写法**，将来改权限必然漏掉一处 |

> 🔴 **B_extra（最危险的一处，容易漏）**：`comments/routes.py:328-339`
> 评论删除逻辑用 `user.role in ADMIN_ROLES` 判断，为真则走**管理员分支**：
> **跳过 5 分钟撤回限制、物理删除任意人的评论**（连同子回复、点赞、媒体文件、互动通知）。
> 也就是说 **auditor 可以无限制删除任何用户的评论**。这不在 `@admin_required` 的 53 个接口里，
> 而是一个**用户端接口内的隐藏特权分支** —— 排查时极易漏掉。

#### 前端 9 处（`frontend/src`）

| # | 位置 | 代码 | 后果 |
|---|---|---|---|
| F1 | `stores/user.js:24` | `isAdmin: (state) => !!(state.user && state.user.is_admin)` | **所有前端判定的总来源** |
| F2 | `router/index.js:214` | `if (to.meta.requiresAdmin && !userStore.isAdmin)` | auditor **可以进任意管理端路由**（用户管理、系统配置…） |
| F3 | `layouts/UserLayout.vue:168` | `v-if="userStore.isAdmin"` → 跳到管理端 | 前台下拉菜单直接给 auditor 开后台入口 |
| F4 | `layouts/AdminLayout.vue` 菜单 | 菜单项无角色过滤 | **渲染出完整 10 项管理菜单** |
| F5 | `components/CommentSection.vue:84,284,346` | `isAdmin` → 显示"删除评论"按钮 | auditor 在前台就能删任意评论（对应上面 B_extra） |
| F6 | `views/user/PostDetailView.vue:45` | `post.user_id === user.id \|\| userStore.isAdmin` | 显示"编辑"入口（对应 B8） |
| F7 | `views/user/LoginView.vue:46` | `else if (user.is_admin)` → 跳管理端 | **auditor 登录后被直接送进管理后台**，而非前台 |
| F8 | `views/admin/UserManageView.vue:244` | `:type="row.is_admin ? 'danger' : 'info'"` | 审核员标签显示为**红色"管理员"样式** |
| F9 | `views/user/ProfileView.vue:102,116` | `v-if="user.is_admin"` | 个人中心显示管理员样式与后台入口 |

### 3.3 根因 ②：没有「角色 → 能力」映射表

`constants.py` 里只有"有哪些角色"（`ROLES` / `ROLE_LABELS` / `ADMIN_ROLES`），
**没有"每个角色能做什么"**。缺失的正是这张表：

```python
# 现在的 constants.py —— 只有名单，没有能力
ROLES = ('user', 'admin', 'super_admin', 'auditor', 'user_admin', 'module_admin', 'moderator')
ADMIN_ROLES = ('admin', 'super_admin', 'auditor', ...)   # ← 一锅端
```

后果链条：

```
管理员在后台把某人设为 auditor
  → admin/users.py:222 校验 role ∈ ROLES  ✅ 通过
  → user.role = 'auditor'，db.commit()      ✅ 落库
  → 用户列表显示「内容审核员」标签           ✅ 界面正确
  → 该用户下一次请求 → auth.py:175 is_admin → True → 拿到全部管理员权限
  → 结论：这次角色变更的唯一实际效果，是把一个普通用户升级成了管理员
```

### 3.4 根因 ③：权限门禁只有"开/关"两档

`utils/auth.py` 里其实**已经写好了收窄能力**，但没人用：

```python
def admin_required(view_func):
    roles = None
    if callable(view_func):
        pass
    else:  # 被当作 admin_required(roles=(...)) 调用
        roles = view_func          # ← 参数解析逻辑写好了
        view_func = None

    def decorator(func):
        ...
        if roles and user.role not in roles and user.role != ROLE_SUPER_ADMIN:
            return error('当前管理员角色无此权限', ...)   # ← 收窄逻辑也写好了
```

**但仓库里 53 处调用全是无参 `@admin_required`**（全量扫描结果）：

```
@admin_required             53 处（9 个蓝图）
@super_admin_required        2 处（角色调整 / 彻底删除用户）
@admin_required(roles=...)   0 处   ← 写好的能力，从未使用
@module_permission_required  0 处   ← 定义了，零调用
```

而 `module_permission_required` 即使被调用，**默认行为还是放行**而不是拒绝：

```python
# utils/auth.py:238-247
if not user.is_super_admin:
    access = AdminModuleAccess.query.filter_by(...).first()
    g.module_scope = access.permission if access else None   # ← 无授权 = None，但继续往下走
else:
    g.module_scope = 'all'
return view_func(*args, **kwargs)     # ← 一律放行
```

于是形成"**三重失效**"：能力写好了没人用 → 预留表没人写 → 唯一的读还是放行语义。

---

## 四、既有结构 vs 目标结构（差距对照）

### 4.1 字段级差距

| 需求 | 现有承载 | 是否够用 | 需要新增 |
|---|---|---|---|
| 三种角色可区分 | `users.role` (String 32) | ✅ 存储够用 | 无需新增（改代码） |
| 角色能做什么 | ❌ 无 | ❌ | `ROLE_PERMISSIONS` 常量表（**代码层，不改库**） |
| 某一模块谁能管 | `admin_module_access` 表 + `modules.allow_roles` 列 | ⚠️ 表在、无写入口、无校验 | 补写入接口 + 接线（可选，v2.0） |
| 帖子派给哪个审核员 | ❌ 无 | ❌ | `posts.assignee_id` / `assigned_by` / `assigned_at` |
| 审核改派历史 | ❌ 无 | ⚠️ 可选 | `post_audit_assignments` 表（决策 D3） |
| 谁审的（事后） | `posts.audited_by` / `audited_at` / `audit_remark` | ✅ | 无需新增 |
| 审核台账 | `operation_logs`（`action='audit'`） | ✅ | 无需新增 |
| 强制下线 / 令牌撤销 | ❌ 无 | ❌ | `users.token_version`（决策 D4） |
| 审核员工作量统计 | 可从 `operation_logs` 聚合 | ✅ 临时够用 | 数据量大时再加汇总表 |

**合计：`users` 表只需加 1 列（`token_version`），`posts` 表加 3 列，可选加 1 张表。**

### 4.2 建议的目标字段定义

```python
# ---------- models/user.py 新增 1 列 ----------
token_version = db.Column(db.Integer, nullable=False, default=0, server_default='0',
                          comment='令牌版本；+1 即让该用户所有旧 token 立即失效')
```

```python
# ---------- models/post.py 新增 3 列（跟随 audited_by 的裸整数风格）----------
assignee_id = db.Column(db.Integer, nullable=True, index=True, comment='指派审核员ID')
assigned_by = db.Column(db.Integer, nullable=True, comment='指派人ID')
assigned_at = db.Column(db.DateTime, nullable=True, comment='指派时间')
```

```python
# ---------- utils/constants.py 新增（纯代码，不动库）----------
#: 角色 → 后台能力集合（'*' 表示全部）
ROLE_PERMISSIONS = {
    ROLE_SUPER_ADMIN:  {'*'},
    ROLE_ADMIN:        {'post.audit', 'post.manage', 'user.manage', 'module.manage',
                        'config.manage', 'log.view', 'trash.manage', 'report.handle'},
    ROLE_AUDITOR:      {'post.audit.view', 'post.audit.do'},      # 只给审核
    ROLE_USER_ADMIN:   {'user.manage', 'log.view'},
    ROLE_MODULE_ADMIN: {'module.manage', 'post.audit'},
    ROLE_MODERATOR:    {'post.audit.view', 'post.audit.do', 'report.handle'},
    ROLE_USER:         set(),
}
```

```python
# ---------- models/user.py 修正语义（关键改动）----------
@property
def is_staff(self):
    """是否能进后台（原来的 is_admin 语义，保留给路由守卫用）。"""
    return self.role in ADMIN_ROLES

@property
def is_admin(self):
    """真正的管理员（不含 auditor / moderator 等受限角色）。"""
    return self.role in (ROLE_ADMIN, ROLE_SUPER_ADMIN)
```

### 4.3 升级方式

```powershell
# 1. 改模型 → 2. 预演 → 3. 执行（幂等，只加列不删数据）
cd backend
.\.venv\Scripts\python.exe scripts\upgrade_schema.py --check
.\.venv\Scripts\python.exe scripts\upgrade_schema.py

# 4. 同步生成建表 SQL 与 ER 图
.\.venv\Scripts\python.exe scripts\gen_schema_docs.py

# 5. 回归
.\.venv\Scripts\python.exe -m pytest tests -q
```

> ⚠️ **SQLite 加列是安全的**（`ALTER TABLE ADD COLUMN`），但如果将来要**改列的可空性/类型**
> （例如把 `role` 换成枚举），SQLite 必须重建表 —— 这也是"`role` 保持 String 更好"的理由。

### 4.4 每处 `is_admin` 应该改成什么（改造对照表）

| 位置 | 改成 | 理由 |
|---|---|---|
| `auth.py:175` | 拆成 `is_staff` + 能力校验 | 门禁按能力判定，不按身份 |
| `auth.py:238` | 未授权时改 `return error(403)` | 现在的"默认放行"是安全隐患 |
| `posts_service.py:62` | `staff_can_view_all(user)` → admin + 有 `post.audit.view` 的角色 | 审核员**应该**能看待审帖 |
| `posts_service.py:73` | 仅 `is_admin` | 编辑他人内容是管理员动作，审核员不该有 |
| `posts_service.py:230` | 仅 `is_admin`（+ 新增禁止自审） | **审核员的帖子必须走审核** |
| `lost_found/routes.py:306` | 仅 `is_admin` | 审核员编辑帖子要重新送审 |
| `comments/routes.py:328` | `user.role in ADMIN_ROLES` → `is_admin`（或按 `comment.manage` 能力） | 关掉隐形的"管理员分支"特权 |
| 前端 `stores/user.js:24` | 后端下发 `permissions: [...]`，前端按能力渲染 | 前端只做展示，**不当安全边界** |

---

## 五、字段级风险清单（按严重度）

| 编号 | 字段 / 属性 | 风险 | 触发条件 | 影响 |
|---|---|---|---|---|
| **R1** | `role`（经 `is_admin`） | 🔴 垂直越权 | 把某人设为 `auditor` | 该用户获得 53 个后台接口权限，含改系统配置、重置任意用户密码、彻底删除数据 |
| **R2** | `role`（经 `ADMIN_ROLES`） | 🔴 隐藏特权分支 | auditor 调用户端删评论接口 | 无限制物理删除任意评论（跳过 5 分钟限制） |
| **R3** | `is_admin` @ `build_post:230` | 🔴 审核绕过 | auditor 发帖 | 自己的帖子直接 `approved`，不经任何审核 |
| **R4** | `is_admin` @ `can_edit:73` | 🔴 越权改内容 | auditor 调编辑接口 | 可改**任意**帖子的标题/正文/联系方式，且改完不重新送审 |
| **R5** | `--`（缺字段） | 🔴 无指派机制 | 需求要求"管理员指定审核员" | 需求无法实现；`audited_by` 只能事后追责 |
| **R6** | `role` 无 CHECK 约束 | 🟡 数据卫生 | 手工改库 / 导入名单出错 | 非法角色值被静默接受，行为回落到"普通用户"且无报错 |
| **R7** | `admin_module_access` 无写入口 | 🟡 功能悬空 | 想做模块级审核员 | 表存在但无法授权，装饰器还会放行 |
| **R8** | `modules.allow_roles` 无校验 | 🟡 功能悬空 | 管理员设置了角色限制 | 界面能存，实际不生效（**假承诺**） |
| **R9** | `--`（缺字段） | 🟡 无法强制下线 | 改密码 / 重置密码 / 封禁后 | 旧 token 仍有效 24 小时（无 `token_version`） |
| **R10** | `audited_by` 等裸整数 | ⚪ 查询成本 | 展示审核人姓名 | 无法 JOIN，需应用层二次查询（已有实现，可接受） |
| **R11** | `post_count` 冗余 | ⚪ 潜在漂移 | 删帖 / 删用户 | **不在 `recount.py` 对账范围内**，长期可能与实际不符 |

---

## 六、给审计文档的登记建议

建议在 `AUDIT.md` 的待办清单里新增以下条目（编号接在 P4 / D1 之后）：

| 编号 | 问题 | 严重度 | 关闭条件 |
|---|---|---|---|
| P5 | `User.is_admin` 语义混淆，导致 auditor 等价于 admin | 🔴 高 | 拆分 `is_staff` / `is_admin`，20 处判定点全部按能力改造完成 |
| P6 | `comments/routes.py:328` 存在隐藏的管理员特权分支 | 🔴 高 | 改为能力判定；补一条"审核员不能无限制删评论"的回归测试 |
| P7 | 审核员的帖子免审核、可编辑任意帖子 | 🔴 高 | `can_edit` / `build_post` / 编辑送审三处仅对真管理员放行 |
| P8 | `admin_module_access` 无写入路径、`allow_roles` 无校验 | 🟡 中 | 二选一：补接口接线，或明确标注"未实现"并从后台界面移除该字段 |
| P9 | 无 `token_version`，改密/封禁后旧 token 仍有效 | 🟡 中 | 加列并在 `_load_user` 校验 |
| D2 | 审核员是否走"公共池 + 指派"混合模式 | ⚠️ 决策 | 选择并记录（见 ROLE_SESSION_ANALYSIS.md 4.3） |
| D3 | 是否新建 `post_audit_assignments` 记录改派历史 | ⚠️ 决策 | 选择并记录 |

---

## 附：本文的取证清单（**修复前**的行号，保留作为诊断依据）

> ⚠️ 下表是**下诊断时**的代码位置，修复后行号已变、部分代码已重写。
> 需要看**当前**实现请直接查 `constants.py` 的 `ROLE_PERMISSIONS`、
> `auth.py` 的 `admin_required`、`models/user.py` 的 `is_staff` / `is_admin`。

| 结论（修复前） | 当时的证据 | 现状 |
|---|---|---|
| `users` 表 20 列完整定义 | `models/user.py:31-47` + `models/base.py:20-24` | 现 25 列（+5 个移交字段） |
| 库结构与模型一致（无漂移） | `docs/schema_sqlite.sql:89-119` | 仍一致 |
| `is_admin` 语义混淆 | `models/user.py:72-75` | ✅ 已拆成 `is_staff` / `is_admin` |
| `ADMIN_ROLES` 含 6 个角色 | `constants.py:32-33` | ✅ 收敛为 2 个（`admin` / `auditor`） |
| 53 处 `@admin_required` 全为无参 | 全量扫描 `^@admin_required` | ✅ 64 个接口全部带 `capability` |
| `roles` 收窄能力已写但未用 | `auth.py:151-183` | 仍保留该参数（低优先，暂无调用） |
| 模块权限默认放行 | `auth.py:238-247` | ✅ 已收紧为"未授权即拒绝"（但装饰器仍零调用 → P8） |
| `admin_module_access` 零写入 | `models/system.py:121-137` | ❌ 仍未变（P8） |
| `allow_roles` 零校验 | `models/module.py:29`、`admin/modules.py:127-128` | ❌ 仍未变（P8） |
| 审核员发帖免审 | `posts_service.py:230` | ✅ 仅真管理员免审 |
| 审核员可编辑任意帖子 | `posts_service.py:73` | ✅ 仅真管理员可改他人正文 |
| 评论删除的隐藏管理员分支 | `comments/routes.py:328-339` | ✅ 已改为 `user.is_admin` |
| 前端 `isAdmin` 总来源 | `stores/user.js:24` | ✅ 已拆 `isAdmin` / `isTrueAdmin` / `can()` |
| 前端 9 处判定点 | 见旧版列表 | ✅ 全部改为能力驱动 |
| 无 `token_version` 字段 | `models/user.py` | ❌ 仍缺（P9） |
