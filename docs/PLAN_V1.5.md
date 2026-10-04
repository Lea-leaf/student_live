# 实施计划 v1.5：拼单 / 跑腿 / 日常 三个模块

> ## ✅ 本计划已实施完成（2026-10-05）
>
> | 项 | 结果 |
> |---|---|
> | 实施状态 | **全部 8 个步骤完成**，见第六节 |
> | 测试 | **`pytest tests -q` → 167 passed**（计划预估基线 160 + 新增用例） |
> | 结构变更 | **0 表 / 0 列 / 0 索引**（`upgrade_schema.py --check` 已验证） |
> | 复检记录 | 见 [AUDIT.md](AUDIT.md) 的「审计 #4」 |
> | 与计划的偏差 | 无实质偏差；额外落地了"统一发布入口 `/publish`、标题固定、类型由页面内选择"（见审计 #4 的 4.2 节） |
>
> **本文件保留为需求与决策的依据**（第七节的 17 条决策是权威来源）。
> 如需了解**实际实现细节**，看 `docs/AUDIT.md` 审计 #4；如需**继续开发**（组队打车 / 交友），
> 照本文件的模式复用即可 —— **仍然不需要改表**。

---

> **本文用途**：把已定稿的需求翻译成可直接执行的改动清单（**现已执行完毕**）。
> **核心约束**：**不改数据库**（不加表、不加列、不改状态常量）。
> 全部依赖已有的 `posts.ext_json` 机制 —— 这是"加模块不改表"设计的一次完整验证。
>
> 需求已由项目负责人逐条拍板（见第七节「已确认决策」），**决策以第七节为准**；
> 如与实现代码不一致，以代码 + `docs/AUDIT.md` 审计 #4 为准。

---

## 一、目标与边界

### 要做的

| # | 内容 |
|---|---|
| 1 | 三个模块可在前台发布、审核、展示（拼单 / 跑腿 / 日常） |
| 2 | 拼单：`ext_json` 存目标人数、当前人数、开始日期；**单主可随时修改人数** |
| 3 | 拼单：**「我要拼」意向标记** —— 复用已有的 `post_likes`，不新建表（见 2.1 与 4.5） |
| 4 | 详情可见性改为**按模块配置**（当前是全局硬编码，会卡住拼单） |
| 5 | 状态选项与筛选器**按模块**给出（避免日常出现两个"已关闭"） |
| 6 | 前端按模块渲染表单与状态文案（沿用已有机制） |

### 明确不做

| 不做 | 原因 |
|---|---|
| 不做「报名/加入」**关系表** | 意向表达复用 `post_likes`（v1.2 已建、已有测试覆盖），无需 `post_participants` |
| 不做自动成团 | 人数由单主手填，自动判断不可靠 → 单主手动改状态 |
| 不加数据库列、不改 `POST_STATUSES` | 硬约束 |
| 跑腿不做"接单"流程 | 单方发帖，看到的人私下联系 |
| 日常不做心情/标签字段 | 负责人明确："日常就用通用帖子就行" |
| 不做"我要 3 份"这类**数量**意向 | `post_likes` 是"一人一条"，无法表达份数（见 2.1 限制说明） |

---

## 二、需求定稿（三张表）

### 2.1 拼单 `group_buy`

| 项 | 定稿 | 落点 |
|---|---|---|
| 目标人数 | **必填**，整数 1–999 | `ext_json.target_count` |
| 当前人数 | **必填**，整数 0–999；**允许 > 目标人数**（单主自行判断） | `ext_json.current_count` |
| 开始日期 | **必填**，日期（非时间） | `ext_json.start_date`，格式 `YYYY-MM-DD` |
| 联系方式 | 选填 | `posts.contact`（没填存 `''`，不能存 `NULL`） |
| **参与意向** | **「我要拼」按钮** —— 复用 `POST /likes/posts/{id}`（幂等切换） | `post_likes` 表，**零结构改动** |
| 修改人数 | **仅单主**，可随时改 `current_count` 与 `target_count` | 新接口，见 3.3 |
| **按意向同步** | 单主可一键把 `current_count` 设为"意向人数" | 复用 3.3 接口 + 前端读 `like_count` |
| 状态文案 | 招募中 / 已结束 / 已取消 | `ongoing` / `claimed` / `closed` |
| 审核 | 需要（走全局 `post_audit_enabled`） | — |

**「我要拼」的设计说明**

点赞与意向是**同一件事**，所以直接复用，不新建关系：

| 需求 | 复用方式 |
|---|---|
| 我想参加 | 点「我要拼」→ `POST /likes/posts/{id}`（已存在、幂等、有计数、有通知） |
| 谁想参加 | 点赞列表（`post_likes` 按 `post_id` 查，本来就能查） |
| 还差几人 | `target_count - current_count` |
| 取消意向 | 再点一次（幂等切换，已实现） |

