# 底层结构审计报告

> **这份文档的用途**：记录对数据库与底层结构的**定期体检**结果，作为以后回看问题的依据。
> 每次审计追加一节，**不要删旧记录** —— 对比历史才能看出「问题是在收敛还是在恶化」。
>
> 与其它文档的分工：
> - `ER.md` —— 表结构长什么样（自动生成）
> - `DATA.md` —— 数据存在哪、怎么备份、两处媒体地址的坑
> - **`AUDIT.md`（本文）** —— 结构是否**健康**、是否**撑得住后续需求**、有哪些**待办问题**

---

## 审计索引

| 序号 | 日期 | 触发原因 | 结论 | 未关闭问题 |
|---|---|---|---|---|
| #1 | 2026-10-04 | v1.2 完成后评估能否支撑后续模块 | 结构健康，可支撑 | 4 项（1 红 2 黄 1 决策） |
| 修复 #1 | 2026-10-04 | 修复审计 #1 的 P1 / P2 / P3 | P1、P2、P3 已关闭 | 2 项（P4、D1） |
| #2 | 2026-10-05 | 评估「管理员 / 普通用户 / 审核员」三级角色与指派链路、同机多账户会话 | **角色层可存、权限层为空、指派关系无表承载；同浏览器只能有一个账户有效** | 见 [ROLE_SESSION_ANALYSIS.md](ROLE_SESSION_ANALYSIS.md)（4 决策点 + 5 项会话缺陷） |
| #3 | 2026-10-05 | 用户相关字段逐个盘点 + 权限问题成因定位 | **表结构无漂移、字段基本够用；根因是 `User.is_admin` 一个布尔值承担了两种语义，波及 20 处判定点** | P5 ~ P9 + D2 / D3，见 [USER_FIELDS.md](USER_FIELDS.md) |
| **修复 #3** | 2026-10-05 | 落地审核员角色与审核指派（v1.4） | **P5、P6、P7 已关闭；D2、D3 已决策并实现**；新增 25 个回归用例 | P8（模块级授权悬空）、P9（token 版本）、会话链路 5 项 |

> **审计 #2 / #3 独立成文**：角色适配性、会话链路与用户字段清单涉及前端 + 后端 + 数据结构三层，
> 篇幅较长，分别放在 [ROLE_SESSION_ANALYSIS.md](ROLE_SESSION_ANALYSIS.md) 与
> [USER_FIELDS.md](USER_FIELDS.md)，本文件只登记索引、待办与结论。

---

# 审计 #1 · 2026-10-04

**范围**：15 张表 / 174 字段 / 数据库 392 KB
**触发**：v1.2（评论楼中楼、点赞、私信）落地后，评估「帖子结构能否兼容二手交易、组队打车、交友等后续模块」
**结论**：**结构健康，能满足后续需求。问题不在表设计，而在两处"设计尚未被真实数据验证过"的地方。**

## 1.1 体检结果总览

| 检查项 | 方法 | 结果 |
|---|---|---|
| 表级差异（模型 vs 库） | `inspect()` 比对表名 | ✅ 无差异（15 张表完全对应） |
| 列级差异 | 逐列比对名称/类型/可空性 | ⚠️ **1 处**（见 1.2-P1） |
| 唯一约束差异 | 比对约束与唯一索引 | ✅ 无差异 |
| 全库外键孤儿 | 每张表每个外键跑 `NOT EXISTS` 反查 | ✅ **0 条** |
| 冗余计数 vs 实际行数 | 19 个帖子逐一核对评论/点赞/收藏 | ✅ **零漂移**（v1.2 的计数维护逻辑正确） |
| 磁盘文件 vs `upload_files` | 8 条记录 vs 8 个文件 | ✅ 无孤儿、无缺失 |
| 清理服务覆盖 | 检查 `utils/cleanup.py` 涉及的表 | ✅ 完整（含 `PostLike`/`CommentLike`/评论媒体） |
| 路由冲突 | `url_map` 去重检查 | ✅ 105 条路由，0 冲突 |

**复查命令**（在 `backend` 目录下）：

```powershell
# 一致性自检（孤儿指针 + 孤儿文件）
.\.venv\Scripts\python.exe scripts\check_orphans.py

# 结构升级检查（应显示 新增列/表/索引 均为 0）
.\.venv\Scripts\python.exe scripts\upgrade_schema.py --check

# 测试与脚手架总量（基线对照）
.\.venv\Scripts\python.exe -m pytest tests -q          # 本次基线：111 passed
```

## 1.2 审计时点的工程现状（基线）

审计时仓库已有的工具与实现（用于后续对比，判断能力是在增强还是退化）：

