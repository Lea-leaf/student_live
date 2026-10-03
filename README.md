# ============================================================================
# 校园生活平台 · 项目说明
#
# 毕业设计原型：学生之间的校园生活互助平台（区别于学校官方管理系统）
# 技术栈：Flask + SQLAlchemy + SQLite/MySQL + JWT ｜ Vue3 + Vite + Element Plus + Pinia
# ============================================================================

## 一、项目简介

面向本校学生的校园生活互助平台，采用 **前后端分离 + 模块化** 架构。

- 用户用 **学号 + 图形验证码** 注册，JWT 认证；
- 核心模块 **失物招领（P0）** 已完整实现：发布 / 列表 / 搜索 / 详情 / 审核 / 状态流转 / 我的发布 / 回收站；
- **模块化设计**：帖子统一存 `posts` 表，用 `type` 字段区分模块；模块本身是数据库里的数据行，
  管理员在后台即可 **启用 / 禁用 / 排序 / 新增** 模块（如「二手交易」「拼单」「跑腿」「其他」）；
- **管理端** 覆盖：首页统计、用户管理（封禁 / 重置密码 / 角色）、内容管理（审核 / 删除 / 置顶）、
  模块管理、回收站（保留条数可配置）、举报处理、日志管理、系统配置。

### 目录结构

```
Project_graduation/
├── backend/                      Flask 后端
│   ├── app/
│   │   ├── __init__.py           应用工厂（扩展、蓝图、错误处理、CLI）
│   │   ├── config.py             三级配置：开发 / 测试 / 生产
│   │   ├── extensions.py         db / migrate / cors 单例
│   │   ├── models/               数据模型（用户/帖子/模块/互动/点赞/日志/配置）
│   │   ├── modules/              业务模块（每个模块一个文件夹）
│   │   │   ├── auth/             认证：注册 / 登录 / 资料 / 安全公告
│   │   │   ├── lost_found/       失物招领（P0）
│   │   │   ├── common/           字典 / 模块列表 / 上传 / 健康检查
│   │   │   ├── favorites/        收藏
│   │   │   ├── reports/          举报
│   │   │   ├── notifications/    通知
│   │   │   ├── comments/         评论（删除已可用；发表待实现）
│   │   │   ├── messages/         私信（待实现）
│   │   │   └── posts_service.py  跨模块共用的帖子领域服务
│   │   ├── admin/                管理端（dashboard/users/posts/comments/modules/logs/trash/reports/configs）
│   │   ├── utils/                响应封装 / JWT / 校验 / 上传 / 配置服务 / 日志 / 验证码 / 种子数据
│   │   │                         清理服务（cleanup）/ 媒体引用（media_refs）
│   │   └── logs/                 运行日志（app.log / error.log）
│   ├── migrations/               Flask-Migrate 迁移目录
│   ├── scripts/                  开发脚本：dev_init / smoke_test / gen_schema_docs /
│   │                             upgrade_schema（结构升级）/ migrate_upload_layout（目录迁移）/
│   │                             fix_media_references（引用修复）/ check_orphans（一致性自检）/
│   │                             fix_ps1_bom（脚本编码修复）/ verify_media_storage
│   ├── tests/                    pytest 用例（90 个）
│   │                             含结构收口、媒体地址一致性、视频语音上传、序列化字段完整性
│   ├── uploads/                  上传的媒体文件（按 <学号>/<日期> 分目录）
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                    开发启动入口
├── frontend/                     Vue3 前端
│   ├── public/                   favicon.svg（站点图标）
│   ├── scripts/                  check-messagebox.js（静态检查未处理的 MessageBox 调用）
│   ├── src/
│   │   ├── api/                  接口封装（request 拦截器 + 各模块地址）
│   │   ├── components/           PostCard 等复用组件
│   │   ├── layouts/              PublicLayout / UserLayout / AdminLayout
│   │   ├── router/               路由表 + 登录与管理员守卫
│   │   ├── stores/               Pinia：user / app / notification
│   │   ├── styles/               全局样式（PC 优先 + 移动端自适应）
│   │   ├── utils/                时间格式化、状态标签、剪贴板等
│   │   └── views/
│   │       ├── user/             首页 / 列表 / 详情 / 发布编辑 / 我的发布 / 收藏 / 通知 / 个人中心
│   │       └── admin/            概览 / 审核台 / 内容 / 用户 / 用户详情 / 模块 / 回收站 / 举报 / 日志 / 配置
│   ├── package.json
│   ├── vite.config.js            @ 别名 + /api 代理到后端
│   └── index.html
├── docs/
│   ├── API.md                    接口文档（含错误码、配置项、权限矩阵）
│   ├── DATA.md                   数据存储与备份说明（数据到底存在哪）
│   ├── ER.md                     ER 图（Mermaid，自动生成）
│   ├── schema_mysql.sql          MySQL 建表脚本（部署）
│   └── schema_sqlite.sql         SQLite 建表脚本（开发）
└── README.md
```