**限制（必须在前端文案上讲清楚）**：

- `post_likes` 是 **UNIQUE(user_id, post_id)** → **一人只能表达一次**，无法表达"我要 3 份"
- 「意向人数」(`like_count`) 与「当前人数」(`current_count`) **可能不一致**：
  有人点了意向但单主还没改人数，或单主线下收到的人没点赞
  → 所以**两者都显示**，并给单主一个"按意向数同步"按钮，而不是自动覆盖

**`ext_json` 示例**

```json
{ "target_count": 5, "current_count": 2, "start_date": "2026-10-10" }
```

### 2.2 跑腿 `errand`

| 项 | 定稿 | 落点 |
|---|---|---|
| 特有字段 | **无** | `ext_json = {}` |
| 期望时间 | 复用现成的"时间"字段 | `posts.happened_at`（前端文案改成"期望时间"，**必填**） |
| 联系方式 | **必填** | `posts.contact`（靠它私下联系） |
| 状态文案 | 进行中 / 已完成 / 已取消 | `ongoing` / `claimed` / `closed` |
| 审核 | 需要 | — |

### 2.3 日常 `daily`

| 项 | 定稿 | 落点 |
|---|---|---|
| 特有字段 | **无** | `ext_json = {}` |
| 联系方式 | 选填 | `posts.contact` |
| 状态文案 | 正常 / 已关闭 | `ongoing` / `closed` |
| 审核 | 需要 | — |

> **待补**：`daily` 目前**不在** `default_modules()` 里
> （现有序：`lost_found`(启用/内置) → `second_hand`(启用) → `group_buy`(禁用) → `errand`(禁用)）。
> 需要在常量与种子数据里补上（见 3.1）。
>
> 另外两个细节：
> - `group_buy` / `errand` 的 `description` 还写着"（v2.x 规划）"，实现后应改成实际描述
> - `modules` 表里可能还有管理员手工新增的 `other` 模块（种子数据里没有，但后台加过）；
>   **不要**因为种子数据里没有就去删除它

---

## 三、后端改动（5 处）

### 3.1 常量与模块登记

**文件**：`backend/app/utils/constants.py`

```python
# 第 222-226 行附近，补一个常量
MODULE_DAILY = 'daily'
```

**文件**：`backend/app/models/module.py` — `default_modules()`（第 48 行起）

在 `errand` 之后补一段（`enabled=False`，与其它新模块一致 —— "做完一个启用一个"）：

```python
{
    'code': MODULE_DAILY,
    'name': '日常',
    'icon': 'ChatDotRound',
    'description': '校园日常分享与闲聊',
    'sort_order': 45,
    'enabled': False,
    'is_system': False,
},
```

同时给已有的 `group_buy` / `errand` 检查 `icon` 字段是否为空（当前 `group_buy` 用 `ShoppingBag`、
`errand` 用 `Bicycle`，如需调整由负责人定）。

> **注意**：`default_modules()` 只在 `flask init-db` / `dev_init.py` 时写入，
> 已存在的库不会自动更新 → 对已有库要用后台"模块管理"新增，或跑一次 `dev.py --reset`。
> **不要**为了这条去改数据库结构。

### 3.2 ext 校验分支

**文件**：`backend/app/modules/posts_service.py` — `validate_module_ext()`（第 364-392 行）

在 `if module_code == MODULE_SECOND_HAND:` 之后追加：

```python
if module_code == MODULE_GROUP_BUY:
    # 目标人数：必填整数 1-999
    target = ext.get('target_count')
    if target in (None, ''):
        raise ValidationError('拼单必须填写目标人数 target_count')
    try:
        target = int(target)
    except (TypeError, ValueError):
        raise ValidationError('目标人数必须是整数') from None
    if not (1 <= target <= 999):
        raise ValidationError('目标人数需在 1-999 之间')
    ext['target_count'] = target

    # 当前人数：必填整数 0-999（允许大于目标人数，由单主自行判断）
    current = ext.get('current_count')
    if current in (None, ''):
        raise ValidationError('拼单必须填写当前人数 current_count')
    try:
        current = int(current)
    except (TypeError, ValueError):
        raise ValidationError('当前人数必须是整数') from None
    if not (0 <= current <= 999):
        raise ValidationError('当前人数需在 0-999 之间')
    ext['current_count'] = current

    # 开始日期：必填，YYYY-MM-DD
    start = ext.get('start_date')
    if start in (None, ''):
        raise ValidationError('拼单必须填写开始日期 start_date')
    if not isinstance(start, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', start):
        raise ValidationError('开始日期格式应为 YYYY-MM-DD')
    try:
        datetime.strptime(start, '%Y-%m-%d')
    except ValueError:
        raise ValidationError('开始日期不是有效日期') from None
    ext['start_date'] = start

# 跑腿 / 日常：无特有字段，通用校验即可（normalize_ext 已处理）
```