| 项 | 状态 | 备注 |
|---|---|---|
| pytest | **111 passed** | 本次基线数字，后续审计以此对照 |
| `scripts/recount.py` | ✅ 存在 | **计数对账**：重算 `like_count`/`comment_count`/`favorite_count`/`reply_count` 并比对，`--fix` 自动回写 |
| `scripts/check_orphans.py` | ✅ 存在 | 一致性自检，支持 `--clean` 与 `--unattached-hours N` |
| `scripts/upgrade_schema.py` | ✅ 存在 | 幂等结构升级（只加不删） |
| `app/utils/hot_score.py` | ✅ 存在 | 热度算法：浏览 + 评论×3 + 点赞×2 + 收藏×2，带 24h 时间衰减 |
| `app/utils/cleanup.py` | ✅ 存在 | 级联清理，覆盖 `PostLike`/`CommentLike`/评论与私信媒体 |
| `posts.sort=hot` | ✅ 已接入 | `lost_found/routes.py` 使用 `hot_score()` 排序 |

> 也就是说：审计 #1 时，「计数对账」「热度算法」「未引用媒体清理」**都已经实现了** ——
> 早期版本曾建议过「加 recount 对账脚本」，现在已经落地，本表记录该能力已具备。

## 1.3 发现的问题

### 🔴 P1 · `messages.content` 与 `comments.content` 均为 NOT NULL（纯媒体消息存不了）

| 位置 | 模型声明 | 数据库实际 | 是否一致 |
|---|---|---|---|
| `messages.content` | `nullable=True` | `TEXT NOT NULL` | ❌ **不一致** |
| `comments.content` | `nullable=False` | `TEXT NOT NULL` | ✅ 一致（设计要求必填） |

**成因**：表由早期 `db.create_all()` 建立（当时 `messages.content` 必填），后来模型改成可空，
但**没有同步改表** —— `create_all()` 只建缺失的表，**不给已有表改列**。

**影响**：会**直接卡住 v1.2 已实现的功能** —— "只发图片/只发语音、不带文字"的私信，插入时报
`NOT NULL constraint failed: messages.content`。
现有测试未暴露，因为测试里的消息都带了文字。

**待决策**：
- 若允许「纯媒体私信」→ 需改表（SQLite 改列要重建表；MySQL 用 `ALTER TABLE ... MODIFY`）
- 若不允许 → 应在**接口层明确校验并给出友好提示**，而不是让数据库抛 500
- `comments.content` 若确实要求"评论必须有文字"，模型和表一致，**无需处理**，但建议在接口层把
  "至少要有文字或媒体其一"的规则写清楚

---

### 🟡 P2 · `posts.media` 的 JSON 键比其它表多一个 `user_dir`

实测三个位置的 `media` 数组键：

| 位置 | 键 |
|---|---|
| `posts.media` | `id, mime, name, path, size, type, url, **user_dir**` |
| `comments.media` | `id, mime, name, path, size, type, url` |
| `messages.media` | `id, mime, name, path, size, type, url` |

**成因**：`save_media()` 的返回值里带了 `user_dir`（调试/展示用），前端把它原样回传并落库。

**影响**：不影响读取，但三个表结构不一致，将来做统一媒体渲染组件时要额外兼容；
也让"media 结构统一"这个设计承诺打折扣。

**建议**：落库前过滤掉 `user_dir`（在 `posts_service.save_post` 或接口层裁剪）；
已有数据可选择性清理。**属于数据卫生问题，不影响功能。**

---

### 🟡 P3 · `ext_json` 从未承载过真实数据

```
有 ext_json 的帖子: 0 条（19 条帖子全是失物招领，ext_json 全为 NULL）
```

**好消息**：写入路径**已经存在且可用** ——
`POST /lost_found/posts` 走 `svc.save_post(post, media=media, ext=data.get('ext'))`，
`PUT` 里有 `if 'ext' in payload: svc.save_post(post, ext=payload.get('ext'))`。

**风险**：「用 `ext_json` 承载模块差异字段」是整个模块化设计的核心承诺，
但**从未有数据流过这条路径** —— 校验、序列化、前端渲染都只是理论。

**建议**：下一个模块（二手交易）就用于验证它。若存在隐藏问题（如 JSON 序列化、长度、转义），
只有真实数据能暴露。

---

### ⚪ P4 · 缺复合索引（当前无需处理）

| 缺失索引 | 影响的查询模式 |
|---|---|
| `type + created_at` | 模块内按时间翻页 |
| `type + like_count` | 模块内按热度排序 |
| `type + happened_at` | 按发生时间筛选（拼单截止、失物时间） |
| `status + audit_status` | 审核台组合过滤 |

**现有索引**：`type+status+is_deleted`、`audit_status+created_at` 及 6 个单列索引。

**判断：现在不加**。毕设规模（几十~几千条）SQLite 全表扫描是毫秒级；加索引的代价是写入变慢、
占用空间，且需要改表结构。等真出现性能问题再加 —— 那时可以用 `EXPLAIN` 分析前后对比写进论文。

---

## 1.4 帖子结构对后续需求的适配性

### 可以直接支撑（不用改表）✅

| 后续需求 | 承载方式 |
|---|---|
| 二手交易 | `type='second_hand'` + `ext_json={price, condition, trade_type}` |
| 交友 | `type='friend'` + `ext_json={tags, gender, grade}` |
| 发图 / 视频 / 语音 | `media` JSON 数组（TEXT 存储，无长度限制） |
| 评论 / 点赞 / 收藏 | 三张独立表已就绪，新模块**自动拥有**这些能力 |