---

## 二、快速开始

### 0. 环境要求

| 依赖 | 版本 |
|---|---|
| Python | 3.10+（本项目在 3.12 上验证） |
| Node.js | 18+（本项目在 24 上验证） |
| 包管理器 | pip / pnpm（npm 亦可） |

### 1. 一键启动（推荐）

项目根目录提供了启动脚本，会自动检查依赖、初始化数据库、后台拉起前后端：

```powershell
.\start-dev.ps1                 # 初始化（首次需要）+ 启动前后端
.\start-dev.ps1 -SkipInit       # 跳过初始化，直接启动（日常用这个）
.\start-dev.ps1 -BackendOnly    # 只启动后端（没装 Node 时可用）
.\start-dev.ps1 -InitOnly       # 只初始化数据库，不启动服务
.\start-dev.ps1 -InstallDeps    # 强制重装依赖
.\stop-dev.ps1                  # 停止（只结束占用 5000 / 5173 的进程）
```

也可以直接双击这几个 `.cmd`（内部同样调用上面的 ps1，已绕过执行策略限制）：

| 文件 | 作用 |
|---|---|
| `start-dev.cmd` | 启动前后端 |
| `init-db.cmd` | 只初始化数据库 |
| `stop-dev.cmd` | 停止服务 |

> **如果提示"禁止运行脚本"**：用 `powershell -ExecutionPolicy Bypass -File .\start-dev.ps1`，
> 或直接双击 `.cmd`。
>
> **脚本改完不生效 / 报"字符串缺少终止符"**：说明 `.ps1` 被另存成了「UTF-8 无 BOM」。
> Windows PowerShell 5.1 会把无 BOM 的 UTF-8 当 GBK 读，中文注释被拆坏导致解析失败。
> 执行 `backend\.venv\Scripts\python.exe backend\scripts\fix_ps1_bom.py` 一键修复
> （`--check` 只检查不修改）。

### 2. 手动启动（两个终端）

```powershell
# 终端 1：后端
cd backend
.\.venv\Scripts\python.exe run.py            # http://127.0.0.1:5000

# 终端 2：前端
cd frontend
pnpm run dev                                 # http://127.0.0.1:5173
```

### 3. 后端初始化（脚本已包含，手动执行时用）

```powershell
cd backend

# 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 方式 A：一键初始化（建表 + 模块 + 配置 + 演示数据）
.\.venv\Scripts\python.exe scripts\dev_init.py            # 幂等，可重复执行
.\.venv\Scripts\python.exe scripts\dev_init.py --reset    # 清空业务数据后重建演示数据

# 方式 B：分步执行
# .\.venv\Scripts\python.exe -m flask --app run:app init-db
# .\.venv\Scripts\python.exe -m flask --app run:app create-admin
# .\.venv\Scripts\python.exe -m flask --app run:app seed

# 启动（默认 http://127.0.0.1:5000）
.\.venv\Scripts\python.exe run.py
```

> `pip` 下载慢时可加国内镜像：
> `-i https://pypi.tuna.tsinghua.edu.cn/simple`

### 4. 前端单独构建（可选）

```powershell
cd frontend
pnpm install          # 或 npm install
pnpm build            # 生产构建，输出 dist/
pnpm preview          # 本地预览构建产物
```

前端通过 Vite 代理访问后端（`/api` → `http://127.0.0.1:5000`），开发时无需处理跨域。

> pnpm 10+ 默认拦截依赖的构建脚本，`esbuild` 会因此不可用。
> 本项目已在 `frontend/pnpm-workspace.yaml` 中放行；若仍报错，执行 `pnpm rebuild esbuild`。