**需要的 import**（文件顶部确认是否已存在）：`re`、`datetime`、`ValidationError`、
`MODULE_GROUP_BUY`。

### 3.3 新增接口：单主修改拼单人数

**文件**：`backend/app/modules/lost_found/routes.py`
（该模块承担全部帖子的发布/详情/状态流转，`?type=` 区分模块）

新增路由（放在状态流转接口附近）：

```
PATCH /api/v1/lost_found/posts/<int:post_id>/count
```

| 项 | 规则 |
|---|---|
| 权限 | **仅帖子作者**（`post.user_id == current_user.id`）；管理员也可（沿用 `can_edit`） |
| 模块限制 | 只对 `post.type == 'group_buy'` 生效，其它模块返回 1001 |
| 请求体 | `{"current_count": 3, "target_count": 5}`，**两者都可选**，至少传一个 |
| 校验 | 整数、范围 0–999（目标人数 1–999）；复用 3.2 的规则 |
| 行为 | 读出 `ext_json` → 改键 → **整个写回**（`ext_json` 不能原子改单键） |
| 返回 | 更新后的帖子 `to_dict()` |
| 日志 | `write_operation_log('update_count', module=post.type, target_type='post', target_id=post.id, detail={'current_count':..,'target_count':..})` |

**实现要点**（`ext_json` 的坑）：

```python
import json
ext = post._ext_dict()          # 或 json.loads(post.ext_json or '{}')
ext['current_count'] = new_current
post.ext_json = json.dumps(ext, ensure_ascii=False)   # ← 必须整体重新赋值
db.session.commit()
```

> SQLAlchemy **不会**感知 dict 内部修改，必须整体重新赋值给列。

#### ⚠️ 必须加的模块硬校验（否则会污染其它模块）

拼单的接口走的是 `lost_found` 模块的通用帖子路由（`?type=` 区分），所以
**如果不显式校验模块，任何模块的帖子都能被改人数** —— 二手交易、失物招领、
管理员手工新增的"其他"模块全都会中招。

**在函数最前面加**（在权限校验之后、解析参数之前）：

```python
if post.type != MODULE_GROUP_BUY:
    return as_error(ValidationError('该模块不支持修改人数', code=1001))
```

对应测试用例（见第五节）必须覆盖这条：**对 `lost_found` / `second_hand` 的帖子调用 → 1001**。

> 同样的思路：**「按意向同步人数」= 调同一个接口**，把 `target_count` 不变、
> `current_count` 设为当前的 `post.like_count`。前端读详情里的 `like_count` 即可，
> **不需要新增后端接口**。

### 3.4 详情可见性改为按模块配置（关键修复）

**问题**（`constants.py:214-217`）：

```python
POST_LIST_VISIBLE_STATUSES = (POST_ONGOING, POST_CLAIMED, POST_EXPIRED)
POST_DETAIL_VISIBLE_STATUSES = (POST_ONGOING,)      # ← 只有"进行中"能看详情
```

**后果**：拼单把状态改成"已结束"(`claimed`) 后 → `detail_visible` 为假 → **详情页返回 4002 打不开**。
但参与者/单主还需要看"还差几人、开始日期"。

**改法**：保留全局常量作为默认值，新增按模块覆盖。

`backend/app/utils/constants.py`，在第 217 行之后追加：

```python
#: 按模块覆盖「详情可查看的状态」。
#: 未列出的模块沿用上面的全局默认；这里列出的模块允许这些状态看详情。
#: 说明：失物招领的设计是"已认领/已过期/已关闭就不再展示详情"，
#: 但拼单/跑腿/日常是"流程结束后仍需要回看信息"，因此覆盖为全部状态可见。
MODULE_DETAIL_VISIBLE_STATUSES = {
    MODULE_GROUP_BUY: POST_STATUSES,     # 全部状态可看详情
    MODULE_ERRAND: POST_STATUSES,
    MODULE_DAILY: POST_STATUSES,
}

#: 按模块覆盖「列表可见的状态」（拼单"已取消"不进公开列表，与'已关闭'一致）
MODULE_LIST_VISIBLE_STATUSES = {
    MODULE_GROUP_BUY: (POST_ONGOING, POST_CLAIMED),
    MODULE_ERRAND: POST_STATUSES,
    MODULE_DAILY: (POST_ONGOING, POST_CLOSED),
}
```

