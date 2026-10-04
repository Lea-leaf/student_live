# 校园生活平台 · API 接口文档    



- **统一前缀**：`/api/v1`
- **数据格式**：`application/json`（上传接口为 `multipart/form-data`）
- **认证方式**：`Authorization: Bearer <access_token>`
- **开发地址**：`http://127.0.0.1:5000`；前端通过 Vite 代理 `http://127.0.0.1:5173/api` 访问

---


## 一、统一响应结构

所有接口（含错误）都返回同一结构：

```json
{
  "code": 0,
  "msg": "success",
  "data": {}
}
```

| 字段 | 说明 |
|---|---|
| `code` | `0` 表示成功，非 0 为业务错误码（见附录 A） |
| `msg` | 提示文案，可直接展示给用户 |
| `data` | 业务数据，可能是对象、数组或 `{}` |

分页接口的 `data` 固定为：

```json
{
  "list": [],
  "total": 100,
  "page": 1,
  "size": 10,
  "pages": 10
}
```

分页请求参数：`?page=1&size=10`；`size` 上限由系统配置 `page_max_size`（默认 100）控制。

**HTTP 状态码策略**：业务错误默认返回 `200` 便于前端统一处理；认证失败返回 `401`、无权限返回 `403`、未实现功能返回 `501`、服务端异常返回 `500`。

---

## 二、认证模块 `/api/v1/auth`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/auth/captcha` | 游客 | 获取图形验证码，返回 `{captcha_id, image(data URI), svg, expires_in, debug_code}`；`debug_code` 仅开发环境返回 |
| POST | `/auth/register` | 游客 | 学号 + 验证码注册 |
| POST | `/auth/login` | 游客 | 登录，返回 `user` + `access_token` + `refresh_token` |
| POST | `/auth/refresh` | 游客 | 用 `refresh_token` 换新 token |
| POST | `/auth/logout` | 登录 | 登出（原型阶段由前端清 token，预留服务端黑名单） |
| GET | `/auth/me` | 登录 | 当前用户信息（含未读通知数、安全公告开关） |
| PUT | `/auth/me` | 登录 | 修改昵称 / 头像 / 邮箱 |
| PUT | `/auth/password` | 登录 | 修改密码（需原密码） |
| GET | `/auth/security-notice` | 游客 | 安全公告文案 |

**注册请求体**

```json
{
  "student_id": "20210001",
  "password": "123456",
  "confirm_password": "123456",
  "nickname": "小明",
  "captcha_id": "0f7c...",
  "captcha": "A3F9"
}
```

> 说明：注册是否需要验证码由系统配置 `register_captcha_enabled` 控制；关闭时可不传 `captcha_id` / `captcha`。

**登录响应**

```json
{
  "code": 0,
  "msg": "登录成功",
  "data": {
    "user": { "id": 2, "student_id": "20210001", "nickname": "小明", "role": "user", "is_admin": false },
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "Bearer",
    "expires_in": 86400
  }
}
```

---

## 三、公共接口 `/api/v1/common`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/common/enums` | 游客 | 全部字典（业务状态 / 审核状态 / 举报状态 / 用户状态 / 角色） |
| GET | `/common/modules` | 游客 | 启用中的模块列表（前端导航与筛选器） |
| GET | `/common/configs` | 游客 | 公开配置（站点名、公告、审核开关、上传限制、游客权限） |
| GET | `/common/health` | 游客 | 健康检查（含数据库连通性） |
| POST | `/common/upload` | 登录 | 通用上传，表单字段 `files`（可多文件） |
| GET | `/api/v1/files/<path>` | 游客 | 访问已上传的图片/视频 |

---