### 5. 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | `admin` | `admin123` |
| 学生 | `20210001` | `123456` |

登录页提供了「演示账号一键填入」按钮，方便答辩演示。

### 6. 打开页面

- 学生端：<http://127.0.0.1:5173/#/>
- 管理端：用管理员登录后进入 <http://127.0.0.1:5173/#/admin/dashboard>

> ⚠️ 地址必须带 `#`（前端使用 hash 路由），而且要用 **5173** 端口。
> 5000 端口只提供 API，直接打开会返回 404 —— 这是设计如此，不是故障。

---

## 三、自测与验证

```powershell
# ---------- 后端 ----------
cd backend

# 单元 / 接口测试（内存库，90 个用例）
.\.venv\Scripts\python.exe -m pytest tests -q

# 端到端冒烟（需先启动后端服务，42 项断言）
.\.venv\Scripts\python.exe scripts\smoke_test.py

# 结构升级（改了模型 / 拉了新代码后执行；幂等，只加列不删数据）
.\.venv\Scripts\python.exe scripts\upgrade_schema.py --check   # 先预演
.\.venv\Scripts\python.exe scripts\upgrade_schema.py

# 数据一致性自检（孤儿指针 + 孤儿文件）
.\.venv\Scripts\python.exe scripts\check_orphans.py

# 改动模型后同步生成建表 SQL 与 ER 图
.\.venv\Scripts\python.exe scripts\gen_schema_docs.py

# ---------- 前端 ----------
cd ..\frontend

# 静态检查：未接住 reject 的 ElMessageBox 调用（避免控制台报 cancel）
pnpm run check

# 生产构建
pnpm run build
```

已验证结果：**pytest 90 passed**，**HTTP 冒烟 42/42 通过**，**`pnpm run check` 0 处问题**，
**前端 `vite build` 成功**，Vite 开发代理 `/api` → Flask 联通。

---

## 四、接口速查

| 分组 | 前缀 | 说明 |
|---|---|---|
| 认证 | `/api/v1/auth` | 验证码 / 注册 / 登录 / 资料 / 安全公告 |
| 公共 | `/api/v1/common` | 字典 / 模块 / 配置 / 上传 / 健康检查 |
| 失物招领 | `/api/v1/lost_found` | 列表 / 详情 / 发布 / 编辑 / 删除 / 状态 / 我的发布 |
| 收藏 | `/api/v1/favorites` | 收藏切换与列表 |
| 举报 | `/api/v1/reports` | 提交举报 / 我的举报 |
| 通知 | `/api/v1/notifications` | 列表 / 未读数 / 已读 |
| 评论·私信 | `/api/v1/comments`、`/api/v1/messages` | v1.2 开放，接口形状已固定 |
| 管理端 | `/api/v1/admin/...` | 统计 / 用户 / 内容 / 模块 / 回收站 / 举报 / 日志 / 配置 |

完整字段说明见 [docs/API.md](docs/API.md)。

---

## 五、帖子数据结构（平台核心）

> 这一节回答项目的**核心设计问题**：不管失物招领、二手交易、拼单还是跑腿，
> 本质都是「**发一条带图片/视频的帖子，按类型分类，别人可以评论和收藏**」。
> 所以全平台**只用一张 `posts` 表**，用 `type` 字段区分模块。

### 5.1 为什么只用一张表

| 方案 | 问题 |
|---|---|
| 每个模块一张表（`lost_found_posts`、`second_hand_posts`…） | 加一个模块就要建表、改代码、改查询；跨模块的「综合浏览页」要 UNION 多张表；评论/收藏/举报要针对每张表各写一套 |
| **一张 `posts` 表 + `type` 区分**（本项目采用） | 加模块只是插一行 `modules` 数据；综合浏览一条 SQL；评论/收藏/举报/媒体**全模块共用** |

模块特有字段（二手交易的 `price`、拼单的 `target_count`）放在 `ext_json` 里，**不用改表结构**。

### 5.2 `posts` 表完整字段