`backend/app/models/post.py`，改两个属性（第 153-161 行）：

```python
@property
def list_visible(self):
    allowed = MODULE_LIST_VISIBLE_STATUSES.get(self.type, POST_LIST_VISIBLE_STATUSES)
    return self.is_public and self.status in allowed

@property
def detail_visible(self):
    allowed = MODULE_DETAIL_VISIBLE_STATUSES.get(self.type, POST_DETAIL_VISIBLE_STATUSES)
    return self.is_public and self.status in allowed
```

> `posts_service.can_view_detail()`（第 75 行附近）调用的是 `post.detail_visible`，
> **不需要改** —— 这也是当初把规则集中在模型属性里的好处。

### 3.5 状态文案 + 按模块的状态子集

`backend/app/utils/constants.py` 的 `MODULE_STATUS_LABELS`（第 232 行）追加：

```python
MODULE_GROUP_BUY: {
    POST_ONGOING: '招募中',
    POST_CLAIMED: '已结束',
    POST_CLOSED: '已取消',
    POST_EXPIRED: '已过期',     # 保留兜底（该模块不会主动用到）
},
MODULE_ERRAND: {
    POST_ONGOING: '进行中',
    POST_CLAIMED: '已完成',
    POST_CLOSED: '已取消',
    POST_EXPIRED: '已过期',
},
MODULE_DAILY: {
    POST_ONGOING: '正常',
    POST_CLOSED: '已关闭',
    POST_CLAIMED: '已关闭',     # 日常不使用该状态，兜底避免出现英文
    POST_EXPIRED: '已过期',
},
```

> 现有代码已通过 `MODULE_STATUS_LABELS.get(self.type, POST_STATUS_LABELS)` 读取
> （`models/post.py:108` 与 `:130`），**不用改读取逻辑**。
> **注意**：字典要覆盖该模块**可能出现的全部 4 个状态**，否则漏掉的状态会显示英文原值。

#### ⚠️ 漏洞修复：状态选项必须按模块过滤（否则日常出现两个"已关闭"）

`MODULE_STATUS_LABELS` 是**标签映射**，不是**允许的状态集合**。后端校验用的是全局
`POST_STATUSES`（4 个值），所以：

| 模块 | 若不限制会出现的选项 | 问题 |
|---|---|---|
| 日常 | 正常 / **已关闭** / **已关闭** / 已过期 | 两个"已关闭"，语义重复 |
| 拼单 | 招募中 / 已结束 / 已取消 / 已过期 | "已过期"该模块用不到 |

**修法**：新增一个「每模块允许的状态」常量，并用它过滤 `/meta` 的 `statuses`。

`backend/app/utils/constants.py` 追加：

```python
#: 每模块允许的业务状态子集（用于表单下拉与筛选器）。
#: 未登记的模块 → 回落到全局 POST_STATUSES（保持向后兼容）。
MODULE_ALLOWED_STATUSES = {
    MODULE_GROUP_BUY: (POST_ONGOING, POST_CLAIMED, POST_CLOSED),
    MODULE_ERRAND: (POST_ONGOING, POST_CLAIMED, POST_CLOSED, POST_EXPIRED),
    MODULE_DAILY: (POST_ONGOING, POST_CLOSED),
    MODULE_LOST_FOUND: (POST_ONGOING, POST_CLAIMED, POST_CLOSED, POST_EXPIRED),
}
```

`backend/app/modules/lost_found/routes.py` 的 `module_meta()`（第 453-457 行）改为：

```python
status_labels = MODULE_STATUS_LABELS.get(module_code, POST_STATUS_LABELS)
allowed = MODULE_ALLOWED_STATUSES.get(module_code, POST_STATUSES)
return success({
    'module': module_code,
    'name': get_config('site_name', '校园生活平台'),
    # 只返回该模块允许的状态，且保留模块专属文案
    'statuses': [{'value': code, 'label': status_labels.get(code, POST_STATUS_LABELS.get(code, code))}
                 for code in allowed],
    'audit_statuses': [{'value': key, 'label': label} for key, label in AUDIT_STATUS_LABELS.items()],
    'fields': fields,
    'audit_enabled': post_audit_enabled(),
})
```

**同时**：改业务状态的接口（`PATCH /lost_found/posts/{id}/status` 一类）应校验目标状态在
`MODULE_ALLOWED_STATUSES[post.type]` 内，避免前端绕过下拉直接提交"日常 → 已认领"。

> 注意 `module_meta()` 里 `fields` 也要按模块调整 `contact.required`
> （拼单/日常为 `False`），见 4.2 —— 否则前端的必填提示与后端不一致。