## 四、帖子模块 `/api/v1/lost_found`（默认失物招领，也支持 `type=second_hand`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/lost_found/posts` | 游客可浏览¹ | 列表：分页、搜索、筛选、排序 |
| GET | `/lost_found/posts/{id}` | 登录² | 详情；仅「进行中」可查看 |
| POST | `/lost_found/posts` | 登录 | 发布（支持 JSON 或 multipart） |
| POST | `/lost_found/posts/upload` | 登录 | 单独上传图片/视频 |
| PUT | `/lost_found/posts/{id}` | 作者/管理员 | 编辑（作者编辑后重新进入待审核） |
| DELETE | `/lost_found/posts/{id}` | 作者/管理员 | 删除（软删除 → 回收站） |
| GET | `/lost_found/my/posts` | 登录 | 我的发布：默认返回全部模块，可用 `?type=` 过滤；含全部状态 |
| POST | `/lost_found/posts/{id}/status` | 作者/管理员 | 状态流转 |
| POST | `/lost_found/posts/{id}/claim` | 作者/管理员 | 标记已认领（等价 `status=claimed`） |
| GET | `/lost_found/meta?type=second_hand` | 游客 | 模块元信息（字段要求、状态字典、是否需审核；二手交易会额外返回价格等 ext 字段） |

¹ 游客可浏览列表由系统配置 `guest_can_list` 控制（默认开）。
² 游客可看详情由 `guest_can_detail` 控制（默认关）。

**列表查询参数**

| 参数 | 说明 |
|---|---|
| `page` / `size` | 分页 |
| `keyword` | 标题 / 描述 / 地点模糊搜索 |
| `status` | `ongoing` / `claimed` / `expired` / `closed` |
| `mine=1` | 只看我的发布（需登录，含待审核与已关闭） |
| `all=1` | 管理员查看全部（含待审核） |
| `sort` | `latest`（默认）/ `hot` / `oldest`；`hot` = 浏览*1 + 评论*3 + 点赞*2 + 收藏*2，再按 24 小时时间衰减 |
| `type` | 模块 code，默认 `lost_found`；已实现 `second_hand`（二手交易），必须是启用中的模块 |

**发布请求体（JSON 方式）**

```json
{
  "type": "second_hand",
  "title": "出九成新自行车",
  "content": "骑了半年，刹车刚保养过",
  "contact": "微信 secondhand",
  "media": [{ "id": 3, "url": "/api/v1/files/20210001/20260301/xxx.jpg", "type": "image", "name": "车.jpg" }],
  "ext": { "price": 260, "original_price": 480, "condition": "九成新", "trade_type": "面交" }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `contact` | **是** | 联系方式，公开可见 |
| `type` | 否 | 模块 code，默认 `lost_found`；`second_hand` 表示二手交易 |
| `ext` | 视模块 | 模块扩展 JSON；二手交易必填 `price`，可选 `original_price` / `condition` / `trade_type` |
| `title` / `content` / `location` / `happened_at` / `media` | 否 | 选填 |

> `ext` 必须是 JSON 对象、最大 4096 字节；二手交易缺 `price` 或价格非法会返回 `1001`。
> 二手交易列表 / 详情 / 卡片都会返回 `ext`，前端按 `type` 渲染价格、成色与交易方式。

**multipart 方式**：字段名同上，文件字段名为 `files`（可多文件），媒体随表单一起提交。

**状态流转规则**

| 当前状态 | 允许变更为 |
|---|---|
| `ongoing` 进行中 | `claimed` / `closed` / `expired` |
| `claimed` 已认领 | `closed` / `ongoing` |
| `expired` 已过期 | `ongoing` / `closed` |
| `closed` 已关闭 | `ongoing` |

**状态可见性规则（需求 6.2）**

| 状态 | 公开列表可见 | 详情可查看 |
|---|---|---|
| 进行中 | ✅ | ✅ |
| 已认领 | ✅ | ❌（作者与管理员除外） |
| 已过期 | ✅ | ❌（作者与管理员除外） |
| 已关闭 | ❌ | ❌（作者与管理员除外） |

> **模块差异（second_hand）**：状态值仍是 `ongoing / claimed / expired / closed`，
> 但显示文案分别为 `在售中 / 已售出 / 已过期 / 已下架`；
> `happened_at` 是必填字段（交易时间）；发布页会在前端提供模块选择器。

> **前端统一发布入口**：所有发布按钮都跳 `/publish`，类型由页面内「选择发布类型」决定，
> 不通过 URL 的 `?type=` 传参；模块字段配置在前端 `src/config/moduleForms.js`，
> 未登记模块自动走 `default`。切换模块时通用字段保留，时间与专属字段清空且不恢复。

**媒体文件存放规则**

| 项 | 值 |
|---|---|
| 磁盘路径 | `backend/uploads/<学号>/<YYYYMMDD>/<uuid>.<ext>` |
| 数据库记录 | `upload_files.path` = 相对路径，`url` = `/api/v1/files/<相对路径>` |
| 命名规则 | 一级按上传者学号（便于按用户管理数据），二级按日期 |
| 删除联动 | 彻底删除帖子 / 删除用户时，磁盘文件一并删除 |

**上传限制（可在后台配置）**

| 项 | 默认值 | 配置键 |
|---|---|---|
| 允许后缀 | `jpg,jpeg,png,gif,webp,mp4,mov` | `upload_allowed_ext` |
| 图片上限 | 10MB | `upload_max_mb_image` |
| 视频上限 | 50MB | `upload_max_mb_video` |

---

## 五、互动模块

### 5.1 收藏 `/api/v1/favorites`（v1.0 可用）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/favorites` | 登录 | 我的收藏列表（分页） |
| POST | `/favorites/posts/{id}` | 登录 | 收藏 / 取消收藏（幂等切换） |
| GET | `/favorites/check/{id}` | 登录 | 是否已收藏 |