| 分组 | 字段 | 类型 | 说明 |
|---|---|---|---|
| **归属分类** | `type` | string(64) | 模块标识，对应 `modules.code`（`lost_found` / `second_hand` / …） |
| | `user_id` | FK → `users.id` | 发布者 |
| **内容** | `title` | string(128) | 标题（选填） |
| | `content` | text | 描述正文（选填） |
| | **`media`** | text | **图片/视频，JSON 数组**（结构见 5.3） |
| | `location` | string(128) | 地点（选填，如「图书馆三楼」） |
| | `happened_at` | datetime | 发生时间（选填；丢了东西的时间 / 交易时间） |
| | `contact` | string(128) | **联系方式（必填，公开可见）** |
| **状态** | `status` | string(16) | 业务状态：`ongoing` 进行中 / `claimed` 已认领 / `expired` 已过期 / `closed` 已关闭 |
| | `audit_status` | string(16) | 审核状态：`pending` 待审核 / `approved` 已通过 / `rejected` 已拒绝 |
| | `audit_remark` | string(255) | 审核意见 |
| | `audited_by` / `audited_at` | int / datetime | 审核人、审核时间 |
| **运营** | `is_top` | bool | 是否置顶 |
| | `view_count` | int | 浏览量（详情页自动 +1，作者与管理员查看不计数） |
| | `comment_count` | int | 评论数（含楼中楼回复；删评论时自动回写，避免计数漂移） |
| | `favorite_count` | int | 收藏数 |
| | **`like_count`** | int | **点赞数**（与收藏是**两个独立功能**，各自计数） |
| **软删除** | `is_deleted` | bool | 是否进回收站（普通用户完全看不到） |
| | `deleted_at` / `deleted_by` | datetime / int | 删除时间、删除人 |
| **扩展** | **`ext_json`** | text | **模块特有字段的 JSON**（见 5.4） |
| **公共** | `id` / `created_at` / `updated_at` | — | 主键与时间戳（所有表都有） |

索引：`type + status + is_deleted`（列表筛选）、`audit_status + created_at`（审核台），
以及 `type`、`user_id`、`status`、`audit_status`、`is_deleted`、`is_top` 单列索引。

### 5.3 `media` 字段（图片 / 视频 / 语音）

存的是 **JSON 数组**，每项结构如下（由上传接口返回，数据库不存文件本身）。
**评论与私信的媒体用的是完全相同的结构**，因此存储、上传、展示三层都能复用：

```json
[
  {
    "id": 1,
    "url": "/api/v1/files/20210001/20261002/9f3c1a2b....png",
    "path": "20210001/20261002/9f3c1a2b....png",
    "name": "我的伞.png",
    "type": "image",
    "size": 10241,
    "mime": "image/png"
  },
  {
    "id": 2,
    "url": "/api/v1/files/20210001/20261002/7d21e0f4....mp3",
    "path": "20210001/20261002/7d21e0f4....mp3",
    "name": "语音留言.mp3",
    "type": "audio",
    "size": 20480,
    "mime": "audio/mpeg"
  }
]
```

| 键 | 含义 |
|---|---|
| `url` | 前端直接引用；实际文件在 `uploads/<学号>/<日期>/` 下 |
| `path` | 相对 `uploads/` 的路径（与 `upload_files` 表一致） |
| `type` | `image` / `video` / `audio` |
| `name` / `size` / `mime` | 原始文件名、字节数、MIME 类型 |

> ⚠️ **媒体地址在数据库里存了两处**：`posts.media`（以及 `comments.media`、`messages.media`）
> 与 `upload_files` 表。改存储布局时必须同时更新，否则页面会 404（详见 [docs/DATA.md](docs/DATA.md)）。
> `upload_files` 用 `owner_type` + `owner_id` 指向归属对象（`post` / `comment` / `message`）。

| 键 | 含义 |
|---|---|
| `url` | 前端直接引用；实际文件在 `uploads/<学号>/<日期>/` 下 |
| `path` | 相对 `uploads/` 的路径（与 `upload_files` 表一致） |
| `type` | `image` 或 `video` |
| `name` / `size` / `mime` | 原始文件名、字节数、MIME 类型 |

> ⚠️ **媒体地址在数据库里存了两处**：`posts.media` 与本表的 `upload_files`。
> 改存储布局时必须同时更新，否则页面会 404（详见 [docs/DATA.md](docs/DATA.md)）。

