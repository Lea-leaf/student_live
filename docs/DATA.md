# 数据存储与备份说明

> 本文回答一个容易误解的问题：**这个项目的用户数据到底存在哪里？**
> 结论先说：**业务数据全在数据库文件里，媒体文件才放磁盘、库里只存路径。**
>
> **相关文档**：
> - [AUDIT.md](AUDIT.md) —— 底层结构的定期审计报告与待办问题跟踪（结构是否健康、能否支撑后续需求）
> - [ER.md](ER.md) —— 表结构图（自动生成）
> - [API.md](API.md) —— 接口文档

---

## 一、两类数据，两种存法

| 数据类型 | 存放位置 | 说明 |
|---|---|---|
| **结构化数据**（用户、帖子、评论、收藏、举报、通知、日志、配置、模块） | `backend/school_life.db` | **一整个 SQLite 文件就是数据库**，数据真身在里面 |
| **媒体文件**（上传的图片 / 视频） | `backend/uploads/<学号>/<YYYYMMDD>/uuid.ext` | 按**用户**分一级、按**日期**分二级；`upload_files` 表只记录 `path` 与 `url` |

**常见误解**：「数据库只存地址吧？」
不是。SQLite 是**嵌入式数据库**，没有独立的数据库服务进程，一个 `.db` 文件即一个完整数据库。
用户密码哈希、帖子正文、**联系方式明文**、日志都在这个文件里。

只有**上传的图片/视频**是"文件放磁盘、库"里存路径"——因为二进制大文件不适合塞进数据库行里。

### 媒体目录为什么按「用户 → 日期」两级分

```
backend/uploads/
├── 20210001/                 ← 一级：用户（学号），硬盘上直接能看出数据归属
│   ├── 20261002/
│   │   └── 9f3c1a2b....png
│   └── 20261003/
│       └── 4d8e7f01....jpg
├── 23190508/
│   └── 20261002/
│       └── b80799f3....png
└── _unknown/                 ← 归属不明的历史遗留文件（需人工确认）
    └── 20260101/
        └── legacy.png
```

| 层级 | 取值 | 为什么这样设计 |
|---|---|---|
| 一级 | **学号** | 硬盘上能直接认出是谁的数据；删除用户时整目录删除，不会误删他人文件 |
| 二级 | **上传日期** | 保留时间维度，同时避免单个用户目录下文件过多 |
| 文件名 | **uuid.ext** | 杜绝中文名、重名覆盖与路径穿越 |

> 早期版本只按 `YYYYMMDD/` 分目录，硬盘上无法区分归属，已通过
> `backend/scripts/migrate_upload_layout.py` 迁移到上述结构。

### 数据库里存什么

`upload_files` 表**只存地址，不存文件本身**：

| 字段 | 示例 | 说明 |
|---|---|---|
| `path` | `20210001/20261002/9f3c1a2b....png` | 相对 `uploads/` 的路径 |
| `url` | `/api/v1/files/20210001/20261002/9f3c1a2b....png` | 前端直接引用 |
| `user_id` | `2` | 上传者 |
| `post_id` | `17` | 挂载的帖子（可为空） |
| `original_name` | `我的伞.png` | 原始文件名单独留一份 |
| `media_type` / `size` / `mime` | `image` / `10241` / `image/png` | 类型与大小 |

好处：换存储根目录、换机器、甚至换成对象存储时，**数据库一行都不用改**（前提是相对路径规则不变）。

---

## 二、⚠️ 媒体地址存了两处（改布局必须同时改）

这是**实际踩过的坑**，务必记住：

| # | 存在哪里 | 内容 |
|---|---|---|
| 1 | `upload_files` 表 | `path`（相对路径）+ `url`（访问地址） |
| 2 | **`posts.media` 列** | JSON 数组，每项含 `url` / `path` / `name` / `type` / `size` |

页面渲染读的是**第 2 处**（帖子详情/列表接口返回的 `media`），而文件是否存在的判断
看的是第 1 处。**只改一处 → 页面用旧地址请求 → 404**（文件明明在磁盘上）。

> 当初把「日期/文件」迁移到「学号/日期」时只改了第 1 处，
> 结果帖子 17 的配图请求 `/api/v1/files/20261002/xxx.png` 报 404。

**修复命令**

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\fix_media_references.py --check   # 预演
.\.venv\Scripts\python.exe scripts\fix_media_references.py           # 执行
```

判断与重写逻辑集中在 `app/utils/media_refs.py`，迁移脚本与修复脚本共用一份，
不会再出现两边不一致。回归测试见 `tests/test_media_reference.py`。

---

## 三、实测数据（开发库，跑过演示数据之后的状态）

| 表 | 内容 |
|---|---|
| `users` | 学号、昵称、角色、状态、`scrypt` 密码哈希 |
| `posts` | 标题、描述、地点、**联系方式（明文）**、状态、审核状态、**media（JSON 地址）** |
| `comments` / `favorites` / `reports` / `notifications` | 评论、收藏、举报、通知 |
| `operation_logs` / `login_logs` | 操作日志与登录日志（含 IP、UA） |
| `system_configs` / `modules` | 配置与模块定义 |
| `upload_files` | **媒体文件的地址**（path/url）与归属（user_id/post_id） |

数据库文件约 **260 KB**（不含媒体文件；媒体在 `uploads/` 目录下）。


---

## 四、备份与恢复

### 备份（两条命令，答辩前建议做一次）

```powershell
# 1. 备份数据库
Copy-Item E:\Project_graduation\backend\school_life.db `
          E:\Project_graduation\backend\school_life.backup.db

# 2. 备份上传的媒体（如果有）
Copy-Item E:\Project_graduation\backend\uploads E:\Project_graduation\backend\uploads_backup -Recurse
```