### 5.2 举报 `/api/v1/reports`（v1.0 可用）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/reports` | 登录 | 提交举报：`{post_id}` 或 `{target_user_id}` + `reason` + `detail` |
| GET | `/reports/my` | 登录 | 我的举报记录 |

### 5.3 通知 `/api/v1/notifications`（v1.0 可用）

`type` 取值：`audit` 审核 / `comment` 评论回复 / `message` 私信 /
`like` 点赞 / `mention` 被 @ / `system` 系统公告。
v1.2 起评论、回复、@、点赞、私信都会写入通知中心。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/notifications` | 登录 | 列表：`is_read=0/1`、`type`、分页 |
| GET | `/notifications/unread-count` | 登录 | 未读数量（前端小红点） |
| POST | `/notifications/read/{id}` | 登录 | 标记单条已读 |
| POST | `/notifications/read-all` | 登录 | 全部已读 |
| DELETE | `/notifications/{id}` | 登录 | 删除通知 |

### 5.4 评论 `/api/v1/comments`（v1.2 可用）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/comments/posts/{id}/comments` | 可选登录 | 顶级评论分页；每条评论带 `replies` 整棵楼中楼子树；返回 `liked`、`total_all` |
| POST | `/comments/posts/{id}/comments` | 登录 | 发表评论 / 回复，支持 JSON 与 `multipart/form-data`（字段 `files`） |
| DELETE | `/comments/{id}` | 登录 | 用户撤回自己 5 分钟内的评论（物理删除）；管理员删除任意评论（物理删除，含子回复、点赞、媒体、互动通知） |

POST 请求体：

```json
{
  "content": "同意楼上，我也在图书馆见过",
  "parent_id": 12,
  "reply_to_user_id": 8,
  "media": [
    { "id": 3, "url": "/api/v1/files/20210001/20261003/a.png",
      "path": "20210001/20261003/a.png", "name": "现场.png",
      "type": "image", "size": 10240, "mime": "image/png" }
  ]
}
```

- `parent_id` 留空表示顶级评论；回复时后端自动计算 `root_id`，并将 `reply_to_user_id` 默认设为父评论作者；
- `media` 建议先调 `POST /common/upload` 上传拿到结构；也支持 multipart 直接带 `files`；
- 评论通知：帖子作者、被回复者、正文中 `@昵称/学号` 的用户都会收到对应通知，自己操作自己不通知；
- 删除规则（v1.2 起）：用户不再有软删除，只能撤回自己 5 分钟内的评论（物理删除）；
  管理员删除任意评论也是物理删除，并在操作日志里保留评论内容等数据库信息快照。