`modules` 表已预置 `second_hand` / `group_buy` / `errand`（`enabled=0`），后台启用即可。

### ⚠️ 需要决策：组队打车的「报名」关系没有表承载

「一个帖子招 3 人，用户能**加入**，显示还差 1 人」—— 这不是评论/点赞/收藏，
而是**第三种关系**（用户 ↔ 帖子的「参与」关系）。三个方案：

| 方案 | 做法 | 评价 |
|---|---|---|
| A 塞进 `ext_json` | `{joined_users: [2,5,7], seats_left: 1}` | ❌ 并发下互相覆盖；无法查「我参加过哪些拼单」；统计要遍历 JSON |
| B 新建关联表 | `post_participants(post_id, user_id, status)` | ✅ 正确做法，但需要改表（可用 `upgrade_schema.py` 加，成本低） |
| C 暂不实现 | 只做「发帖 + 评论联系」 | 功能弱，但不动表 |

拼单（`joined_count`/`target_count`）有同样问题；**二手交易与交友没有这个问题**。

---

## 1.5 本次审计的结论与建议

| 维度 | 评价 |
|---|---|
| 表结构完整性 | ✅ 模型与库高度一致（仅 1 处可空性差异） |
| 引用完整性 | ✅ 全库 0 孤儿，唯一约束齐全 |
| 帖子结构扩展性 | ✅ 三类新模块不用改表 |
| 计数一致性 | ✅ 当前零漂移 |
| 清理逻辑 | ✅ 覆盖完整，无孤儿文件 |
| 真正的风险 | ⚠️ 两处「设计未被数据验证」：`ext_json` 与纯媒体消息 |

**建议顺序**：

1. **先修 P1 的决策**（纯媒体消息是否允许）—— 它卡住已实现的功能
2. **做二手交易模块** —— 零结构风险，且能同时验证 `ext_json`
3. 顺手清理 P2 的 `user_dir`
4. P4 索引等有性能数据再说；P3 的报名关系等做组队打车时再决策

---

## 附：本次审计的检查方法（便于复现）

```python
# 1. 模型 vs 数据库逐列比对
from sqlalchemy import inspect
insp = inspect(db.engine)
model_cols = {c.name: c for c in db.metadata.tables[T].columns}
real_cols = {c["name"]: c for c in insp.get_columns(T)}
# 比对 nullable / type / 唯一约束

# 2. 全库外键孤儿（每张表每个外键）
select count(*) from <子表> c
 where c.<外键列> is not null
   and not exists (select 1 from <父表> p where p.<父键列> = c.<外键列>)

# 3. 冗余计数对账
select count(*) from comments where post_id=? and is_deleted=0   -- 对比 posts.comment_count
select count(*) from post_likes where post_id=?                  -- 对比 posts.like_count
select count(*) from favorites  where post_id=?                  -- 对比 posts.favorite_count

# 4. 磁盘 vs 数据库
对比 upload_files.path 集合 与 os.walk(uploads) 的相对路径集合
```

> 只读方式打开数据库，避免误改：
> `sqlite3.connect("file:<路径>?mode=ro", uri=True)`

---

## 待办清单（跟踪用）

> 📌 **本表是审计 #1 时点的快照**（P1~P3 当时确实未处理）。
> 它们已在同日「修复记录 #1」关闭 —— 当前状态请看
> 文末的**统一待办清单**与 [README 第十节](../README.md)（唯一权威口径）。

| 编号 | 问题 | 严重度 | 状态（审计 #1 时点） | 关闭条件 |
|---|---|---|---|---|
| P1 | `messages.content` NOT NULL 与纯媒体消息冲突 | 🔴 高 | 未处理 → 同日已关闭 | 明确是否允许纯媒体；改表或加接口校验 |
| P2 | `posts.media` 多存 `user_dir` 键 | 🟡 中 | 未处理 → 同日已关闭 | 落库前裁剪；历史数据可选清理 |
| P3 | `ext_json` 零使用，设计未验证 | 🟡 中 | 未处理 → v1.3 已关闭 | 二手交易模块上线并跑通真实数据 |
| P4 | 缺 4 个复合索引 | ⚪ 低 | **暂不处理** | 出现性能问题并有 `EXPLAIN` 依据 |
| D1 | 组队打车的「报名」关系无表承载 | ⚠️ 决策 | **待决策** | 选择方案 A/B/C 并记录 |


---

# 修复记录 #1  2026-10-04

**对应审计**：审计 #1
**本轮处理**：P1、P2 已关闭；P3 完成写入链路校验，等待二手交易模块真实上线；P4 / D1 维持原判断。

## P1  纯媒体消息与 NOT NULL

- **决策**：允许「纯图片 / 纯语音」内容，不要求必须带文字。
- **实现语义**：没有文字时，`comments.content` / `messages.content` 存**空字符串 `''`**，
  既满足数据库 `TEXT NOT NULL`，也不会出现 `NULL`。