### 5.4 `ext_json` 字段（模块差异化的关键）

不同模块要不同字段时**不动表结构**，直接塞 JSON：

```json
// 二手交易
{ "price": 120, "condition": "九成新", "trade_type": "面交", "original_price": 299 }

// 拼单
{ "target_count": 5, "joined_count": 2, "deadline": "2026-10-10 20:00", "unit_price": 12.5 }

// 跑腿
{ "fee": 5, "from": "菜鸟驿站", "to": "6 号楼 302", "deadline": "今天 18:00" }

// 失物招领（暂时没有特有字段，留空）
{}
```

前端按 `type` 渲染不同表单与展示样式，后端只做透传存取，
**新增模块不需要改数据库、不需要改接口签名**。

### 5.5 帖子与「评论 / 点赞 / 收藏」的关系

```mermaid
erDiagram
    users ||--o{ posts : "发布"
    modules ||..o{ posts : "type 分类（逻辑关联，非外键）"
    posts ||--o{ comments : "一对多"
    posts ||--o{ favorites : "收藏（私有书签）"
    posts ||--o{ post_likes : "点赞（公开计数）"
    posts ||--o{ reports : "一对多"
    posts ||--o{ upload_files : "media 里的每个文件一条记录"
    comments ||--o{ comments : "parent_id 直接父级"
    comments ||--o{ comments : "root_id 顶级评论（楼中楼）"
    comments ||--o{ comment_likes : "评论点赞"
    users ||--o{ comments : "评论人"
    users ||--o{ favorites : "收藏人"
    users ||--o{ post_likes : "点赞人"
```

> **注意 `modules` 与 `posts` 的关系**：`posts.type` 存的是 `modules.code` 的值，
> 这是**逻辑关联**（`Module.code == Post.type`），数据库层**没有建外键约束**。
> 这样设计是有意的：管理员可以在后台自由新增模块（甚至直接改 `type` 的字符串值），
> 不会被外键卡住；代价是删除模块时需要应用层检查（`admin/modules.py` 里已有
> "模块下有帖子则拒绝删除"的校验，不会产生孤儿）。

| 交互 | 表 | 关键字段 | 说明 |
|---|---|---|---|
| **评论（楼中楼）** | `comments` | `post_id`、`user_id`、`parent_id`、**`root_id`**、`reply_to_user_id`、**`media`**、`like_count`、`reply_count` | `parent_id` 指向**直接父级**、`root_id` 指向**顶级评论**：查一层用前者，一次取整棵子树用后者（不用递归查库）。`media` 支持**图片与语音**，结构与帖子一致 |
| **评论点赞** | `comment_likes` | `user_id` + `comment_id`，唯一约束 `uq_comment_like_user_comment` | 每条评论独立计数 |
| **帖子点赞** | `post_likes` | `user_id` + `post_id`，唯一约束 `uq_post_like_user_post` | 帖子表的 `like_count` 是它的冗余计数 |
| **收藏** | `favorites` | `user_id` + `post_id`，唯一约束 `uq_favorite_user_post` | 语义是**私有书签**（"留着以后看"），与点赞**互相独立** |
| **举报** | `reports` | `post_id`、`reporter_id`、`reason`、`status` | 管理员处理后可联动删除帖子或封禁用户 |
| **通知** | `notifications` | `user_id`、`type`、`ref_id`、`is_read` | 审核结果、评论、私信、系统公告统一走这里 |

> **为什么点赞与收藏要分成两张表**：语义与可见性不同 ——
> 收藏是私有书签、只有自己看得到列表；点赞是公开表态、计数显示在帖子卡片上。
> 合并成一张表加 `type` 字段虽然可行，但会让「我的收藏」和「点赞数」的查询互相干扰。

### 5.6 媒体类型与大小限制

图片 / 视频 / **语音** 三类走同一套存储与访问链路，只是大小限制分档：

| 类型 | 判断依据 | 默认上限 | 配置键 |
|---|---|---|---|
| `image` | `jpg/jpeg/png/gif/webp/bmp` | 10 MB | `upload_max_mb_image` |
| `video` | `mp4/mov/avi/webm/mkv` | 50 MB | `upload_max_mb_video` |
| **`audio`** | `mp3/wav/m4a/ogg/aac/amr/silk/webm` | **5 MB** | `upload_max_mb_audio` |