#### ⚠️ 漏洞修复：筛选器改走 `/meta`（当前用全局枚举，文案不跟随模块）

`frontend/src/views/user/PostListView.vue` 的状态筛选下拉现在读的是
**全局** `appStore.enums.post_status`（4 项通用文案）。而 `/meta` 已经能给出
**按模块的正确选项**（上面刚修好）。

**改法**：列表页在 `type` 变化时调用 `GET /lost_found/meta?type=xxx`，用返回的
`statuses` 渲染筛选器。这样：
- 拼单页显示「招募中 / 已结束 / 已取消」
- 日常页显示「正常 / 已关闭」
- 失物招领页仍是原来的 4 项（兼容）

**工作量很小**（该接口已存在，只是换数据源），**收益是消除文案错配**。

---

## 四、前端改动

### 4.1 模块表单配置

**文件**：`frontend/src/config/moduleForms.js`

在 `MODULE_FORMS` 里加三段（机制已存在，照 `second_hand` 的样子写）：

```javascript
group_buy: {
  formHint: '拼单需填写目标人数、当前人数与开始日期；人数变化可随时在「我的发布」里修改。',
  titleLabel: '拼单名称',
  titlePlaceholder: '例如：拼奶茶（一点点，满 5 杯起送）',
  contentLabel: '拼单说明',
  contentPlaceholder: '口味要求、取货方式、分摊方式等',
  locationLabel: '取货地点（选填）',
  locationPlaceholder: '例如：6 号宿舍楼下',
  mediaLabel: '图片 / 视频（选填）',
  time: { label: '开始日期（必填）', placeholder: '选择开始日期', required: true, dateOnly: true },
  extFields: [
    { key: 'target_count', label: '目标人数（必填）', component: 'number',
      required: true, props: { min: 1, max: 999, precision: 0, step: 1 } },
    { key: 'current_count', label: '当前人数（必填）', component: 'number',
      required: true, default: 0, props: { min: 0, max: 999, precision: 0, step: 1 } },
    { key: 'start_date', label: '开始日期（必填）', component: 'date',
      required: true }
  ]
},

errand: {
  formHint: '跑腿请填写期望时间与联系方式，方便同学联系你。',
  titleLabel: '跑腿需求',
  titlePlaceholder: '例如：帮取一个快递（菜鸟驿站 → 6 号楼）',
  contentLabel: '详细说明',
  contentPlaceholder: '物品大小、重量、注意事项等',
  locationLabel: '取件地点',
  locationPlaceholder: '例如：菜鸟驿站',
  mediaLabel: '图片（选填）',
  time: { label: '期望时间（必填）', placeholder: '期望送达的时间', required: true },
  extFields: []
},

daily: {
  formHint: '日常分享，随便写点什么都可以。',
  titleLabel: '标题（选填）',
  titlePlaceholder: '例如：食堂新出的麻辣香锅挺好吃',
  contentLabel: '内容（选填）',
  contentPlaceholder: '想说的话',
  locationLabel: '地点（选填）',
  locationPlaceholder: '例如：二食堂二楼',
  mediaLabel: '图片 / 视频（选填）',
  time: { label: '时间（选填）', placeholder: '选择时间', required: false },
  extFields: []
},
```

> **需要确认**：`start_date` 用的是 `component: 'date'`。
> 若现有渲染器（`PostEditView.vue` 里按 `component` 分支）**只支持 number/select/text**，
> 需要补一个 `date` 分支（用 `<el-date-picker type="date" value-format="YYYY-MM-DD">`）。
> 也可以偷懒：把它做成 `component: 'text'` + 占位提示 `YYYY-MM-DD`。
> **推荐补 date 分支**，体验更好且校验更可靠。

### 4.2 联系方式必填与否按模块区分

**文件**：`frontend/src/views/user/PostEditView.vue`

现状：`contact` 的表单校验写死为必填。

改成：

```javascript
const CONTACT_REQUIRED_MODULES = ['lost_found', 'second_hand', 'errand']
// group_buy / daily → 选填
```