- **模型对齐**：
  - `Message.content` 从 `nullable=True` 改为 `nullable=False, default=''`
  - `Comment.content` 保持 `nullable=False`，补充 `default=''`
- **没有改表结构**：数据库列保持 `TEXT NOT NULL`，避免 SQLite 重建表。
- **回归测试**：`test_comment_reply_to_user_and_media`、`test_message_with_voice_media`
  现在会断言数据库里的 `content == ''`，证明纯媒体内容可正常入库。

## P2  posts.media 的 user_dir 键

- 新增 `app/utils/uploads.py::canonical_media_list()`，统一只保留
  `id / url / path / name / type / size / mime` 七个键。
- `posts_service.save_post()` 落库前统一裁剪，`user_dir` 等调试字段不会再进入 `posts.media`。
- 新增脚本 `backend/scripts/fix_media_keys.py`（`--check` 预演 / 默认执行），
  可一次性清理 posts / comments / messages 三处历史 media JSON 的多余键。
- **执行结果**：开发库预演发现 3 行帖子 media 含多余键，执行清理 3 行 / 3 个 `user_dir`；
  复检为 0 行、0 个多余键。
- **回归测试**：`test_post_media_matches_upload_record` 现在断言 `posts.media` 的键集合
  必须等于统一键集合，且不含 `user_dir`。

## P3  ext_json 写入链路

- 新增 `posts_service.normalize_ext()`：
  - 必须是 JSON 对象，否则返回 1001；
  - 必须可序列化；
  - 限制最大 4096 字节，防止把 `ext_json` 当数据库用。
- 新增测试 `test_ext_json_roundtrip_and_validation`：真实走 `POST /lost_found/posts`
  写入 `ext`，详情/创建响应能原样回读，非法类型与超大对象会被接口拒绝。
- **后续更新（v1.3）**：二手交易模块已经上线：
  - `posts.type='second_hand'` + `ext_json={price, original_price, condition, trade_type}`；
  - `POST /lost_found/posts` 支持 `?type= / body.type` 选择模块，按模块做 ext 校验；
  - 前端发布页支持选择已启用模块；二手交易表单支持价格 / 成色 / 交易方式，
    状态文案为 `在售中 / 已售出 / 已过期 / 已下架`，交易时间必填；
    列表 / 详情 / 卡片都能展示价格与成色；
  - `dev_init --reset` 会生成 3 条二手交易演示数据，开发库中也已写入 2 条真实记录；
  - `test_second_hand_ext_flow` 已覆盖「发布  审核  按 type 列表  详情回读」。
  - 至此审计 #1 对 P3 的关闭条件已满足。

## 更新后的待办

| 编号 | 问题 | 严重度 | 状态 | 关闭条件 |
|---|---|---|---|---|
| P1 | 纯媒体消息与 NOT NULL 冲突 |  高 |  **已关闭** | 允许纯媒体；空字符串入库；模型与库对齐 |
| P2 | `posts.media` 多存 `user_dir` |  中 |  **已关闭** | 落库前统一裁剪；历史数据已清理 |
| P3 | `ext_json` 零使用，设计未验证 |  中 |  **已关闭** | 二手交易模块已上线；ext 校验、列表、详情、真实数据全部跑通 |
| P4 | 缺 4 个复合索引 |  低 |  暂不处理 | 出现性能问题并有 `EXPLAIN` 依据 |
| D1 | 组队打车的「报名」关系无表承载 |  决策 |  待决策 | 选择方案 A/B/C 并记录 |
| **P5** | `User.is_admin` 语义混淆，auditor 等价于 admin（20 处判定点） | 🔴 高 | ✅ **已关闭** | 拆出 `is_staff` / `is_admin`；64 个后台接口全部按能力归类 |
| **P6** | `comments/routes.py:328` 隐藏的管理员特权分支 | 🔴 高 | ✅ **已关闭** | 改为 `user.is_admin`；新增「审核员不能走用户端无限删评」回归测试 |
| **P7** | 审核员的帖子免审核、且可编辑任意帖子 | 🔴 高 | ✅ **已关闭** | `can_edit` / `build_post` / 编辑送审三处只放行真管理员；禁止自审 |
| **P10** | 角色等级有四套并行口径，导致 admin 拿不到 `user.role` | 🔴 高 | ✅ **已关闭** | 收敛成一套：`ROLES` 3 值 + `ADMIN_ROLES` 2 值 + 管理员通配能力；`super_admin` 彻底移除 |
| **P8** | `admin_module_access` 无写入路径、`modules.allow_roles` 无校验 | 🟡 中 | **未处理** | 补接口接线，或标注「未实现」并从后台界面移除该字段 |
| **P9** | 无 `token_version`，改密/封禁后旧 token 仍有效 24 小时 | 🟡 中 | **未处理** | 加列并在 `_load_user` 校验版本 |
| **D2** | 审核员是「严格只看指派」还是「指派 + 公共池」 | ⚠️ 决策 | ✅ **已决策** | 采用**混合模式**：指派 + 公共池自助认领（先到先得，24 小时超时退回） |
| **D3** | 是否新建 `post_audit_assignments` 记录改派历史 | ⚠️ 决策 | ✅ **已决策** | 建 `post_audit_logs` 流水表（assign/claim/release/approve/reject + 耗时） |