> ⚠️ 早期实现是「是 video 就 video，**否则一律 image**」，导致 `mp3` 被当成图片、
> 并套用了图片的 10MB 限制。现在显式判断三类，未知后缀才回落到 `image`。
>
> 前端上传单独放宽了超时（`UPLOAD_TIMEOUT`，默认 5 分钟）：全局 axios 是 20 秒，
> 图片够用但**视频必然超时**，这是实际踩过的坑。

### 5.7 一条完整帖子的 API 返回示例

```json
{
  "id": 17,
  "type": "lost_found",
  "title": "在图书馆三楼丢了黑色雨伞",
  "content": "昨天下午在图书馆三楼自习，落在一把黑色长柄雨伞，伞柄有个小熊挂件。",
  "media": [
    { "id": 1, "url": "/api/v1/files/23190508/20261002/b80799f3....png",
      "path": "23190508/20261002/b80799f3....png", "name": "伞.png",
      "type": "image", "size": 955961, "mime": "image/png" }
  ],
  "location": "图书馆三楼",
  "happened_at": "2026-10-02 15:30:00",
  "contact": "微信 xiaoming2021",
  "status": "ongoing",
  "status_label": "进行中",
  "audit_status": "approved",
  "audit_status_label": "已通过",
  "is_top": false,
  "view_count": 42,
  "comment_count": 3,
  "favorite_count": 5,
  "is_deleted": false,
  "ext": {},
  "author": { "id": 2, "student_id": "23190508", "display_name": "Lea" },
  "created_at": "2026-10-02 16:01:22"
}
```

> 列表接口返回的是精简版（`to_brief()`）：`content` 截断 80 字、`media` 只带第一张图，
> 减少传输体积；详情接口返回完整字段。

### 5.8 这套设计对答辩的价值

| 结论 | 证据 |
|---|---|
| **一套结构支撑所有类型** | 失物招领已完成；二手交易/拼单/跑腿**只需填 `ext_json` 与前端表单**，不需要动数据库 |
| **加模块不改代码** | 后台「模块管理」新增一行 → 前台导航与筛选器自动出现（已实测：启用"二手交易"后导航立刻多一个 tab） |
| **交互能力全模块复用** | 评论/收藏/举报/通知都是按 `post_id` 关联，新模块**自动拥有**这些能力 |
| **可平滑扩展** | 要加点赞只需照 `favorites` 加一张表；要加标签只需加 `post_tags` 关联表；帖子主结构不用动 |

---

## 六、关键设计说明（答辩要点）

1. **统一响应结构**：所有接口返回 `{code, msg, data}`，前端 axios 拦截器统一拆包与报错，
   业务代码不重复写错误处理。错误码分段管理（1xxx 参数、2xxx 认证、4xxx 帖子……）。

2. **模块化架构**：新增一个功能模块只需三步 —— 在 `app/modules/<name>/routes.py` 定义蓝图、
   在 `models/module.py::default_modules()` 登记模块元数据、在 `modules/__init__.py` 加一行映射。
   模块的启停与排序完全由后台数据控制，**前端导航自动跟随**。

3. **帖子统一存储 + 模块扩展字段**：`posts` 表用 `type` 区分模块，模块特有字段放 `ext_json`，
   避免每加一个模块就改表结构。

4. **状态可见性规则**：需求 6.2 的「列表可见 / 详情可点」在 `Post.list_visible` 与
   `Post.detail_visible` 中集中定义，列表与详情接口共用同一套判断，不会出现规则不一致。

5. **审核工作流**：发布 → 待审核 → 管理员通过 / 拒绝 → 自动给作者发通知；
   作者编辑已通过的帖子会重新进入待审核；管理员发帖默认直通（可配置）。

6. **回收站**：软删除（`is_deleted`）而非物理删除，仅管理员可见；
   保留条数 `recycle_retention_count` 与超量策略 `recycle_retention_mode` 可在后台配置，
   每次删除后自动按策略清理。

7. **一切可配置**：审核开关、注册验证码、游客权限、上传限制、分页上限、回收站策略
   全部存在 `system_configs` 表，读取顺序为「表 → 环境变量 → 代码默认值」，带 30 秒进程内缓存。

