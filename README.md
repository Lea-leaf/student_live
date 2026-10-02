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
│   │   ├── models/               数据模型（users / posts / modules / 日志 / 配置 …）
│   │   ├── modules/              业务模块（每个模块一个文件夹）
│   │   │   ├── auth/             认证：注册 / 登录 / 资料 / 安全公告
│   │   │   ├── lost_found/       失物招领（P0）
│   │   │   ├── common/           字典 / 模块列表 / 上传 / 健康检查
│   │   │   ├── favorites/        收藏
│   │   │   ├── reports/          举报
│   │   │   ├── notifications/    通知
│   │   │   ├── comments/         评论（v1.2，接口已固定）
│   │   │   ├── messages/         私信（v1.2，接口已固定）
│   │   │   └── posts_service.py  跨模块共用的帖子领域服务
│   │   ├── admin/                管理端（dashboard/users/posts/modules/logs/trash/reports/configs）
│   │   ├── utils/                响应封装 / JWT / 校验 / 上传 / 配置服务 / 日志 / 验证码 / 种子数据
│   │   └── logs/                 运行日志（app.log / error.log）
│   ├── migrations/               Flask-Migrate 迁移目录
│   ├── scripts/                  开发脚本（dev_init / smoke_test / gen_schema_docs）
│   ├── tests/                    pytest 用例（44 个）
│   ├── uploads/                  上传的图片与视频
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                    开发启动入口
├── frontend/                     Vue3 前端
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

### 1. 后端

```powershell
cd backend

# 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 方式 A：一键初始化（建表 + 模块 + 配置 + 演示数据）
.\.venv\Scripts\python.exe scripts\dev_init.py --reset

# 方式 B：分步执行
# .\.venv\Scripts\python.exe -m flask --app run:app init-db
# .\.venv\Scripts\python.exe -m flask --app run:app create-admin
# .\.venv\Scripts\python.exe -m flask --app run:app seed

# 启动（默认 http://127.0.0.1:5000）
.\.venv\Scripts\python.exe run.py
```

> `pip` 下载慢时可加国内镜像：
> `-i https://pypi.tuna.tsinghua.edu.cn/simple`

### 2. 前端

```powershell
cd frontend
pnpm install          # 或 npm install
pnpm dev              # 开发服务器 http://127.0.0.1:5173
pnpm build            # 生产构建，输出 dist/
```

前端通过 Vite 代理访问后端（`/api` → `http://127.0.0.1:5000`），开发时无需处理跨域。

### 3. 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | `admin` | `admin123` |
| 学生 | `20210001` | `123456` |

登录页提供了「演示账号一键填入」按钮，方便答辩演示。

### 4. 打开页面

- 学生端：<http://127.0.0.1:5173/#/>
- 管理端：用管理员登录后进入 <http://127.0.0.1:5173/#/admin/dashboard>

---

## 三、自测与验证

```powershell
cd backend

# 单元 / 接口测试（内存库，44 个用例）
.\.venv\Scripts\python.exe -m pytest tests -q

# 端到端冒烟（需先启动后端服务，42 项断言）
.\.venv\Scripts\python.exe scripts\smoke_test.py

# 改动模型后同步生成建表 SQL 与 ER 图
.\.venv\Scripts\python.exe scripts\gen_schema_docs.py
```

已验证结果：**pytest 44 passed**，**HTTP 冒烟 42/42 通过**，**前端 `vite build` 成功**，
Vite 开发代理 `/api` → Flask 联通。

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

## 五、关键设计说明（答辩要点）

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

10. **安全基线**：密码 Werkzeug scrypt 哈希（自带盐）；JWT 含签发者与过期时间；
    登录失败按 IP+账号节流；封禁用户即时失效（每次请求校验状态）；
    输入统一走 `utils/validators.py` 校验与危险标签过滤；上传文件用 uuid 重命名并限制类型与大小；
    文件访问拒绝路径穿越。

---

## 六、迭代计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| v1.0 原型 | 登录注册、角色权限、失物招领、管理员用户/帖子列表、审核、回收站、日志、收藏、举报、通知 | ✅ 已完成 |
| v1.1 | 审核流程细化、通知中心、操作日志可视化、回收站策略配置 | ✅ 已完成（提前纳入 v1.0） |
| v1.2 | 评论、私信（预留 WebSocket 实时通道） | 接口已固定，返回「待开放」 |
| v1.3 | 模块管理增强、二手交易模块业务实现 | 模块骨架已就绪 |
| v2.0 | 移动端拆分、多级管理员（RBAC 生效）、Docker 部署上线 | 表与常量已预留 |

---

## 七、常见问题

**Q：后端启动报 `ModuleNotFoundError: No module named 'app'`？**
A：请在 `backend` 目录下执行（`run.py` 所在目录）。

**Q：前端页面能打开但数据一直报错？**
A：确认后端已在 `127.0.0.1:5000` 启动；前端请求经 Vite 代理转发，后端未启动时会在页面右上角提示网络异常。

**Q：`pnpm install` 后 `vite build` 报找不到 esbuild？**
A：pnpm 10+ 默认拦截依赖构建脚本，本项目已在 `frontend/pnpm-workspace.yaml` 中放行 `esbuild`；
若仍报错，执行 `pnpm rebuild esbuild`。

**Q：怎么切换到 MySQL？**
A：在 `backend/.env` 中设置
`DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/school_life?charset=utf8mb4`，
安装 `PyMySQL`，再执行 `flask db upgrade`（或直接导入 `docs/schema_mysql.sql`）。

**Q：上传的图片存在哪里？**
A：`backend/uploads/YYYYMMDD/uuid.ext`，通过 `GET /api/v1/files/<日期>/<文件名>` 访问，
记录同时写入 `upload_files` 表。

---

## 八、待定项的默认处理（对应需求文档第十五节）

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