> **P5 ~ P9 的完整分析**（字段逐个清单、20 处判定点、改造对照表）见
> [docs/USER_FIELDS.md](USER_FIELDS.md)。

---

## 四、管理员唯一性与移交（v1.4 补丁 2 · 2026-10-05）

**需求**：系统**只允许存在一个管理员**。管理员若想改自己的角色，等于"让出管理员"，
不能直接降级（否则后台再也没人能任命角色，会锁死）。

### 4.1 两阶段移交模型

```
t=0                A 发起移交（指定 B）      B 获得管理员身份，但**按原角色工作**
t=0 ~ 24h          A 仍是管理员、功能照常      B 用原本的权限（审核员继续审核），
                   A 随时可撤销                但拿不到任何管理员特权；发帖仍需审核
t=24h（懒执行）      A 降为普通用户            B 正式上任，拿到管理员全部能力
```

**冻结到底冻结了什么（方案 A，`is_frozen` 的语义）**：

| 维度 | 冻结期行为 |
|---|---|
| `role` | 已是 `admin`（身份上已接管） |
| `handover_prev_role` | 记住接管前的角色，用于授权与恢复 |
| `capabilities` | **取自原角色** —— 原本是审核员就还能审帖、删评论（**工作不停**） |
| `is_admin` | **强制 false** —— 因此发帖仍走审核、不能编辑他人正文 |
| 对外身份 | 显示**原角色**（如「内容审核员」），不显示「管理员」 |
| 管理员专属能力 | 全部拿不到（配置 / 模块 / 角色 / 回收站 / 日志 / 媒体清理） |

> ⚠️ **这一步是被评审问出来的漏洞**：最初实现是"冻结期一刀切 403 所有后台接口"，
> 看起来安全，实际有三个问题：
> ① **接任者若是审核员，24 小时内无法审核** —— 交接把正常工作搞停了；
> ② 冻结只拦了后台**路由**，而 `is_admin` 在 `build_post`（发帖免审）/
>    `can_edit`（编辑他人正文）里还有副作用，**等于提前行使了管理员特权**；
> ③ 冻结者对外仍显示「管理员」徽章，别人以为他能管事。
>
> 修正为"按原角色降级"后，三个问题同时消失：
> **拦截点从"路由层"下沉到"语义层"（`is_admin` / `capabilities`）**，
> 所有依赖身份的判断点（含不在后台路由里的）自动跟着正确。

### 4.2 硬约束（后端强制，不靠约定）

| 约束 | 拒绝方式 |
|---|---|
| 管理员不能改自己的角色 | 1001 + 提示走「管理员移交」 |
| 不能把别人直接改成管理员 | 1001「系统只允许存在一个管理员」 |
| 不能删除管理员账号 | 1001 |
| 发起移交时，其它残留管理员一并降级 | 自动收敛成一个（防御性清理） |
| 审核员够不到移交接口 | 403（独立能力 `admin.handover`） |
| 撤销移交 → 恢复**接管前的角色** | 原本是审核员就还原成审核员，不会掉成普通用户 |

**时间口径**：统一用**北京时间**（UTC+8 固定偏移，`utils/handover.py::now_beijing`）。
不用 `zoneinfo`：精简环境可能缺 tzdata 包，而中国不实行夏令时，固定偏移即标准北京时间。
**懒执行**：没有定时任务，24 小时到点后由下一次后台请求触发结算；
`/status` 下发 `server_now` 供前端校准倒计时。

### 4.3 同时修掉的一个真实漏洞

`BaseModel.to_dict()` 会遍历**全部列**，而 `User.to_dict` 早期只做了
`if with_sensitive: data['email'] = ...` —— 看起来是"按需下发敏感字段"，
**实际邮箱与手机号一直都在每个用户响应里**（包括普通用户列表）。
现在改为 `with_sensitive=False` 时显式 `exclude` 掉这两列。

### 4.5 前端 UI 修正

| 问题 | 处理 |
|---|---|
| 用户管理「操作」列 4 个中文按钮合计约 290px、列宽只有 230px → **必然换行错位** | 改为「1 个主操作（封禁/解封）+『更多』下拉」，列宽收到 150px |
| 审核员看到「重置密码 / 删除」按钮，点了 403 | 按 `capabilities` 隐藏，改为 **不再显示** |
| 审核员进详情页会白挨两个 403 提示（发帖记录 + 日志并发请求） | 按能力跳过这两个请求，并隐藏对应区块 |
| 审核员不知道自己的权限边界 | 列表页与详情页各加一条说明（能做 / 不能做） |
| **「接任者」下拉一个都选不了**（逻辑死锁） | 候选从"现有管理员（排除自己）"改为**"除自己外的全部正常账号"**；见下 |
| 详情页「调整角色」里列出「管理员」，点了必被拒 | 下拉**过滤掉 `admin`**，只保留普通用户 / 内容审核员 |