> **后端必须同步改**（这是计划里唯一会让实现者卡住的地方）：
>
> `backend/app/utils/validators.py:182` 的 `validate_contact()` 当前**强制必填**：
>
> ```python
> def validate_contact(value):
>     """联系方式：必填且公开可见，做宽松格式校验。"""
>     value = clean_text(value, 64, '联系方式', required=True)   # ← required=True
>     if not RE_CONTACT.match(value):
>         raise ValidationError('联系方式格式不正确（支持手机号 / QQ / 微信 / 邮箱）')
>     return value
> ```
>
> **改法**：加一个 `required` 参数，并放宽空串匹配（正则 `{2,64}` 不接受空串）：
>
> ```python
> def validate_contact(value, required=True):
>     """联系方式：默认必填且公开可见，做宽松格式校验。
>
>     required=False 时允许空值：此时返回空字符串 ''，
>     以满足 posts.contact 的 NOT NULL 约束（拼单/日常的联系方式选填）。
>     """
>     value = clean_text(value, 64, '联系方式', required=required)
>     if not value:
>         return ''
>     if not RE_CONTACT.match(value):
>         raise ValidationError('联系方式格式不正确（支持手机号 / QQ / 微信 / 邮箱）')
>     return value
> ```
>
> 然后 `posts_service.build_post()` 里按模块传参：
>
> ```python
> # 拼单 / 日常：联系方式选填；其余模块必填
> CONTACT_OPTIONAL_MODULES = (MODULE_GROUP_BUY, MODULE_DAILY)
> contact_required = post_type not in CONTACT_OPTIONAL_MODULES
> contact=validate_contact(data.get('contact'), required=contact_required),
> ```
>
> **回归提醒**：`test_lost_found.py` 里有"不填联系方式返回 1001"的用例，
> 改完必须仍然通过（证明失物招领仍是必填）。

### 4.3 状态文案与筛选器

- **列表/详情/卡片**：直接显示后端返回的 `status_label`（后端已按模块给文案），**前端不用改**。
- **筛选器**：状态下拉改为读 `GET /lost_found/meta?type=xxx` 返回的 `statuses`
  （**见 3.5 的漏洞修复**），不再用全局 `appStore.enums.post_status`。
  这样筛选文案跟随模块变化，且选项数量正确。
- **业务状态按钮**（"我的发布"里的状态切换）：同样按 `/meta` 的 `statuses` 渲染，
  避免给日常提供"已认领"这种无意义选项。

### 4.4 拼单"修改人数"入口 +「按意向同步」

**文件**：`frontend/src/views/user/MyPostsView.vue`（我的发布）

- 当 `item.type === 'group_buy'` 时，多显示一行：`当前人数 2 / 5`
- 加一个「修改人数」按钮（仅作者可见）→ 弹出小弹窗或 `ElMessageBox.prompt`，两个数字输入
- 调 `PATCH /lost_found/posts/{id}/count`
- **必须处理 reject**：`ElMessageBox` 关闭会 reject → 用 `await` + `try/catch` 或 `.catch()`，
  否则控制台报 `Uncaught (in promise) cancel`（项目已有此教训，见 `docs/AUDIT.md`）
- 改完可跑 `cd frontend && pnpm run check` 验证

**「按意向同步」按钮**（同样是作者可见）：

- 显示 `意向 X 人 → 同步为当前人数`
- 点击 → 调**同一个接口**，`current_count = post.like_count`（`target_count` 不动）
- **不需要新增后端接口** —— 详情接口已返回 `like_count`

### 4.5 详情页展示拼单信息 +「我要拼」

**文件**：`frontend/src/views/user/PostDetailView.vue`

**（1）展示拼单字段**

当 `post.type === 'group_buy'` 时展示 `ext.target_count` / `ext.current_count` / `ext.start_date`。

**（2）超员显示规则（漏洞 4 定稿）**

`current_count` **允许大于** `target_count`（单主可能线下又拉了几个人）。显示规则：

| 情况 | 进度条 | 文案 |
|---|---|---|
| `current < target` | `current/target` | **还差 N 人**（`N = target - current`） |
| `current == target` | **100%（封顶）** | **人数已满** |
| `current > target` | **100%（封顶，不溢出）** | **人数已满（超出 N 人）** |

> **要点**：进度条**永远封顶 100%**，不能出现超过容器宽度的溢出；
> 超出部分只用文案表达。这是前端容易写错的地方。

**（3）「我要拼」按钮 —— 复用点赞**

- 按钮文案：拼单模块下把"点赞"改为 **「我要拼」**（已点过显示「已表达意向 / 取消」）
- 接口：`POST /likes/posts/{id}`（**已存在，幂等切换，后端零改动**）
- 状态：`GET /likes/posts/{id}` 返回当前用户是否已点赞
- 显示：`意向 X 人` 与 `还差 N 人` **并列展示**，并加一句说明：
  「意向仅表示想参加，最终人数由发起人维护」
- **作者额外可见**：意向名单（点赞用户列表，若后端已有该接口则直接用；没有就用现有
  点赞详情/用户列表接口拼，**不要为此新增后端接口**）
- **文案必须写清限制**：一人只能点一次，无法表达"我要 3 份"

> ⚠️ **不要**把点赞数自动写成 `current_count`。两者语义不同（意向 ≠ 已确认），
> 自动覆盖会让单主失去控制权。所以只提供**手动**的"按意向同步"按钮（4.4）。