### 5.5 点赞 `/api/v1/likes`（v1.2 可用）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/likes/posts/{id}` | 登录 | 帖子点赞 / 取消（幂等切换），返回 `{liked, like_count}` |
| GET | `/likes/posts/{id}` | 登录 | 查询当前用户是否已点赞该帖子 |
| POST | `/likes/comments/{id}` | 登录 | 评论点赞 / 取消，返回 `{liked, like_count}` |
| GET | `/likes/comments/{id}` | 登录 | 查询当前用户是否已点赞该评论 |

> 点赞与收藏是独立功能：`posts.like_count` / `comments.like_count` 只随点赞变化，
> `posts.favorite_count` 只随收藏变化。点赞成功会通知内容作者。

### 5.6 私信 `/api/v1/messages`（v1.2 可用）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/messages/conversations` | 登录 | 会话列表（对方信息、最后一条消息、会话未读数） |
| GET | `/messages/with/{user_id}` | 登录 | 与某人的消息记录（分页）；**拉取即把对方发来的未读标记为已读**，返回 `user`、`read_count` |
| POST | `/messages/with/{user_id}` | 登录 | 发送私信；`content` / `media` / `msg_type` / `post_id`，支持 multipart `files` |
| POST | `/messages/{message_id}/recall` | 登录 | 撤回自己发送的消息：**仅发送方、5 分钟内、数据库物理删除**，媒体与通知一并清理 |
| DELETE | `/messages/{message_id}` | 登录 | 普通删除：单侧隐藏（`sender_deleted` / `receiver_deleted`）；双方都删除后自动物理清理 |
| POST | `/messages/read/{message_id}` | 登录 | 单条已读回执（仅接收方） |
| POST | `/messages/read-all` | 登录 | 全部已读 |
| GET | `/messages/unread-count` | 登录 | 未读红点：`{unread, unread_conversations}` |

> 发送成功后接收方会收到 `message` 类型站内通知；发送方在会话里能看到每条消息的「已读 / 未读」。
> 实时化预留：表结构已按 `conversation_key` 设计，后续可平滑升级 WebSocket。


---

## 六、管理端 `/api/v1/admin`（全部需要管理员权限）

### 6.1 首页统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/dashboard/overview` | 用户总数、帖子总数、今日新增、待审核、回收站、待处理举报、今日登录 |
| GET | `/admin/dashboard/trend?days=7` | 近 N 天发帖 / 注册趋势 |
| GET | `/admin/dashboard/module-stats` | 各模块帖子数量分布 |
| GET | `/admin/dashboard/pending?limit=10` | 最近待审核帖子 |
| GET | `/admin/dashboard/media` | 媒体存储用量：按用户列磁盘占用 + 孤儿文件 + 未提交上传清单 |
| POST | `/admin/dashboard/media/clean` | 清理未引用媒体：未提交上传（默认保留 24 小时）+ 磁盘孤儿文件 |

### 6.2 用户管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/users` | 列表：`keyword` / `role` / `status` / `order` / 分页 |
| GET | `/admin/users/{id}` | 详情 + 发帖统计 |
| GET | `/admin/users/{id}/posts` | 发帖记录（含软删除） |
| GET | `/admin/users/{id}/logs` | 该用户的登录日志与操作日志 |
| GET | `/admin/users/{id}/media` | 该用户的媒体清单 + 磁盘占用（删除前确认用） |
| POST | `/admin/users/{id}/ban` | 封禁：`{reason}` |
| POST | `/admin/users/{id}/unban` | 解封 |
| POST | `/admin/users/{id}/reset-password` | 重置密码：`{new_password}`，留空则重置为 `123456` |
| POST | `/admin/users/{id}/role` | 调整角色（超级管理员）：`{role}` |
| POST | `/admin/users/{id}/remark` | 管理员备注 |
| POST | `/admin/users` | 管理员创建账号（可指定角色） |
| POST | `/admin/users/batch/ban` | 批量封禁：`{user_ids, reason}` |
| DELETE | `/admin/users/{id}` | **彻底删除用户**（不可恢复）：`{confirm_student_id}` 二次确认；仅超级管理员。级联清理其帖子/评论/收藏/私信/通知/媒体记录，并**删除磁盘目录 `uploads/<学号>/`**；操作日志保留但置空 `user_id` |