> **死锁复盘**：最初 `list_admins(exclude_id=自己)` 作为接任者候选 ——
> 而系统只允许一个管理员，排除自己后**永远是空列表**，移交功能实际不可用。
> 接任者的正确语义是"从普通用户 / 审核员里挑一个，选中后升为管理员"。
> 已补回归测试 `test_handover_candidates_are_not_admins` 锁死这个语义。

### 4.6 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests -q` | **160 passed**（新增 12 个移交给用例 + 候选语义 + 冻结审核员场景） |
| `scripts/verify_admin_handover.py`（真实 HTTP） | **24 / 24 通过**，跑完自动还原演示环境 |
| `scripts/verify_auditor_handover.py`（新增，真实 HTTP） | **25 / 25 通过** —— 专门验证"接任者是审核员"这个场景 |
| 线上实测：接任者下拉 | **13 个候选**（普通用户 + 审核员），管理员自己不在其中 |
| 迁移 | 开发库已加 5 列（`users.handover_*`），复检 0/0/0 |
| 前端 build + check | 成功 / 0 处问题 |
| `scripts/reset_demo_admin.py` | 新增：验证脚本被中途打断后清理残留移交、恢复演示环境 |

---

## 三、角色结构收敛（v1.4 补丁 · 2026-10-05）
**触发**：`admin` 看不到「调整角色」按钮 —— 排查发现是**角色等级的表达方式有四套并行**，
口径两两不一致。本轮把等级结构收敛成一套。

### 3.1 收敛前后的对比

| 项 | 收敛前 | 收敛后 |
|---|---|---|
| 可分配角色 `ROLES` | 7 个 | **3 个**：`user` / `admin` / `auditor` |
| `ADMIN_ROLES`（能进后台） | 6 个 | 2 个：`admin` / `auditor` |
| `TRUE_ADMIN_ROLES`（真管理员） | admin + super_admin | 只留 `admin` |
| `ROLE_PERMISSIONS` 键数 | 7 | 6（3 个现行 + 3 个预留） |
| 管理员能力 | 逐项列 16 项 | **通配 `*`**（以后新增能力自动覆盖，不会漏） |
| `is_super_admin` 属性 | 存在（admin 也算） | **已删除** |
| `super_admin_required` 装饰器 | 存在 | **已删除**（它从来就等价于 `admin_required`） |
| 下发 `is_super_admin` 字段 | 有 | **已移除** |

### 3.2 三处真矛盾的处置

| 矛盾 | 处置 |
|---|---|
| 能力表把 `user.role` 只给了 super_admin，`is_super_admin` 却认为 admin 也算 | ✅ **管理员拿到 `user.role`** —— 「调整角色 / 任命审核员」现在可用 |
| `TRUE_ADMIN_ROLES` 含 super_admin 但无此账号 | ✅ **`super_admin` 彻底移除**（常量、文案、属性、装饰器、下发字段全删） |
| `not is_super_admin` 拦"管理员动管理员"→ 判断恒为假 → 管理员互相不能动 | ✅ **改为管理员之间完全平级**（可互相封禁 / 重置密码 / 删除），只保留"不能操作自己" |

### 3.3 预留角色的处理（按需求：注释保留，以后要用再启用）

`user_admin` / `module_admin` / `moderator` 三个角色：

- **常量定义**：注释保留在 `constants.py`，并写明三步启用方法；
- **中文名**：存进 `RESERVED_ROLE_LABELS`；
- **能力初稿**：`ROLE_PERMISSIONS` 里保留（键名用字符串字面量）；
- **不在 `ROLES` 里** → 因此**接口拒绝分配、前端下拉框不显示**，等于"放着不生效"。

> 启用一个预留角色只需三步（不改数据库）：加进 `ROLES` / `ROLE_LABELS` / `ADMIN_ROLES`，
> 前端菜单与下拉框会自动跟随。

### 3.4 当前的角色结构（唯一权威口径）

| 角色 | 中文 | 后台访问 | 能力项 | 说明 |
|---|---|---|---|---|
| `user` | 普通用户 | ❌ | 0 | — |
| `auditor` | 内容审核员 | ✅ | 9 | 内容处置 + 管理普通用户；**不能改角色 / 重置密码 / 看用户明细 / 碰系统** |
| `admin` | 管理员 | ✅ | 通配 | **最高等级**，等价于此前的 super_admin |

### 3.5 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests -q` | **144 passed**（新增 6 个角色结构用例） |
| 线上实测：admin 任命审核员 | ✅ code=0，`role=auditor / is_staff=true / is_admin=false` |
| 线上实测：4 个预留角色均被拒绝分配 | ✅ code=1001「角色取值非法」 |
| 线上实测：审核员访问配置 / 日志 / 模块 | ✅ 全部 2003 |
| 线上实测：审核员尝试改角色 | ✅ 2003 |
| 线上实测：`/common/enums` 下拉框 | ✅ 只剩 user / admin / auditor |
| 前端 build + check | ✅ 成功 / 0 处问题 |

