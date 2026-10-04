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

| 编号 | 问题 | 严重度 | 状态 | 关闭条件 |
|---|---|---|---|---|
| P1 | `messages.content` NOT NULL 与纯媒体消息冲突 | 🔴 高 | **未处理** | 明确是否允许纯媒体；改表或加接口校验 |
| P2 | `posts.media` 多存 `user_dir` 键 | 🟡 中 | **未处理** | 落库前裁剪；历史数据可选清理 |
| P3 | `ext_json` 零使用，设计未验证 | 🟡 中 | **未处理** | 二手交易模块上线并跑通真实数据 |
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