> 删除用户的详细影响范围见 [DATA.md](DATA.md) 第三节。

### 6.3 评论管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/comments` | 评论列表：`keyword` / `post_id` / `user_id` / `include_deleted` / 分页 |
| GET | `/admin/comments/stats` | 评论概览（总数 / 可见 / 已删 / 评论最多的帖子） |
| DELETE | `/admin/comments/{id}` | 删除评论（数据库物理删除，含子回复、点赞、媒体、互动通知；兼容 `?purge=1`） |

> 评论的**发表**功能仍属 v1.2；删除能力在 v1.0 提前提供，便于管理员处理违规内容。

### 6.4 内容管理（跨全部模块）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/posts` | 全部帖子：`keyword` / `type` / `status` / `audit_status` / `is_deleted` / `is_top` / `user_id` / 分页 |
| GET | `/admin/posts/pending` | 待审核列表 |
| GET | `/admin/posts/{id}` | 详情（含已软删除） |
| PUT | `/admin/posts/{id}` | 编辑帖子内容 |
| POST | `/admin/posts/{id}/audit` | 审核：`{audit_status, remark, status?}`，自动通知作者 |
| POST | `/admin/posts/batch/audit` | 批量审核：`{post_ids, audit_status, remark}` |
| POST | `/admin/posts/{id}/status` | 直接改业务状态：`{status, reason?}` |
| POST | `/admin/posts/{id}/top` | 置顶 / 取消置顶：`{is_top}`（不传则取反） |
| DELETE | `/admin/posts/{id}` | 删除（软删除 → 回收站），并通知作者 |
| GET | `/admin/posts/stats/summary` | 内容概览（各状态 / 各模块数量） |

### 6.5 模块管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/modules` | 全部模块（含禁用）+ 帖子数 + 待审核数 |
| POST | `/admin/modules` | 新增模块：`{code, name, icon, description, sort_order, enabled, config}` |
| PUT | `/admin/modules/{id}` | 修改模块 |
| POST | `/admin/modules/{id}/toggle` | 启用 / 禁用：`{enabled}`（不传则取反） |
| POST | `/admin/modules/reorder` | 批量排序：`{items: [{id, sort_order}]}` |
| DELETE | `/admin/modules/{id}` | 删除模块（内置模块禁止删除；有帖子时禁止删除） |

### 6.6 回收站

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/trash` | 回收站列表（含删除人、保留条数配置） |
| POST | `/admin/trash/{id}/restore` | 恢复 |
| DELETE | `/admin/trash/{id}` | 彻底删除 |
| POST | `/admin/trash/batch/restore` | 批量恢复：`{post_ids}` |
| POST | `/admin/trash/batch/purge` | 批量彻底删除：`{post_ids}` |
| POST | `/admin/trash/cleanup` | 立即按保留条数清理：`{keep?}`（同时写入配置） |
| GET | `/admin/trash/stats` | 回收站概览与保留策略 |

### 6.7 举报处理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/reports` | 举报列表：`status` / `keyword` / 分页 |
| POST | `/admin/reports/{id}/handle` | 处理：`{status: handled\|rejected, remark, action: none\|delete_post\|ban_user}` |

### 6.8 日志管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/logs/operations` | 操作日志：`keyword` / `module` / `action` / `log_type` / `target_type` |
| GET | `/admin/logs/logins` | 登录日志：`keyword` / `success=0\|1` |
| GET | `/admin/logs/errors?lines=200` | 异常日志（读取 `app/logs/error.log` 尾部） |
| GET | `/admin/logs/summary` | 日志概览统计 |