---

## 五、测试要求

**新增文件**：`backend/tests/test_new_modules.py`

| 用例 | 断言要点 |
|---|---|
| 日常模块发布 | `type='daily'`、`ext` 为空对象、发布成功、审核后可查 |
| 日常联系方式选填 | **不填联系方式也能发布成功**（返回的 `contact == ''`） |
| 跑腿模块发布 | 联系方式必填（不填 → 1001）；`happened_at` 能存 |
| 拼单发布（合法） | 三个字段正确回读；`ext` 是对象不是字符串 |
| 拼单发布（缺字段） | 缺 `target_count` / `current_count` / `start_date` 各返回 1001 |
| 拼单发布（非法值） | 目标人数 0 / 1000 / 非整数 / 日期格式错 → 均 1001 |
| 拼单联系方式选填 | 不填 → 成功且 `contact == ''` |
| **拼单修改人数（作者）** | 改为 3/5 成功，`ext` 正确回读 |
| **拼单修改人数（非作者）** | 403（`code=2003`） |
| **拼单修改人数（其它模块）** | 对 `lost_found` 与 `second_hand` 帖子调用 → **1001**（漏洞 1 回归） |
| **拼单人数超出目标** | 设 `current_count > target_count` → 允许保存（不报错） |
| **详情可见性（关键回归）** | 拼单状态置 `claimed` 后：**详情可访问**（不是 4002）；失物招领置 `claimed` 后仍是 4002（旧规则不被破坏） |
| 模块状态文案 | 拼单 `ongoing` → `status_label='招募中'`；日常 `closed` → `'已关闭'` |
| 列表可见性 | 拼单 `closed` 不进公开列表；`errand` 的 `claimed` 仍在列表 |
| **`/meta` 状态选项按模块过滤** | 日常返回 **2 项**且无重复文案；拼单 **3 项**；失物招领 **4 项**（漏洞 2 回归） |
| **`/meta` 的 contact.required** | 拼单/日常为 `False`，跑腿/失物招领为 `True` |
| 「我要拼」复用点赞 | 点赞后 `like_count` +1、`GET /likes/posts/{id}` 显示已点；**不影响 `ext.current_count`**（两者独立） |

**必须回归**：`pytest tests -q` 全绿（当前基线 160 passed）。
**特别注意**：`test_lost_found.py` 里有断言失物招领"已认领详情不可看"的用例 —— 那是
**正确行为**，改动后必须仍然通过（证明按模块配置没有波及旧模块）。

---

## 六、实施顺序（每步可独立验证）

| 步骤 | 内容 | 验证方式 |
|---|---|---|
| **1** | 3.1 常量与 `daily` 模块登记 | `dev_init.py --reset` 后查 `modules` 表有 4 个模块 |
| **2** | 3.5 状态文案 + 按模块状态子集 + `/meta` 过滤 | `GET /meta?type=daily` 返回 2 项、拼单 3 项、失物招领 4 项 |
| **3** | **日常**：3.2 放行 + 3.4 可见性 + 前端 4.1/4.2/4.3 | 发布一条日常帖（不填联系方式），走完审核，详情可看 |
| **4** | **跑腿**：同上（联系方式必填） | 发布跑腿帖，不填联系方式被拒（1001） |
| **5** | **拼单**：3.2 校验 + 3.3 修改人数接口（含模块硬校验）+ 4.4/4.5 前端 | 修改人数成功；非作者 403；对其它模块 1001 |
| **6** | 全量测试 + `pnpm run check` + `pnpm run build` | 全绿 |
| **7** | 更新 `README.md` / `docs/API.md` / `docs/AUDIT.md`（登记审计 #4） | 文档与实际一致 |
| **8** | 逐个在后台**启用**模块（负责人演示前做） | 前台导航出现新 tab |

> **步骤 5 的验证清单**（拼单最容易出错，逐条过）：
> ① 作者改 3/5 成功 ② 非作者 403 ③ 对失物招领帖子调用 1001
> ④ `current_count > target_count` 允许保存 ⑤ 进度条封顶不溢出
> ⑥「我要拼」点赞后 `like_count` +1 但 **`current_count` 不变**
> ⑦「按意向同步」按钮能把 `current_count` 设为 `like_count`

---

## 七、已确认决策（不要再改）