### 恢复

```powershell
Copy-Item E:\Project_graduation\backend\school_life.backup.db `
          E:\Project_graduation\backend\school_life.db -Force
```

### 重建（不想要旧数据时）

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\dev_init.py --reset   # 清空业务数据并重新生成演示数据
```

> ⚠️ **`--reset` 会删除全部业务数据**（用户、帖子、日志、配置改动都会没）。
> 它会重新写入 16 条演示帖子和 13 个账号，密码回到 `admin123` / `123456`。
> **注意：`--reset` 不会删除 `uploads/` 里的媒体文件**，如需一并清理请手动删目录。

### 删除用户时会发生什么

管理端「用户管理 → 删除」会**级联清理**，不留孤儿指针与孤儿文件：

| 被删除的东西 | 说明 |
|---|---|
| 该用户的全部帖子 | 连同帖子下的**他人评论**、收藏、媒体记录 |
| 该用户发出的评论 / 收藏 / 私信 / 通知 | 物理删除 |
| 该用户相关的举报 | 他是举报人则删除；他是被举报人则保留记录但**置空引用** |
| 该用户的操作日志 | **保留**（审计需要），但把 `user_id` 置空 |
| 磁盘目录 `uploads/<学号>/` | **整个目录删除** |

调用方式：`DELETE /api/v1/admin/users/{id}`，请求体需带
`{"confirm_student_id": "<该用户学号>"}` 做二次确认；仅超级管理员可调用。

删除前可用 `GET /api/v1/admin/users/{id}/media` 查看将影响的文件数量与占用空间。

---

## 五、数据一致性自检

几个脚本用于检查「孤儿指针」「孤儿文件」与媒体键一致性：

```powershell
cd backend

# 检查外键一致性 + 找出磁盘上无人引用的文件
.\.venv\Scripts\python.exe scripts\check_orphans.py

# 顺带删除孤儿文件（释放空间）
.\.venv\Scripts\python.exe scripts\check_orphans.py --clean --unattached-hours 24

# 修剪 posts/comments/messages 的 media JSON 多余键（如 user_dir）
.\.venv\Scripts\python.exe scripts\fix_media_keys.py --check   # 预演
.\.venv\Scripts\python.exe scripts\fix_media_keys.py           # 执行

# 上传目录布局迁移（旧的 日期/文件 结构 → 学号/日期/文件）
.\.venv\Scripts\python.exe scripts\migrate_upload_layout.py --check   # 预演
.\.venv\Scripts\python.exe scripts\migrate_upload_layout.py           # 执行
```

管理端也提供 `GET /api/v1/admin/dashboard/media`，按用户列出磁盘占用与孤儿文件。

---

## 六、Git 与数据文件

`.gitignore` 已排除数据文件，**不会把用户数据提交到仓库**：

```gitignore
*.db
*.sqlite
backend/school_life.db
backend/uploads/*          # 保留 .gitkeep
backend/app/logs/*.log
pip-*/                     # pip 临时目录
```

含义：克隆仓库后数据库是空的，必须执行一次初始化：

```powershell
python scripts\dev_init.py --reset
```

---

## 七、迁移到 MySQL（部署时）

SQLite 换成 MySQL 后，**数据不再是一个文件，而是在 MySQL 服务里**。切换方式：

1. 在 `backend/.env` 里设置连接串：
   ```
   DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/school_life?charset=utf8mb4
   ```
2. 安装驱动：`.\.venv\Scripts\python.exe -m pip install PyMySQL`
3. 建表：`.\.venv\Scripts\python.exe -m flask --app run:app db upgrade`
   或直接导入 `docs/schema_mysql.sql`
4. 备份方式随之改变：用 `mysqldump`，而不是拷贝文件。

**媒体文件仍然在 `backend/uploads/`**，与数据库无关——迁移时别忘了整个目录一起搬
（目录结构是「学号/日期」，搬到新机器后路径不变，所以 `upload_files.path` 无需修改）。

---

## 八、上线前必须处理的数据安全问题

| 问题 | 现状 | 建议 |
|---|---|---|
| 联系方式明文存储 | 帖子 `contact` 字段明文 | 需求要求"公开可见"，可接受；但不要在此存身份证、银行卡 |
| 数据库文件在项目目录内 | `backend/school_life.db` 与代码同级 | 部署时移到独立数据目录并限制权限 |
| 上传目录可被直接遍历？ | 否，`GET /api/v1/files/<path>` 做了路径穿越校验；目录名也经过 `safe_segment()` 过滤 | — |
| 删除用户不可恢复 | 已加二次确认（需输入学号）+ 仅超级管理员可调用 | 生产环境建议再加操作审批留痕 |
| 敏感文件入库 | 平台已在发布前弹安全公告，但**没有技术阻拦** | v2 可考虑关键词检测 + 人工复核 |
| 备份策略 | 无自动备份 | 正式部署建议每日定时 `mysqldump` + 同步备份 `uploads/` |