8. **RBAC 预留**：角色常量已包含 `super_admin / auditor / user_admin / module_admin / moderator`，
   并预留 `admin_module_access` 表（管理员 ↔ 模块授权）。当前原型只用 `user / admin` 两级，
   升级多级管理员时不需要改表结构。

9. **数据库平滑迁移**：开发用 SQLite，部署切 MySQL 只需改 `.env` 里的 `DATABASE_URL`；
   已集成 Flask-Migrate，并额外提供自动生成的 MySQL 建表脚本。
   **注意**：`db.create_all()` 只建缺失的表、**不给已有表加列**，所以结构变更（加列/加表）
   一律走 `scripts/upgrade_schema.py`（幂等、只加不删、带数据回填）。

10. **安全基线**：密码 Werkzeug scrypt 哈希（自带盐）；JWT 含签发者与过期时间；
    登录失败按 IP+账号节流；封禁用户即时失效（每次请求校验状态）；
    输入统一走 `utils/validators.py` 校验与危险标签过滤；上传文件用 uuid 重命名并限制类型与大小；
    文件访问拒绝路径穿越。

---

## 七、迭代计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| v1.0 原型 | 登录注册、角色权限、失物招领、管理员用户/帖子列表、审核、回收站、日志、收藏、举报、通知 | ✅ 已完成 |
| v1.1 | 结构收口（楼中楼评论字段、评论/私信媒体、点赞独立建表、音频支持、结构升级脚本） | ✅ 已完成（表结构与迁移脚本就绪） |
| v1.2 | 评论发表/回复/语音（楼中楼）、评论点赞、私信收发与已读回执 | 表结构已就绪，**待写接口与前端** |
| v1.3 | 模块管理增强、二手交易 / 组队打车 / 交友三类模块（填 `ext_json` + 前端表单即可） | 模块骨架已就绪 |
| v2.0 | 移动端拆分、多级管理员（RBAC 生效）、Docker 部署上线 | 表与常量已预留 |

> **v1.2 为什么能"填"得很快**：评论的楼中楼、媒体、点赞字段全部已经建好
> （见第五节），接下来只需要写接口与前端组件，**不用再动数据库**。

---

## 八、常见问题

**Q：后端启动报 `ModuleNotFoundError: No module named 'app'`？**
A：请在 `backend` 目录下执行（`run.py` 所在目录）。

**Q：前端页面能打开但数据一直报错？**
A：确认后端已在 `127.0.0.1:5000` 启动；前端请求经 Vite 代理转发，后端未启动时会在页面右上角提示网络异常。

**Q：控制台报 `Unchecked runtime.lastError: The message port closed...` 或
`A listener indicated an asynchronous response by returning true...`？**
A：**这是浏览器扩展的噪音，与本项目无关，不用改。** 它是 Chromium 内核的标准提示：
某个扩展的 content script 向它的后台发了消息，但页面在回复到达前就跳转/关闭了，
所以每次**路由切换**都可能出现。

三条判据：
1. 本项目代码里**没有任何** `chrome.*` / `sendMessage` / `onMessage` / `MessageChannel` 调用；
2. 报错位置显示的是**页面 URL**（如 `:5173/#/publish:1`）而不是 `src/` 下的文件——`:1` 只是占位行号；
3. 浏览器命令行里能看到 `--extension-process --renderer-sub-type=extension`。

**功能测试时建议用无痕窗口**（`Ctrl+Shift+N`，默认禁用扩展），控制台会干净很多，
不至于把真正的错误淹没掉。

**Q：控制台报 `Uncaught (in promise) cancel`（文件指向 `messageBox.ts`）？**
A：这是 `ElMessageBox` 在用户点 `×` / `ESC` / 遮罩关闭时 **reject** 造成的，
说明某处调用**既没 `await`（在有 try 的位置）也没 `.catch()`**。
用 `cd frontend && pnpm run check` 静态扫描定位，修法二选一：

```javascript
try { await ElMessageBox.alert('...') } catch { /* 用户关闭 */ }
ElMessageBox.alert('...').catch(() => {})
```