---

# 修复记录 #3 · 2026-10-05（v1.4 审核员角色与审核指派）

**对应审计**：#2（角色适配性 / 会话链路）、#3（用户字段与成因）
**目标需求**：新增「内容审核员」角色 —— 由管理员指定、可多位、能像普通用户一样发帖、
有后台页面（删评论 / 管理审核后帖子 / 管理普通用户），但**没有任命审核员的权利**。

## 一、根因修复：拆开一个布尔值的两种语义

```python
# 修复前：能进后台 == 是管理员（引入 auditor 后立刻失效）
def is_admin(self):  return self.role in ADMIN_ROLES

# 修复后：两个语义分开
def is_staff(self):  return self.role in ADMIN_ROLES          # 能不能进后台
def is_admin(self):  return self.role in TRUE_ADMIN_ROLES     # 是不是真管理员
```

新增 `constants.ROLE_PERMISSIONS`（角色 → 能力集合），`admin_required` 支持
`capability=` 参数；**64 个后台接口全部按能力归类**（`@admin_required` 无参调用清零）。

## 二、权限边界（按需求落定）

| 能力 | 管理员 | 内容审核员 |
|---|---|---|
| 概览统计 | ✅ | ✅ |
| 审核内容（通过 / 拒绝 / 批量） | ✅ | ✅ |
| 内容管理（删帖 / 置顶 / 改状态） | ✅ | ✅ |
| **修改他人帖子正文** | ✅ | ❌ 刻意不给（改内容属发布者权利） |
| 评论管理（物理删除） | ✅ | ✅ |
| 举报处理（含联动删帖 / 封禁） | ✅ | ✅ |
| 用户列表 / 封禁解封 / 批量封禁 | ✅ | ✅（**仅普通用户**） |
| 用户详情 / 发帖记录 / 登录日志 / 重置密码 | ✅ | ❌ |
| 模块管理 / 系统配置 / 日志 / 回收站 / 媒体清理 | ✅ | ❌ |
| 调整角色（任命审核员） | 超管 | ❌ |

> **自审禁令**：谁都不能审自己发的帖子（管理员也不例外）。审核员发帖与普通用户一样
> 进入待审队列，由其他审核员或管理员处理。

## 三、审核指派 / 认领（D2、D3 决策落地）

- **数据**：`posts` 加 `assignee_id / assigned_by / assigned_at / assignment_expires_at`；
  新建 `post_audit_logs` 流水表（只追加，可 SQL 聚合工作量）。
- **管理员**：可指派 / 改派 / 收回；「先到先得」只约束审核员，管理员随时可覆盖（留流水）。
- **审核员**：可认领公共池（**原子条件 UPDATE**：`WHERE assignee_id IS NULL`），
  并发下第一个写入者赢，第二个收到 `4005 已被 XX 认领`。
- **超时**：认领 24 小时后自动退回公共池（懒执行，不需要定时任务）。
- **视角**：待审台支持「全部 / 我的 / 公共池」，别人已认领的默认不出现。

## 四、验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests -q` | **138 passed**（原 113 + 新增 25） |
| `scripts/smoke_test.py` | **55 / 55 通过** |
| `scripts/verify_auditor_flow.py`（新增，打真实 HTTP） | **47 / 47 通过** |
| `scripts/upgrade_schema.py` | 开发库已升级；复检 0 列 / 0 表 / 0 索引 |
| 前端 `pnpm run build` | 成功 |
| 前端 `pnpm run check` | 45 个文件，0 处问题 |

## 五、本轮顺带修掉的两个隐藏缺陷

1. **`purge_overflow` / `purge_post` 未清理审核流水** → 彻底删除帖子时
   `post_audit_logs.post_id` 违反 NOT NULL（回归测试直接暴露）。已在两处补级联清理；
   `purge_user` 则把流水的 `actor_id` / `assignee_id` 置空（保留审计价值，解除引用）。
2. **`comments/routes.py` 的隐藏管理员分支**（P6）：审核员原本可在用户端接口里
   跳过 5 分钟限制物理删除任意评论。现仅真管理员可走该分支。

## 六、仍未关闭

| 编号 | 问题 | 说明 |
|---|---|---|
| P8 | 模块级授权悬空 | `admin_module_access` 仍无写入接口；`module_permission_required` 已改为**未授权即拒绝**（安全默认），但「按模块分权」尚未启用 |
| P9 | 无 `token_version` | 改密 / 重置密码 / 封禁后旧 token 仍有效至过期（24 小时） |
| 会话 | 同机多账户 5 项缺陷 | 见 [ROLE_SESSION_ANALYSIS.md](ROLE_SESSION_ANALYSIS.md) 3.5 节（storage 同步 / sessionStorage / refresh 死代码等） |

