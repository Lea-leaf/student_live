# 角色结构适配性分析 & 同机多账户会话链路分析

> **这份文档回答两个问题**：
> 1. 现有「用户底层结构」能否支撑 **管理员 / 普通用户 / 审核员** 三级角色，以及
>    「管理员指定审核员去审核普通用户的帖子」这条指派链路？
> 2. 同一台电脑上同时登录两个不同账户，其中一个退出登录时，会发生什么？
>
> **阅读前提**：本文结论均来自当前仓库代码（文件与行号已标注），不是设计意图的复述。
> 凡是「文档里说有、代码里没生效」的地方，本文会明确点出来 —— 这是本次分析的核心价值。

---

## 〇、结论速览

| 问题 | 结论 | 关键缺口 |
|---|---|---|
| 三种角色能否存得下 | ✅ **能，且不用改表** | `users.role` 是 `String(32)` + 无 CHECK/枚举约束，6 个角色常量与中文标签**已存在** |
| 三种角色能否**行为不同** | ~~❌ 不能~~ → ✅ **已修复（v1.4）** | 64 个后台接口已按能力归类；见 [AUDIT.md 修复记录 #3](AUDIT.md) |
| 「管理员指定审核员」的指派关系 | ~~❌ 无表承载~~ → ✅ **已实现（v1.4）** | `posts.assignee_id` + `post_audit_logs` 流水表 |
| 审核员只看得到派给自己的帖子 | ~~❌ 不支持~~ → ✅ **已支持** | 待审台支持 `scope=mine/pool`，被指派后 24 小时超时退回 |
| 同机登两个账户 | ⚠️ **同一浏览器只能有一个账户有效** | token 存 localStorage 固定键，第二个账户登录即覆盖第一个 |
| 一个账户退出对另一个的影响 | ⚠️ **全局登出** | 同一浏览器内另一个标签页会被连带登出（有延迟，最长 30 秒） |

> ⚠️ **本文写于修复前（审计 #2，2026-10-05）**，用于记录问题诊断过程。
> 前三条结论**已由 v1.4 修复**（角色权限、指派链路），
> 后两条属于**会话链路**，仍未处理 —— 见第四节 4.1 与 3.5 的整改清单。

**一句话**：**「角色」这一层是现成的，「权限」和「指派」这两层原本是空的**
（v1.4 已补齐，见 [AUDIT.md 修复记录 #3](AUDIT.md)）；
会话问题的根因是 token 放在 localStorage 而不是「按标签页隔离」的地方。

---

## 一、现状盘点：底层结构里已有什么

### 1.1 角色：常量、标签、字段三重就绪

`backend/app/utils/constants.py:11-33`

```python
ROLE_USER = 'user'
ROLE_ADMIN = 'admin'
# 预留：RBAC 多级管理员（参见需求文档「管理员分级思路」）
ROLE_SUPER_ADMIN = 'super_admin'
ROLE_AUDITOR = 'auditor'          # ← 审核员常量已存在
ROLE_USER_ADMIN = 'user_admin'
ROLE_MODULE_ADMIN = 'module_admin'
ROLE_MODERATOR = 'moderator'

ROLE_LABELS = {..., ROLE_AUDITOR: '内容审核员', ...}

#: 当前具备后台访问权限的角色集合（后续扩展只需改这里）
ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_AUDITOR,
               ROLE_USER_ADMIN, ROLE_MODULE_ADMIN, ROLE_MODERATOR)
```

| 层 | 现状 | 是否够用 |
|---|---|---|
| 数据库列 | `users.role VARCHAR(32) NOT NULL, index=True`（`models/user.py:33`） | ✅ 任意角色字符串都能存，**不用改表、不用迁移** |
| 角色字典 | `ROLE_LABELS` 含 6 个角色的中文名 | ✅ 前端下拉直接可用 |
| 对外暴露 | `GET /common/enums` 返回 `role` 列表（`modules/common/routes.py:34`） | ✅ 前端已通过 `appStore.enums.role` 渲染筛选器 |
| 改角色接口 | `POST /admin/users/<id>/role`（`admin/users.py:213`） | ✅ `if role not in ROLES` 校验，**现在就能把某人设成 `auditor`** |
| JWT | payload 里带 `role`（`utils/auth.py:58`） | ⚠️ 带了但**从没被读过**（见 2.1） |

> **重要**：`users.role` 是普通字符串列，没有数据库层枚举约束。
> 这意味着把 `auditor` 写进去**不会有任何数据库报错** —— 风险恰恰在这里：
> 写进去了，但系统行为完全不变，会出现「看板显示审核员、实际权限等于管理员」的静默错配。

### 1.2 审核链路：审核动作本身是完整可用的

现有的审核是**「谁有权限谁就能审」的无指派模式**，但动作、留痕、通知都已闭环：

| 环节 | 实现位置 | 说明 |
|---|---|---|
| 待审列表 | `GET /admin/posts/pending`（`admin/posts.py:108`） | 只支持 `?type=` 按模块过滤 |
| 审核动作 | `POST /admin/posts/<id>/audit`（`admin/posts.py:143`） | 通过 / 拒绝 + 审核意见 |
| 批量审核 | `POST /admin/posts/batch/audit`（`admin/posts.py:188`） | 勾选后批量通过 / 拒绝 |
| 审核人留痕 | `posts.audited_by` / `audited_at` / `audit_remark`（`models/post.py:49-51`） | 记录**最后一个**审核人 |
| 操作日志 | `write_operation_log('audit', module=post.type, target_type='post', ...)`（`admin/posts.py:179`） | 含操作人、IP、UA、时间，**这是审核台账的现成基础** |
| 通知作者 | `send(post.user_id, ..., notify_type='audit', ...)`（`admin/posts.py:181`） | 审核结果自动通知发帖人 |
| 前端审核台 | `frontend/src/views/admin/AuditView.vue` | 平铺列表 + 通过 / 拒绝 / 批量，**无「分配给我」概念** |

### 1.3 预留但**未接线**的设施（关键风险点）

仓库里存在三处「看起来支持 RBAC」的设施，**实际全部处于未生效状态**：

| 设施 | 位置 | 真实状态 |
|---|---|---|
| `admin_required(roles=(...))` 角色收窄参数 | `utils/auth.py:151-183` | 形参逻辑写好了，但**仓库里 60 处调用全是无参 `@admin_required`**（见 2.1 的扫描结果） |
| `module_permission_required(module_code, permission)` | `utils/auth.py:225-251` | 定义了，**零处调用**；且未授权时是**默认放行**（`g.module_scope=None` 而不是 403） |
| `admin_module_access` 表（管理员↔模块授权） | `models/system.py:121` | 已建表、已进 ER 图，**全仓库只有装饰器里的一次读，没有任何写入口** |
| `modules.allow_roles` 列（允许发布的角色） | `models/module.py:29` | `admin/modules.py:127` 能存，**没有任何地方读它做校验** |

> 这四项合起来是一个典型的「**骨架先行、肌肉没长**」状态：
> 表在、参数在、装饰器在，但**权限判定从未真正按角色分支过**。

---

## 二、适配性评估：三个需求逐条对照

### 2.1 需求 A：管理员 / 普通用户 / 审核员三种角色

**判定：⚠️ 一半适配 —— 存得下，但区分不开。**

**证据（后端）**：对 `backend/app` 全量扫描权限装饰器的结果 ——

````
admin_required            53 处，全部为无参调用
super_admin_required       2 处（角色调整 / 彻底删除用户）
module_permission_required 0 处
admin_required(roles=...)  0 处
````

而 `admin_required` 的判定核心只有一行（`utils/auth.py:175`）：

```python
if not user.is_admin:                 # ← 只判断「是不是后台角色」
    return error('需要管理员权限', CODE_FORBIDDEN, http_status=403)
if roles and user.role not in roles and user.role != ROLE_SUPER_ADMIN:
    ...                               # ← roles 永远是 None，这一行从不执行
```

`User.is_admin` 的定义（`models/user.py:72-75`）：

```python
@property
def is_admin(self):
    return self.role in ADMIN_ROLES   # auditor ∈ ADMIN_ROLES → 审核员 is_admin = True
```

**因此当前把某人设为 `auditor` 后，他能做的事**（与实际管理员**完全一致**）：

| 审核员当前可执行的接口 | 为什么这是问题 |
|---|---|
| `POST /admin/users/<id>/ban` 封禁用户 | 审核员不该有处置账号的权力 |
| `POST /admin/users/<id>/reset-password` 重置任意用户密码 | **严重**：可接管账号 |
| `GET /admin/users/<id>/logs` 看任意用户登录/操作日志 | 越权读取 |
| `POST /admin/modules` 新增 / 启停模块 | 越权改平台结构 |
| `PUT /admin/configs` 改系统配置（含审核开关 `post_audit_enabled`） | **严重**：审核员可把审核关掉 |
| `GET /admin/trash`、`DELETE /admin/trash/<id>`、`POST /admin/trash/batch/purge` 彻底删除数据 | 越权销毁数据 |
| `POST /admin/posts/<id>/status`、`/top`、`PUT /admin/posts/<id>` | 越权改他人内容 |

**证据（前端）**：

```js
// stores/user.js:24
isAdmin: (state) => !!(state.user && state.user.is_admin),

// router/index.js:214-216 —— 唯一的后台门禁
if (to.meta.requiresAdmin && !userStore.isAdmin) {
  return { name: 'home', query: { denied: 'admin' } }
}
```

前端拿到的 `is_admin` 就是后端 `to_dict()` 里的布尔值（`models/user.py:125`），
它同样是「∈ ADMIN_ROLES」——**前端也把审核员当管理员**，会直接渲染出
**完整的管理端菜单**（用户管理、模块管理、回收站、系统配置……）。

**结论**：三种角色在**数据层可以立刻建立**，但**权限层必须补**，否则建立角色等于没建立。

---

### 2.2 需求 B：管理员选定审核员，审核员审核普通用户的帖子

**判定：❌ 不适配 —— 缺「指派」这一整个概念。**

**缺口 1：没有任何字段/表记录「派给谁」**

| 需要的语义 | 现有承载 | 结论 |
|---|---|---|
| 这条帖子指派给哪个审核员 | 无 | ❌ 缺 `assignee_id` |
| 什么时候派的、谁派的 | 无 | ❌ |
| 指派历史（改派过几次） | 无 | ❌（可选） |
| 谁最终审的 | `posts.audited_by` | ⚠️ 只有最后一人的快照，不是指派关系 |
| 审核动作台账 | `operation_logs`（`action='audit'`） | ✅ 可复用，能查「某审核员审了多少条」 |

> **注意区分**：「谁审的」≠「派给谁」。
> 现在的 `audited_by` 是**事后**写的（审核那一刻落库），
> 而需求要的是**事前**的分配关系 —— 待审列表里得先有「这条归张三」。

**缺口 2：审核员的队列无法按人过滤**

`admin/posts.py:108-119` 的待审查询只接受 `type`：

```python
post_type = (request.args.get('type') or '').strip() or None
query = svc.pending_audit_query(post_type).order_by(Post.id.asc())
```

即使加了 `assignee_id`，还得同步改这里的查询条件，并给审核员**默认只看自己名下**的策略。

**缺口 3：没有「审核员不能审自己帖子」的约束**

`audit_post` 没有做 `post.user_id == operator.id` 的自审拦截。
如果审核员同时也是普通用户（能发帖），他可以直接通过自己的帖子。

**缺口 4：审核员能否发帖 / 评论，需求未定义**

`ADMIN_ROLES` 里的角色在业务侧**没有任何降级处理**：
审核员进前台照样能发帖、评论、私信。这需要明确决策（见 4.3 决策点）。

**结论**：这条链路需要**数据层 + 接口层 + 前端三处同时改**，属于真实功能开发，不是配置开关。

---

### 2.3 结构改动量评估

好消息：**改动集中在「加少量列 + 收紧判定」，不需要重构表结构。**

| 改动项 | 类型 | 成本 | 备注 |
|---|---|---|---|
| `users.role` 存 `auditor` | 无需改表 | 0 | 已是 `String(32)` |
| 角色授权判定（`ROLE_PERMISSIONS` 映射） | 纯代码 | 小 | 集中在 `constants.py` + `auth.py` |
| `@admin_required` 收窄为按角色 | 纯代码 | 中 | 53 处调用需逐个归类到「哪个角色能调」 |
| 管理端菜单按角色渲染 | 前端 | 小 | `AdminLayout` 菜单项加 `roles` 字段 |
| 前端 `isAdmin` 语义拆分 | 前端 | 小 | 需拆出 `isAuditor` / `canAudit` |
| `posts.assignee_id`（+ 索引） | **加列** | 小 | 走 `scripts/upgrade_schema.py`（幂等、只加不删） |
| 指派接口 + 待审列表过滤 | 纯代码 | 中 | 新增 `POST /admin/posts/<id>/assign` |
| 改派历史（可选） | 加表 | 中 | `post_audit_assignments`，答辩加分项 |
| 前端「分配审核人」交互 | 前端 | 中 | 审核台 + 帖子列表批量分配 |

---

## 三、同机多账户会话链路分析

### 3.1 存储事实：token 存在哪里

```js
// frontend/src/api/request.js:11-12, 30-42
export const TOKEN_KEY = 'slp_access_token'
export const REFRESH_KEY = 'slp_refresh_token'

getToken()        { return localStorage.getItem(TOKEN_KEY) || '' }
setToken(a, r)    { localStorage.setItem(TOKEN_KEY, a); localStorage.setItem(REFRESH_KEY, r) }
clearToken()      { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY) }
```

三个必须同时成立的事实：

| 事实 | 含义 |
|---|---|
| 用的是 **`localStorage`**，键名**固定**（不区分账户、不区分标签页） | 同一浏览器 + 同一 origin（`127.0.0.1:5173`）**只有一份 token 槽位** |
| 用的是 **`localStorage`** 而不是 `sessionStorage` | 标签页之间**共享**，且**关掉浏览器仍然保留** |
| Pinia store 与 axios 实例是**每标签页独立**的 JS 运行时 | 但 `getToken()` **每次请求都重新读 localStorage**（`request.js:71`） |

> 最后一条是关键：**内存里的「我是谁」和请求头里的「我是谁」是两套东西**，
> 前者每标签页一份，后者全局共享 —— 这就是所有诡异现象的来源。

### 3.2 登出链路：本地行为 + 一行服务端日志

```js
// stores/user.js:83-95
async logout() {
  try {
    if (getToken()) await authApi.logout()   // 只为写日志，不使 token 失效
  } catch (e) { /* 忽略 */ }
  finally {
    clearToken()      // ← 删 localStorage 里那两个键（全局生效）
    this.user = null  // ← 只清当前标签页的内存状态
    this.initialized = true
  }
}
```

```python
# modules/auth/routes.py:229-238
@bp.post('/logout')
@token_required
def logout():
    """原型阶段由前端删除本地 token；这里预留服务端失效逻辑
    （接入 Redis 黑名单时，把当前 token 的 jti 写入黑名单即可）。"""
    write_operation_log('logout', module='auth', target_type='user', target_id=g.current_user.id)
    return success({'msg': '已登出'})
```

**服务端没有任何失效动作** —— 这是一次**纯客户端登出**：

- 没有 token 黑名单，没有 `token_version`，没有服务端会话表；
- access token 有效期 **24 小时**（`config.py:62`），refresh token 7 天；
- ⇒ **被清掉的那串 token 在 24 小时内依然是合法凭证**（只要它还在别处存在）。
- logout 唯一的价值是：`operation_logs` 里留了一条「谁在什么 IP/UA 下登出」的记录。

### 3.3 四种情形推演

设：**A 账户**已在标签页 1 登录并正常使用；随后在**标签页 2** 登录 **B 账户**。

#### 情形 1 —— 同一浏览器、两个普通标签页（最常见的误操作）

| 时刻 | localStorage | 标签页 1（页面显示 A） | 标签页 2（B） |
|---|---|---|---|
| B 在标签页 2 登录 | 被**覆盖**为 B 的 token | 内存里还是 A 的用户对象 | 显示 B |
| 标签页 1 任意请求 | — | 请求头带的是 **B 的 token** → **以 B 的身份操作** | — |
| 刷新标签页 1 | — | `fetchMe()` 读到的也是 B → **页面变成 B** | — |

⚠️ **这是最容易踩的坑**：用户以为「标签页 1 还是 A」，
但那个页面**后续所有操作（发帖、评论、私信、点赞）都记在 B 名下**。
界面上的头像/昵称（来自内存）与真实的请求身份（来自 localStorage）**不一致**。

> **结论：同一浏览器内，两个账户无法同时有效，只有「后登录者生效」。**

#### 情形 2 —— 情形 1 之下，A 在标签页 1 点「退出登录」

沿用上面的状态（localStorage 里是 B 的 token，A 已实际下线）：

```
标签页 1 点登出 → userStore.logout()
  ├─ authApi.logout()  →  请求头带 B 的 token
  │                       ⇒ 后端记录「B 登出」到 operation_logs
  │                       ⇒ B 的会话日志被写脏（把 A 的登出算在 B 头上）
  ├─ clearToken()      →  删掉 B 的 token（全局）
  └─ this.user = null  →  标签页 1 变未登录
                          ↓
标签页 2（显示 B）下一次请求（最长 30 秒后，见下）
  → 没有 Authorization 头 → 后端返回 body.code = 2001（未登录）
  → 响应拦截器 clearToken() + ElMessage 警告 + 跳登录页
  → 标签页 2 被连带登出
```

📌 **两个可观察的副作用**：
1. **审计日志归属错乱**：A 的登出动作被记成 B 的操作；
2. **B 被连带登出**：B 并非自己操作登出，而是被动失效，且**跳转前没有任何解释**
   （如果 B 正在编辑帖子的表单里，页面直接被路由切走，**未保存内容丢失**）。

#### 情形 3 —— 真正的双账户并行（必须做浏览器级隔离）

| 隔离方式 | 能否同时有效 | 一个登出是否影响另一个 |
|---|---|---|
| 普通标签页 + 普通标签页 | ❌ 只有一个有效 | ✅ 会连带（见情形 2） |
| **普通窗口 + 无痕窗口** | ✅ 可以 | ✅ **互不影响**（存储上下文独立） |
| **Chrome + Edge**（两个浏览器） | ✅ 可以 | ✅ **互不影响** |

> README 的 FAQ 里已经建议「功能测试用无痕窗口」，这条建议**恰好也是多账户并行的正确姿势** ——
> 值得在文档里把因果关系写清楚（不只是「控制台干净」，而是**会话就应该是隔离的**）。

#### 情形 4 —— 同一账户开两个标签页，其中一个登出

两个标签页共享同一个 token，登出后另一个标签页同样在**下次请求**时（或最长 30 秒后）失效。
表现与情形 2 相同，但**没有身份错乱问题**（本来就是同一个人）。

### 3.4 「最长 30 秒延迟」从哪来

```js
// layouts/UserLayout.vue:35-42  —— 登录后启动轮询
onMounted(() => {
  if (userStore.isLogin) {
    notificationStore.startPolling()   // stores/notification.js:63 → setInterval 30000
    messageStore.startPolling()
  }
})
```

未读通知 / 私信每 **30 秒**轮询一次。因此另一个标签页**不是立刻**发现 token 消失，
而是要等下一个轮询请求返回「未登录（code 2001）」—— 这期间它仍以「已登录」的外观渲染。

### 3.5 附带发现（同一链路上的既有缺陷）

| 编号 | 发现 | 影响 | 建议 |
|---|---|---|---|
| S1 | **被动登出会丢当前页面** | 拦截器里 `goLogin()` 用 `router.replace()` 直接跳登录页，没有任何保存草稿的钩子；发布页写了一半的内容会被直接切走 | 发布页加 `onBeforeRouteLeave` 草稿提示，或跳转前先落草稿到本地 |
| S2 | **`/auth/refresh` 是死代码** | 前端**从未调用** refresh，`slp_refresh_token` 存了也没用；24 小时后 access token 过期只能重新登录 | 在拦截器里对 2002（过期）做一次静默刷新再重试，refresh 接口已就绪 |
| S3 | **登出后 token 24 小时内仍有效** | 无黑名单 / 无 token 版本；token 一旦泄露，登出无法止损 | 加 `users.token_version` 列，JWT 里带上并在 `_load_user` 校验；或接 Redis 黑名单（注释里已留好位置） |
| S4 | **改密码 / 重置密码不失效旧 token** | 管理员重置密码后，旧 token 仍能用 —— 与「重置密码」的安全预期不符 | 与 S3 用同一套 `token_version` 机制，改密码时 +1 |
| S5 | **轮询定时器是模块级单例** | `stores/notification.js` 的 `timer` 在模块作用域，多布局切换靠 `stopPolling` 收口，容易漏 | 定时器移入 store state，`onUnmounted` 用 store action 收口 |

---

## 四、整改建议（按优先级）

### 4.1 会话链路（改动小、收益立竿见影，建议先做）

| 优先级 | 措施 | 工作量 | 效果 |
|---|---|---|---|
| **P0** | 监听 `window.addEventListener('storage', ...)`：检测到 token 键被别的标签页改/删时，本标签页 `clearToken()` + 清 store + 跳登录页并提示「账号已在其他标签页退出」 | 小 | 消灭「界面显示 A、实际操作 B」的身份错乱（情形 1、2） |
| **P0** | 后端 logout 日志**带上前端传的实际操作者提示**，或在登出前先校验 token 的 `uid` 与内存用户一致（不一致则不调 logout 接口，只清本地） | 小 | 修掉「A 的登出记在 B 头上」的日志脏数据 |
| **P1** | 把 token 存到 **`sessionStorage`**，实现按标签页隔离 | 中 | 真正支持「同机双账户并行」；代价：新开标签页需重新登录（可接受，且更安全） |
| **P2** | 加 `token_version`（改密码 / 封禁 / 强制下线时 +1，JWT 携带并在 `_load_user` 校验） | 中 | 服务端可撤销，补上 S3 / S4 |
| **P2** | 前端接上 `/auth/refresh` 静默续期（S2） | 小 | 24 小时过期不再打断用户；refresh + `token_version` 组合是最佳实践 |

> ⚠️ 若采用 P1（`sessionStorage`），**必须同时做 P0 的 `storage` 监听**吗？不必 ——
> 两者是**替代关系**：`sessionStorage` 天然按标签页隔离，多账户并行时**不存在互相覆盖**，
> 也就不会有连带登出。可以二选一，**推荐 P1 为终态、P0 为过渡**。
> 但注意 F5 刷新不丢、**关标签页即失效**，这对「共用电脑」场景反而是优点。

### 4.2 角色与指派（功能开发，建议排期）

**第 1 步 · 让角色真正生效（后端）**

```python
# utils/constants.py 新增：角色 → 允许的后台能力
ROLE_PERMISSIONS = {
    ROLE_SUPER_ADMIN: {'*'},
    ROLE_ADMIN:       {'post.audit', 'post.manage', 'user.manage', 'module.manage',
                       'config.manage', 'log.view', 'trash.manage', 'report.handle'},
    ROLE_AUDITOR:     {'post.audit.view', 'post.audit.do'},   # ← 只给审核
    ...
}
```

```python
# utils/auth.py：把已有的 roles 参数用起来
@admin_required(roles=(ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_AUDITOR))   # 审核相关
@admin_required(roles=(ROLE_ADMIN, ROLE_SUPER_ADMIN))                 # 用户/配置/模块
```

对应到 53 处调用做一次归类即可，**不需要改表**。

**第 2 步 · 加「指派」关系（后端加列 + 接口）**

```python
# models/post.py 新增（走 scripts/upgrade_schema.py 幂等升级）
assignee_id = db.Column(db.Integer, nullable=True, index=True, comment='指派审核员')
assigned_by = db.Column(db.Integer, nullable=True, comment='指派人')
assigned_at = db.Column(db.DateTime, nullable=True, comment='指派时间')
```

```python
POST /admin/posts/<id>/assign      {"assignee_id": 7}      # 指派 / 改派（传 null 取消）
POST /admin/posts/batch/assign     {"post_ids": [...], "assignee_id": 7}
GET  /admin/posts/pending?assignee=me|7|unassigned          # 待审列表支持审核人维度
```

审核员策略建议：**默认只看自己名下的**，同时保留「公共池」（`assignee_id IS NULL`）可自助认领，
避免审核员下线导致帖子卡死。

**第 3 步 · 审核约束（后端）**

- 审核员只能审 `assignee_id == 自己` 或公共池的帖子，否则 403；
- **禁止自审**：`post.user_id == operator.id` 直接拒绝（无论什么角色）；
- 审核员**不能**调 `/admin/posts/<id>/status`、`/top`、`PUT`、`DELETE`（这些是管理员动作）；
- 审核员**不能**调 `/admin/configs`，尤其是 `post_audit_enabled`。

**第 4 步 · 前端（小改）**

| 位置 | 改动 |
|---|---|
| `stores/user.js` | 把 `isAdmin` 拆成 `isAdmin` / `isAuditor` / `canAudit`；后端建议在 `to_dict()` 里直接下发 `permissions: [...]` 数组，前端只做展示、**不做安全判定** |
| `router/index.js` | `meta.requiresAdmin` 增加 `meta.roles: ['admin','auditor']` 维度；审核员访问 `/admin/users` 应被挡回 |
| `AdminLayout.vue` | 菜单项加 `roles` 过滤：审核员只看到「审核工作台」（+ 可选「概览」） |
| `AuditView.vue` | 顶部加「审核人筛选 / 只看我的」；管理员额外显示「分配」按钮与审核人列 |
| `PostManageView.vue` | 支持多选 → 批量分配审核员 |

> **安全原则**：前端菜单过滤只是**体验**，真正的门禁必须在后端装饰器。
> 当前代码恰好相反 —— 前端是门禁（`isAdmin`），后端是全开（`ADMIN_ROLES` 一视同仁）。

### 4.3 需要你确认的 4 个决策点

| 编号 | 决策点 | 选项 | 我的建议 |
|---|---|---|---|
| **D1** | 三种角色是**互斥身份**还是**能力叠加**？ | A. 互斥：审核员没有普通用户身份，不能发帖<br>B. 叠加：审核员也是普通用户，能发帖/评论 | **B（叠加）**，符合高校实际（老师/助管也要用平台），但**必须配套「禁止自审」** |
| **D2** | 审核员只审**被指派**的，还是也能审**公共池**？ | A. 严格：只能审指派给自己的<br>B. 混合：指派优先 + 公共池自助认领 | **B**，避免审核员请假导致队列堵死 |
| **D3** | 是否需要**改派历史 / 审核工作量统计**？ | A. 不做，只留当前指派（3 列即可）<br>B. 做 `post_audit_assignments` 表，可统计「每人审了多少、平均耗时」 | **B 作为答辩加分项**：工作量统计对学生审核员是刚需，且能直接复用 `operation_logs` |
| **D4** | 会话方案选哪个？ | A. `storage` 事件同步（改动最小，语义仍是「同浏览器单账户」）<br>B. `sessionStorage` 按标签页隔离（真正支持双账户）<br>C. 再加 `token_version` | **A 先做（P0 止血），B/C 作为 v2.0 一并做**（v2.0 本来就规划了「多级管理员（RBAC 生效）」） |

---

## 五、给答辩的表达建议

> ⚠️ 本节最早写于修复前（当时 auditor 与 admin 权限等价，答法会误导）。
> 下面的内容**已全部更新为当前口径**，可直接照着说。

| 老师可能问 | 建议回答 |
|---|---|
| 「你们支持多级管理员吗？」 | 答：**已落地三层** —— `user` / `auditor`（内容审核员）/ `admin`（管理员，最高级）。权限用**「角色 → 能力集合」**（`ROLE_PERMISSIONS`）表达，64 个后台接口逐个用 `@admin_required(capability=...)` 声明所需能力；前端菜单与按钮由后端下发的 `capabilities` 驱动，**门禁始终在后端**。关键设计点：`is_staff`（能不能进后台）与 `is_admin`（是不是管理员）**是两个语义** —— 早期混为一谈，导致审核员一建出来就等于管理员。 |
| 「接口那么多，怎么保证不漏权限？」 | 答：**管理员持通配能力 `*`**，新增能力自动覆盖；受限角色显式列举。并且有一条回归测试扫描全仓库，断言**预留装饰器零调用**，防止"以为接线了实际没有"。 |
| 「为什么系统只允许一个管理员？换人怎么办？」 | 答：多个管理员会互相封号 / 降级，责任不清。换人走**两阶段移交**：指定接任者后对方获得管理员身份但 24 小时内**按原身份工作**（原本是审核员就继续审核，工作不停），只是拿不到管理员特权、发帖仍需审核；期间原管理员随时可撤销；到期才正式交接。时间以**北京时间**为准，前端倒计时用服务器返回的时间校准。 |
| 「为什么审核要指派而不是谁都能审？」 | 三个理由：**责任可追溯**（`assignee_id` + 审核流水表，出问题能定位到人）；**工作量可统计**（避免有人审一大堆、有人一条不审）；**避免利益冲突**（禁止自审，管理员也不例外）。认领用**数据库原子条件更新**实现先到先得，并发下第二个提交者会收到明确提示。 |
| 「同一台电脑登两个账号会怎样？」 | ⚠️ **这一项当前仍未修复**，诚实回答：token 存 localStorage 固定键，所以**同浏览器只能有一个账户有效，且一个登出会连带另一个**（最长 30 秒后才感知）。这不是 bug，而是"全局单会话"的实现选择。规避方式：**无痕窗口**或换浏览器。终态方案（`sessionStorage` 按标签页隔离 + `token_version`）见本文 4.1 节。**这个问题答好了是加分项** —— 它证明你理解「认证状态存在哪」这个本质。 |
| 「登出后 token 还有效吗？」 | 诚实回答：**仍有效至过期（24 小时）**，因为是无状态 JWT + 没有黑名单（代码注释里已预留位置）。给出 `token_version` 方案（见 P9）。 |
| 「有没有还没做的？」 | 主动列清单，比被问出来好：**模块级分权未启用**（P8）、**token 无法撤销**（P9）、**会话链路 5 项**（S1~S5）。每项都能说清"为什么先不做"与"怎么补"。见 README 第十节。 |

---

## 附：本次分析的代码取证清单

| 结论 | 证据文件 | 关键行 |
|---|---|---|
| 角色常量与标签已存在 | `backend/app/utils/constants.py` | 11-33 |
| `role` 列可存任意角色 | `backend/app/models/user.py` | 33 |
| 审核员被判为管理员 | `backend/app/models/user.py` | 72-75 |
| `@admin_required` 不区分角色 | `backend/app/utils/auth.py` | 151-183 |
| `roles` 参数从未被使用 | `backend/app/utils/auth.py` | 175-178（`roles` 恒为 `None`） |
| 模块级权限默认放行 | `backend/app/utils/auth.py` | 225-251 |
| 审核动作与留痕 | `backend/app/admin/posts.py` | 143-186 |
| 待审列表只按模块过滤 | `backend/app/admin/posts.py` | 108-119 |
| 无指派字段 | `backend/app/models/post.py` | 47-51（只有 `audited_by`） |
| 前端门禁基于 `is_admin` | `frontend/src/router/index.js` | 214-216 |
| 前端 `isAdmin` 来源 | `frontend/src/stores/user.js` | 24 |
| token 存 localStorage 固定键 | `frontend/src/api/request.js` | 11-12, 30-42 |
| 每次请求重新读 token | `frontend/src/api/request.js` | 68-78 |
| 认证失败（2001 / 2002 / 401）清 token 并跳登录 | `frontend/src/api/request.js` | 114-128, 155-157 |
| 登出只清本地 | `frontend/src/stores/user.js` | 83-95 |
| 后端登出不失效 token | `backend/app/modules/auth/routes.py` | 229-238 |
| token 有效期 24 小时 | `backend/app/config.py` | 62 |
| 30 秒轮询 | `frontend/src/layouts/UserLayout.vue` / `stores/notification.js` | 35-42 / 63-67 |
| `/auth/refresh` 未被前端调用 | `frontend/src/api/auth.js` vs 全局搜索 | 无调用点 |