### 6.9 系统配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/configs` | 配置列表（含分组） |
| PUT | `/admin/configs` | 批量修改：`{items: [{key, value}]}` |
| POST | `/admin/configs/reset` | 恢复默认：`{keys?}`（不传则全部） |
| POST | `/admin/configs/init` | 补齐缺失配置项 |

---

## 附录 A：业务错误码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1001 | 参数错误 |
| 1002 | 资源不存在 |
| 1003 | 请求方法不被允许 |
| 1004 | 请求过于频繁 |
| 2001 | 未登录 / token 无效 |
| 2002 | token 已过期 |
| 2003 | 已登录但无权限 |
| 2004 | 账号已被封禁 |
| 2005 | 验证码错误或已过期 |
| 2006 | 学号或密码错误 |
| 3001 | 学号已注册 |
| 3002 | 用户不存在 |
| 4001 | 帖子不存在 |
| 4002 | 当前状态不可查看详情 |
| 4003 | 已审核，不能重复审核 |
| 4004 | 非法状态流转 |
| 5001 | 举报已处理 |
| 5002 | 通知不存在 |
| 5003 | 超过 5 分钟不能撤回（评论 / 私信共用） |
| 6001 | 不支持的文件类型 |
| 6002 | 文件超出大小限制 |
| 6003 | 文件上传失败 |
| 7001 / 7002 | 历史占位码：v1.2 已实现，接口不再返回 |
| 9001 | 服务器内部错误 |
| 9002 | 数据库操作失败 |

## 附录 B：系统配置项

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `site_name` | 校园生活平台 | 站点名称 |
| `site_notice` | — | 首页公告 |
| `security_notice_enabled` | `1` | 是否弹出安全公告 |
| `security_notice_text` | — | 安全公告内容 |
| `post_audit_enabled` | `1` | 发帖是否需要审核 |
| `register_captcha_enabled` | `1` | 注册是否需要验证码 |
| `recycle_retention_count` | `10` | 回收站保留条数 |
| `recycle_retention_mode` | `force` | 超量处理方式（彻底删除 / 仅保留） |
| `upload_allowed_ext` | `jpg,jpeg,png,gif,webp,mp4,mov,mp3,wav,m4a,ogg,webm` | 允许上传的后缀 |
| `upload_max_mb_image` | `10` | 图片大小上限（MB） |
| `upload_max_mb_video` | `50` | 视频大小上限（MB） |
| `upload_max_mb_audio` | `5` | 语音大小上限（MB，评论 / 私信录音） |
| `page_default_size` | `10` | 默认每页条数 |
| `page_max_size` | `100` | 每页条数上限 |
| `guest_can_list` | `1` | 游客可浏览列表 |
| `guest_can_detail` | `0` | 游客可查看详情 |

## 附录 C：权限矩阵

| 功能 | 游客 | 普通用户 | 管理员 |
|---|---|---|---|
| 浏览帖子列表 | ✅（可配置） | ✅ | ✅ |
| 查看帖子详情 | ❌（可配置） | ✅ | ✅ |
| 发布帖子 | ❌ | ✅ | ✅（免审核） |
| 编辑 / 删除自己的帖子 | ❌ | ✅ | ✅ |
| 标记帖子状态 | ❌ | ✅（自己的） | ✅（全部） |
| 评论 / 点赞 | ❌ | ✅ | ✅ |
| 私信 / 已读回执 | ❌ | ✅（本人会话） | ✅（本人会话） |
| 收藏 / 举报 | ❌ | ✅ | ✅ |
| 查看所有用户信息 | ❌ | ❌ | ✅ |
| 封禁 / 解封用户 | ❌ | ❌ | ✅ |
| 重置用户密码 | ❌ | ❌ | ✅ |
| 审核帖子 / 删除任意帖子 | ❌ | ❌ | ✅ |
| 查看操作日志 | ❌ | ❌ | ✅ |
| 模块管理 / 回收站配置 | ❌ | ❌ | ✅ |
| 调整用户角色 | ❌ | ❌ | 超级管理员 |