---

# 统一待办清单（截至 2026-10-05，唯一权威口径）

> 审计 #1 ~ #3 与两次修复记录里的条目已在此合并去重。
> **其它章节里的"未处理"字样均为当时快照**，以本表为准。
> 同一份内容在 [README 第十节](../README.md) 有面向读者的简版。

## 已完成（已关闭）

| 编号 | 事项 | 关闭于 |
|---|---|---|
| P1 | `messages.content` NOT NULL 与纯媒体消息冲突 | 修复记录 #1（空字符串入库） |
| P2 | `posts.media` 多存 `user_dir` 键 | 修复记录 #1（统一裁剪 + 历史清理） |
| P3 | `ext_json` 零使用，设计未验证 | v1.3（二手交易上线跑通） |
| P5 | `User.is_admin` 语义混淆，auditor 等价于 admin | 修复记录 #3（拆 `is_staff` / `is_admin`，62 接口按能力归类） |
| P6 | `comments/routes.py` 隐藏的管理员特权分支 | 修复记录 #3（改为能力判定 + 回归测试） |
| P7 | 审核员的帖子免审核、可编辑任意帖子 | 修复记录 #3（三处只放行真管理员；禁止自审） |
| P10 | 角色等级四套口径不一致，admin 拿不到 `user.role` | 角色结构收敛（`super_admin` 移除；管理员通配能力） |
| D2 | 审核员是"严格指派"还是"指派 + 公共池" | 采用混合模式（指派 + 认领，先到先得，24h 超时退回） |
| D3 | 是否记录改派历史 | 建 `post_audit_logs` 流水表 |
| — | 单一管理员 + 移交（含冻结期按原角色工作） | 迁移补丁 2 |
| — | 用户管理页操作列错位 / 越权按钮可见 | 迁移补丁 2（"更多"下拉 + 按能力隐藏） |
| — | `User.to_dict` 敏感字段其实一直下发 | 迁移补丁 2（显式 exclude） |
| — | 接任者下拉永远为空（逻辑死锁） | 迁移补丁 2（候选改为"非管理员账号"） |
| — | 撤销移交会丢失原角色 | 迁移补丁 2（`handover_prev_role` 恢复） |

## 未完成 / 待决策

| 编号 | 事项 | 严重度 | 状态 | 关闭条件 |
|---|---|---|---|---|
| **P4** | 缺 4 个复合索引 | ⚪ 低 | 暂不处理 | 出现性能问题并有 `EXPLAIN` 依据 |
| **P8** | 模块级分权未启用（表无写入接口 / `allow_roles` 不生效） | 🟡 中 | 未处理 | 补授权写入接口并接线；或从后台界面移除并标注"未实现" |
| **P9** | 无 `token_version`，改密后旧 token 仍有效 | 🟡 中 | 未处理 | 加列并在 `_load_user` 校验版本 |
| **S1** | 被动登出会丢当前页面（草稿无提示） | 🟡 中 | 未处理 | 发布页加 `onBeforeRouteLeave` 草稿保护 |
| **S2** | `/auth/refresh` 是死代码，refresh token 从未使用 | 🟡 中 | 未处理 | 拦截器对 2002 静默刷新再重试 |
| **S3** | 登出为纯客户端行为，token 过期前仍有效 | 🟡 中 | 未处理 | 同 P9 |
| **S4** | 改密码 / 重置密码不失效旧 token | 🟡 中 | 未处理 | 同 P9 |
| **S5** | 轮询定时器是模块级单例，易漏收口 | ⚪ 低 | 未处理 | 定时器移入 store state |
| **会话** | 同浏览器无法双账户并行（一个登出连带另一个） | 🟡 中 | 未处理 | 见 ROLE_SESSION_ANALYSIS 4.1（`sessionStorage` 隔离 + token 版本） |
| **D1** | 组队打车的「报名」关系无表承载 | ⚠️ 决策 | 待决策 | 做该模块时选方案 A/B/C |
| — | 组队打车 / 交友两类模块 | — | 待做 | 填 `ext_json` + 前端表单，**不需要改表** |
| — | 移动端拆分 / Docker 部署（v2.0） | — | 未开始 | — |

## 预留未启用（结构已就位，当前不影响使用）

| 预留项 | 现状 | 启用方式 |
|---|---|---|
| `moderator` / `user_admin` / `module_admin` | 常量与能力初稿已写并注释；不在 `ROLES` 里 → 拒绝分配、前端不显示 | 加回 `ROLES` / `ROLE_LABELS` / `ADMIN_ROLES`（不改库） |
| `admin_module_access` + `module_permission_required` | 表已建、装饰器已写，**零调用、无写入接口** | 见 P8 |
| `email` / `phone` 列 | 已建列，仅管理员可见，无业务逻辑 | 接短信 / 邮箱登录时启用 |
| 服务端 token 黑名单 | `logout` 注释里留了位置 | 见 P9 |
| WebSocket 私信 | `conversation_key` 已按会话设计 | 替换 `startPolling` 实现 |