**Q：`pnpm install` 后 `vite build` 报找不到 esbuild？**
A：pnpm 10+ 默认拦截依赖构建脚本，本项目已在 `frontend/pnpm-workspace.yaml` 中放行 `esbuild`；
若仍报错，执行 `pnpm rebuild esbuild`。

**Q：运行 `start-dev.ps1` 报"表达式或语句中包含意外的标记 }"、"字符串缺少终止符"？**
A：`.ps1` 被另存成了「UTF-8 无 BOM」。Windows PowerShell 5.1 会按 GBK 解码无 BOM 的 UTF-8
文件，中文注释被拆坏导致解析失败。执行
`backend\.venv\Scripts\python.exe backend\scripts\fix_ps1_bom.py` 一键补 BOM。
（用 VS Code 保存时请选 “UTF-8 with BOM”。）

**Q：重复执行 `dev_init.py` 会不会产生脏数据或报错？**
A：不会。默认策略是「库中已有业务数据就跳过种子生成」，模块与系统配置也只补缺失项、
不覆盖你在后台改过的值，因此该脚本可安全重复执行（`start-dev.ps1` 每次启动都会调用它）。
需要清空重建时用 `dev_init.py --reset`。

**Q：直接打开 `http://127.0.0.1:5000/` 报 404 / “The requested URL was not found”？**
A：正常。5000 端口只提供 `/api/v1/*` 接口与一个根路径信息页，界面在 5173 端口。
访问界面请用 <http://127.0.0.1:5173/#/>（注意 `#` 不能少）。

**Q：怎么切换到 MySQL？**
A：在 `backend/.env` 中设置
`DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/school_life?charset=utf8mb4`，
安装 `PyMySQL`，再执行 `flask db upgrade`（或直接导入 `docs/schema_mysql.sql`）。

**Q：上传的图片存在哪里？**
A：`backend/uploads/<学号>/<YYYYMMDD>/uuid.ext`，按「**用户 → 日期**」两级存放：
一级是上传者学号（硬盘上能直接看出数据归属，删用户时整目录删除），二级是上传日期。
`upload_files` 表**只记录相对路径与 URL**（不存文件本身），通过
`GET /api/v1/files/<学号>/<日期>/<文件名>` 访问。彻底删除帖子或删除用户时，磁盘文件会一并删除。

**Q：怎么检查有没有孤儿数据（外键指向已删记录 / 磁盘上有没人引用的文件）？**
A：`cd backend` 后执行 `.\.venv\Scripts\python.exe scripts\check_orphans.py`，
加 `--clean` 可顺手删除孤儿文件。旧的「日期/文件」上传布局可用
`scripts\migrate_upload_layout.py`（先加 `--check` 预演）迁移到新的「学号/日期」结构。

**Q：帖子里的图片显示不出来、控制台报 404（例如 `/api/v1/files/20261002/xxx.png`）？**
A：因为**媒体地址在数据库里存了两处**：`upload_files` 表一处、`posts.media`（JSON）一处。
只改一处就会出现「文件在磁盘上、页面却用旧地址」的情况。执行修复：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\fix_media_references.py --check   # 先预演
.\.venv\Scripts\python.exe scripts\fix_media_references.py           # 再修复
```

这条坑已固化成回归测试 `tests/test_media_reference.py`：
它会断言「帖子里的每个媒体 url 都能取到文件」，以后改布局不会再漏第二处引用。

---

## 九、待定项的默认处理（对应需求文档第十五节）

| 待定项 | 当前默认实现 |
|---|---|
| 游客能否浏览 | 可浏览列表（`guest_can_list=1`），不可看详情（`guest_can_detail=0`），后台可改 |
| 注册验证码形式 | 图形验证码（零依赖 SVG 生成），接口形状已留好，可替换为短信/邮箱 |
| 管理员分级 | 当前两级 `user / admin`，常量与授权表已按 RBAC 预留 |
| 私信是否实时 | 先普通接口，`conversation_key` 已按会话设计，可平滑升级 WebSocket |
| 视频大小限制 | 50MB（`upload_max_mb_video`，后台可改） |
| UI 库 | Element Plus（PC 优先 + 移动端自适应） |
| Git 托管 | 建议 Gitee，`.gitignore` 已排除依赖、数据库、上传文件与日志 |
| 数据库名 / 接口前缀 | `school_life` / `/api/v1` |