| # | 决策 | 结论 |
|---|---|---|
| 1 | 拼单人数数据存哪 | **`ext_json`**，不加数据库列 |
| 2 | 拼单是否需要"报名"关系表 | **不需要** —— 意向表达**复用 `post_likes`**（v1.2 已建） |
| 3 | 拼单当前人数怎么来 | **单主手动修改**，可随时改；不做自动成团 |
| 4 | 拼单修改人数权限 | **仅单主**（管理员可，沿用 `can_edit`）；**且必须限定 `type='group_buy'`** |
| 5 | 拼单开始日期 | **必填**，日期格式 `YYYY-MM-DD` |
| 6 | 拼单是否需要截止时间 | **不需要** |
| 7 | 「我要拼」的实现方式 | 复用 `POST /likes/posts/{id}`，前端改文案；**不自动覆盖人数** |
| 8 | 人数与意向不一致怎么办 | **两者并列显示** + 单主"按意向同步"按钮（手动） |
| 9 | `current_count` 超过目标 | **允许**；进度条封顶 100%，文案显示"已满（超出 N 人）" |
| 10 | 跑腿 | **纯通用帖子**，只改前端显示（期望时间复用 `happened_at`，联系方式必填） |
| 11 | 日常 | **纯通用帖子**，不加心情/标签字段 |
| 12 | 详情可见性 | **改为按模块配置**；失物招领与二手交易旧规则不变 |
| 13 | 状态选项 | **按模块过滤**（日常 2 项 / 拼单 3 项 / 跑腿与失物招领 4 项） |
| 14 | 筛选器数据源 | 改读 `GET /lost_found/meta?type=` |
| 15 | 状态常量 | **不改** `POST_STATUSES`，只加模块级文案映射与子集 |
| 16 | 模块启用 | **做完一个启用一个**（默认 `enabled=False`） |
| 17 | 数据库改动 | **零**（不加表、不加列） |

---

## 八、风险与注意事项

| 风险 | 说明 | 应对 |
|---|---|---|
| **修改人数接口影响其它模块** | 走的是通用帖子路由，不校验就会污染二手交易/失物招领 | **必须加 `type == group_buy` 硬校验**（见 3.3），并有回归用例 |
| **日常出现两个"已关闭"** | `MODULE_STATUS_LABELS` 是标签映射，不是允许集合 | 新增 `MODULE_ALLOWED_STATUSES` 并过滤 `/meta`（见 3.5） |
| `posts.contact` 是 `NOT NULL`，且 `validate_contact()` **强制必填** | 拼单/日常要选填，直接传空会被后端拒（1001） | 按 4.2 给 `validate_contact` 加 `required` 参数；空值返回 `''` 而非 `null` |
| `ext_json` 不能原子改单键 | 改人数需整体重写 JSON | 见 3.3 的实现要点（必须整体重新赋值给列） |
| 详情可见性改动可能波及旧模块 | 失物招领有"已认领不可看详情"的既有测试 | 保留全局常量为默认值，只对三个新模块覆盖；回归用例必须仍绿 |
| **意向数与人数不一致** | 点赞≠已确认，自动同步会让单主失去控制 | 两者并列显示；只提供手动"按意向同步" |
| 进度条溢出 | `current_count > target_count` 时百分比会 >100% | 进度条封顶 100%，超出只用文案表达（见 4.5） |
| `daily` 未登记在种子数据 | 已有库不会自动新增 | 后台模块管理新增，或 `dev_init.py --reset` |
| `start_date` 需要 `date` 组件 | 现有渲染器可能只支持 number/select/text | 补一个 `date` 分支，见 4.1 |
| `ElMessageBox` reject | 修改人数的弹窗若未接住会报 `cancel` | 用 `await` + `try/catch`；跑 `pnpm run check` |
| `ext_json` 4096 字节上限 | 拼单只存 3 个字段，远不会超 | 无需处理 |
| `POST_STATUS_LABELS` 兜底 | 模块文案字典若漏某个状态，会显示英文原值 | 每个模块的字典都写满 4 个状态（见 3.5） |

---

## 九、完工标准

- [ ] `pytest tests -q` 全绿（含新增用例，且原有 160 个不回退）
- [ ] `pnpm run check` 0 处问题
- [ ] `pnpm run build` 成功
- [ ] `upgrade_schema.py --check` 显示 **新增列/表/索引均为 0**（证明没改结构）
- [ ] `check_orphans.py` 无孤儿
- [ ] 三个模块各有至少 1 条真实帖子，走完"发布 → 审核 → 列表 → 详情"全流程
- [ ] 拼单"修改人数"由单主操作成功、非作者被拒、**对其它模块返回 1001**
- [ ] 拼单「我要拼」可点、可取消，`like_count` 变化而 `current_count` **不变**
- [ ] 拼单进度条在超员时**不溢出**，文案显示"已满（超出 N 人）"
- [ ] `/meta` 状态选项：日常 2 项且无重复文案、拼单 3 项、失物招领 4 项
- [ ] 失物招领的旧规则（已认领不可看详情）**仍然生效**
