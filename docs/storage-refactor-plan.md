# 知识存储结构重构规划

> 目标：让存储从「扁平条目列表」升级为「以实体为中心 + 带时序的结构」，
> 从而同时满足两件事：**生成时高效取用准确信息**，以及**未来按单实体聚合展示**。
>
> 状态：**规划阶段，尚未动代码**。本文基于代码静态分析 + 一次子代理深度调研。
> 重要前提：`data/` 下 **零真实数据**（所有项目 `knowledge_items = 0`），因此迁移成本基本为零，这是动手的最佳窗口。

---

## 一、现状盘点：能力三态

调研结论按「存在 / 存在但有问题 / 不存在」三态分类，每条附代码位置。

### 已存在且在生产使用 ✅

| 能力 | 证据 |
|---|---|
| 12 个分类，一个实体/事件 = 一条（**决策后减为 11 个**，见 2.7） | `services/memory/core.py:231` `KNOWLEDGE_CATEGORIES` |
| 读取时按名聚类（角色卡/设定卡） | `domain/knowledge_entities.py:277` `build_character_entity_cards`，被 API(`api/app.py:788`) 与 UI(`ui/entity_experience.py:137`) 调用 |
| 时间线事件排序（order_hint + time，自然排序） | `domain/knowledge_entities.py:253` `timeline_item_sort_key` |
| 实体间关系（势力敌对等） | `storage/migrations/001_initial.sql:343` `graph_edges`；写入见 `repositories/knowledge.py:960` |
| 实体归并键（按名 + story + worldline 哈希） | `repositories/knowledge.py:781` `_entity_node_id`；但**读取侧聚类用的隔离键更完整**：`knowledge_entities.py:24` `_isolation_group_key` 返回 `(setting_scope, story_id, worldline_id, version_scope)` 四元组——新 `entities` 表的唯一索引必须同样覆盖这四维，否则会漏掉跨版本/跨 scope 的同名隔离 |
| 别名归并（识别"林越 = 林公子"） | `domain/knowledge_quality.py:233` `upsert_entity_alias_group` |
| 软删除（读取侧已全面过滤） | `knowledge_items.deleted_at`，过滤见 `repositories/knowledge.py:302/333/390` |
| 迁移机制（加表只需一步） | `storage/schema.py:49` `ensure_schema`，版本 16；新建 `017_xxx.sql` + 改 `CURRENT_SCHEMA_VERSION` |

### 存在但有严重问题 ⚠️

| 问题 | 证据与说明 |
|---|---|
| **归并语义是"并集拼接"，不是"取最新"** | `knowledge_quality.py:18-27` `merge_text_values` 用 `\n\n` **去重拼接**；`merge_details_values:73` 同名字段同样拼接。于是"身在京城"+"身在洛阳" → 归并结果为**两者并存** |
| **章号塞在 tags/details 里，无法 SQL 查询** | `workflows/skills/common.py:826` 写入 `tags: ["chapter:5"]`，`knowledge_items` 表**无 chapter 列**（迁移 001 无命中） |
| **两套图节点并存且各不完整** | `knowledge_node_{knowledge_id}`(`:740`，有类型无归并) 与 `entity_node_{hash}`(`:798`，有归并但 `node_type` 硬编码 `'entity'`、`knowledge_id` 为 NULL) |
| **角色卡不持久化** | `save_character_entities` 仅被 3 个 tools 验证脚本调用，生产代码零写入方；卡片每次实时计算 |
| **always 注入无上限，检索被静默饿死** | `setting_knowledge.py:616` `format_setting_items_for_prompt` 拼接全部 summary 无 LIMIT；预算 12k 且硬约束先扣款（`context_assembly.py:271`） |

### 完全不存在 ❌

| 缺失能力 | 说明 |
|---|---|
| 实体主档（持久化的跨条目聚合记录） | 聚类只发生在读取时，存储层无"一个角色一行"的概念 |
| 世界状态随时间变化 / 快照 | 全库无 `state_at` / `world_state` / `chronology` schema |
| 按章节范围取知识 | 生成侧 `context_assembly.py:398` 全量 `load_knowledge_base` 后 Python 过滤，**无 chapter 维度** |
| 事实的生效/失效区间 | 条目一旦写入就永久有效，无法表达"第 5~8 章在京城" |

---

## 二、目标模型：Entity-Fact-Relation 三层

核心思路：**不推翻现有表，而是在其之上加一层「实体主档」，并给事实加上时间区间。**

```
L1  Entities（主档）   一个角色 / 势力 / 道具 / 事件 = 一行
     ↑ 1:N
L2  Facts（事实）      复用 knowledge_items，新增 entity_id + fact_key + 生效区间
     
L3  Relations（关系）  复用 graph_edges，端点改指向 entities
```

为什么这样设计：

- **聚类需求**由 L1 满足：角色/势力/道具都是 Entity，天然聚合；
- **时间相关性**由 L2 的生效区间满足：事件也是 Entity，用 `chapter_no` 排序即时间线；
- **生成取用**变成一次带索引的 SQL 查询，不再是全量加载 + Python 过滤；
- **展示需求**由 L1 直接满足：查一个 Entity 及其全部 Facts = 角色卡/势力卡/时间线。

### 2.1 新增表 `entities`（迁移 017）

```sql
CREATE TABLE entities (
    entity_id       TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL,          -- character|organization|location|item|ability|event|world_rule|...
    canonical_name  TEXT NOT NULL,          -- 归并后的规范名
    display_name    TEXT NOT NULL DEFAULT '',
    story_id        TEXT,
    worldline_id    TEXT,
    setting_scope   TEXT NOT NULL DEFAULT 'project',
    version_scope   TEXT NOT NULL DEFAULT 'project_main',  -- 关键：区分 canon(原作) 与 project_main(二创)
    alias_group_id  TEXT REFERENCES entity_alias_groups(alias_group_id) ON DELETE SET NULL,
    summary         TEXT NOT NULL DEFAULT '',   -- 当前概述（自动派生或人工维护）
    meta_json       TEXT NOT NULL DEFAULT '{}', -- 展示用：头像、配色、排序、标签
    importance      INTEGER NOT NULL DEFAULT 0, -- 生成时的取舍权重
    world_t         REAL,                       -- event 专用：世界内时间的可排序键（见 2.6c）
    world_time_label TEXT,                      -- event 专用：人类可读时间标签
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_identity
    ON entities(entity_type, canonical_name, story_id, worldline_id, setting_scope, version_scope);
```

> 唯一索引必须与读取侧聚类键对齐：`_isolation_group_key`（`knowledge_entities.py:24`）
> 返回 `(setting_scope, story_id, worldline_id, version_scope)` 四元组，
> 其中 `version_scope` 取 `project_main` / `canon`（`services/memory/knowledge.py:365`）。
> **若漏掉 `version_scope`，原作与二创的同名角色会撞唯一索引**——这是本方案一版 DDL 的疏漏，已补。

`entity_type` 由现有 category 映射（复用 `repositories/knowledge.py:712` `_graph_node_type_for_category` 的思路，但把 `'entity'` 这个笼统值拆开）。取消 `constraints` 后为 11 个（见 2.7）。

### 2.2 `knowledge_items` 加列（迁移 017）

```sql
ALTER TABLE knowledge_items ADD COLUMN entity_id          TEXT REFERENCES entities(entity_id);
ALTER TABLE knowledge_items ADD COLUMN fact_key           TEXT;   -- 槽位键：location|status|owner|...
ALTER TABLE knowledge_items ADD COLUMN chapter_no         INTEGER;-- 来源章节（取代 tags 里的 chapter:N）
ALTER TABLE knowledge_items ADD COLUMN valid_from_chapter INTEGER;
ALTER TABLE knowledge_items ADD COLUMN valid_to_chapter   INTEGER;-- NULL = 至今有效
ALTER TABLE knowledge_items ADD COLUMN superseded_by      TEXT REFERENCES knowledge_items(knowledge_id);

CREATE INDEX idx_ki_entity_slot  ON knowledge_items(entity_id, fact_key, valid_from_chapter);
CREATE INDEX idx_ki_entity_valid ON knowledge_items(entity_id, valid_from_chapter, valid_to_chapter);
CREATE INDEX idx_ki_chapter      ON knowledge_items(chapter_no);
```

### 2.3 关系层与「实体间引用」的统一（本次审查的重大补充）

`graph_edges` 结构已完备（`source_node_id/target_node_id/relation_type/direction/confidence/evidence_id`），
改造只需让端点指向 `entities.entity_id`，并在 `graph_nodes` 之外保留别名归并能力。

#### 决策（2026-09-04 拍板）：废弃 graph_nodes，统一节点到 entities

用户明确"重构目的是得到更完善、清晰、简洁的结构，不迁就兼容"。据此决定：

- **`entities` 是唯一的实体节点表**；`graph_nodes` 表**废弃**（停止写入，保留表不删以维持迁移加性）。
- **`graph_edges` 端点 = `entities.entity_id`**（不再是 graph_nodes.node_id）。
- `graph_nodes` 曾承担两职，均被取代：`knowledge_node_{id}` 无任何读取方（纯冗余）；
  `entity_node_{hash}` 的职责被更完整的 `entities` 覆盖（含 entity_type/version_scope/world_t/summary）。
- 关系边（relationship）与引用边（owns/member_of/...）**统一**走 graph_edges，端点都是 entity_id。
- 读取方 `load_knowledge_graph_rows`（`knowledge_center.py:199`）由 JOIN graph_nodes 改为 JOIN entities。

但**只改"关系"这一条边是远远不够的**。审查发现：项目里存在一整类
「**实体间引用字段**」，它们现在是**纯文本列表，与实体零结构化关联**，规划未覆盖：

| 字段 | 所属分类 | 语义 | 现状 |
|---|---|---|---|
| `owners` | items | 谁持有此物 | 纯文本 |
| `users` | abilities | 谁会此能力 | 纯文本 |
| `leaders` / `members` | organizations | 谁领导/隶属此势力 | 纯文本 |
| `inhabitants` | locations | 谁在此地 | 纯文本 |
| `parent_location` | locations | 此地隶属何地 | 纯文本 |
| `participants` | timeline_events | 谁参与此事件 | 纯文本 |
| `affiliations` | characters | 角色属于何势力 | 纯文本 |
| `relations` | organizations | 势力间关系 | 纯文本 |

这些字段和 `relationships` 一样，本质上都是「**两个实体之间的边**」，
却只有 `relationships` 走了 `graph_edges`（`_upsert_graph_relationship_edges` 仅在写 relationships
时被调用，`repositories/knowledge.py:378/664`）。后果：

- 问"林越持有哪些物品" → 无法结构化查询，只能全文检索碰运气；
- 问"青云门有哪些成员" → 同上；
- 问"林越参与过哪些事件" → 同上。

**这正是"充分适配小说生成/读取"的关键缺口**——小说里"谁拥有什么、谁属于哪、
谁在哪、谁做了什么"是最频繁的关联查询，却全部退化成了文本。

**解决方案：把所有实体间引用统一收编到 `graph_edges`。**

- 每个引用字段 → 一条边，`relation_type` 语义化：
  `owns`（持物）/ `wields`（用剑）/ `member_of`（隶属）/ `leads`（领导）/
  `located_in`（地处）/ `participated_in`（参与）/ `affiliated_with`（结盟）/
  `parent_of`（上级地点）/ `related_to`（兜底）；
- `graph_edges` 补时序列（见 2.6a）：`valid_from/to_chapter` + `merge_policy` + `chapter_no`，
  这样"第 5 章林越持有此剑、第 20 章转赠他人"也能表达；
- 边与 `knowledge_items` 一样，靠 `entity_id` 端点 + `valid_from_chapter` 做区间查询。

**保留文本字段作冗余**：`owners`/`members`/`participants` 等文本字段**仍保留**（供展示、供 LLM 抽取的原始结果存档、供全文检索），
但新增一条**权威的结构化边**作为查询主路径。二者以 `edge` 为准、以文本为回退。

**这也是 P1 的新增工作量**：写入时，凡抽取到带引用字段的条目，除写 `knowledge_items` 外，
同步 upsert 对应 `graph_edges`（同 P1 已有的事件参与者关联逻辑，一并实现）。

### 2.4 合并策略：追加 vs 取代（关键补充）

> 这一节是初版方案的修正。初版把事实分为"静态槽位（不需时序）"与"动态槽位（需时序）"，
> 这是**错的**——外貌、性格同样会随时间改变（添疤 / 一夜白头 / 性情大变）。

正确的区分不是「会不会变」，而是「**新值是追加还是取代旧值**」：

| | 追加 append | 取代 replace |
|---|---|---|
| 语义 | 新事实叠加在旧事实上 | 新事实让旧事实失效 |
| 例子 | 学会刀法（剑法还在）、脸上添疤 | 移到洛阳（不在京城）、一夜白头 |
| `valid_to_chapter` | 不设，永久有效 | 设为新值的生效章 |
| 该事实的 `merge_policy` | `append` | `replace` |

**关键点：同一个 `fact_key` 两种语义都可能出现。**
外貌既能追加（第 20 章添疤）也能取代（第 30 章白头），因此策略不能由槽位类型一刀切。

建议在 `knowledge_items` 上增加一列记录本次写入采用的策略（便于事后审计与修复）：

```sql
ALTER TABLE knowledge_items ADD COLUMN merge_policy TEXT NOT NULL DEFAULT 'append';
-- 取值：append | replace
```

默认策略表（可按项目配置覆盖）：

```python
FACT_MERGE_POLICY = {
    "location":    "replace",  # 只能在一个地方
    "status":      "replace",  # 受伤/被囚等状态互斥
    "holder":      "replace",  # 一件物品一个持有者
    "abilities":   "append",   # 技能是累积的
    "appearance":  "append",   # 外貌特征通常累加
    "personality": "append",   # 性格层次累加
}
```

**写入流程**：新事实落库时，若其 `merge_policy == 'replace'`，
则把同 `(entity_id, fact_key)` 下当前有效的旧事实的 `valid_to_chapter` 置为本条事实的 `valid_from_chapter`。

**查询不受影响**：第三节的查询范式对两种语义都成立，无需改动。

**风险与兜底**：让 LLM 自动判断 append/replace 并不完全可靠，因此三层兜底——
① 默认按槽位策略（覆盖绝大多数情况）；② 待审队列提供开关供人工改为 replace；
③ 判错可修复（历史完整保留，清掉 `valid_to_chapter` 即可恢复）。

### 2.5 需要补充的槽位

核对 `knowledge_types.py:14` 后发现：`characters` 的字段定义为
`aliases / roles / appearance / personality / motivations / abilities / affiliations`，
**缺少 `location`（当前位置）、`status`（当前状态）、`holding`（持有物）**——
而这几项恰是跨章连贯最需要时序管理的槽位（`items` 反倒有 `status` 与 `owners`）。

进一步核对后发现**缺 `status` 的不止 characters**：

| 类型 | 现有字段 | 缺 status？ | 会变吗 |
|---|---|---|---|
| characters | 别名/身份/外貌/性格/动机/能力/所属 | **缺** | 会（位置、状态、持有物） |
| items | 类型/持有者/功能/限制/**状态** | 有 | 会（断裂、易主） |
| locations | 别名/类型/上级地点/特征/居民 | **缺** | 会（被围困、易主、毁灭） |
| organizations | 别名/类型/领导者/成员/目标/关系 | **缺** | 会（覆灭、结盟、分裂） |

因此 `fact_key` 分两类：

- **沿用现有字段规范**：`appearance` / `personality` / `abilities` / `affiliations` 等
- **新增通用动态槽位**：`location` / `status` / `holder` / `current_goal`

#### 补齐方案（动态槽位矩阵 + 抽取来源）

动态槽位不是笼统加给所有实体，而是**按实体类型给一个明确的槽位集合**，
并逐一落实到"从哪抽出来"：

| 实体类型 | 补齐的动态槽位 | 合并策略 | 抽取来源（现状） |
|---|---|---|---|
| character | `location` / `status` / `holding` / `current_goal` | replace / replace / replace / replace | ❌ 未抽取 |
| item | `status` / `owners`（已有，复用） | replace / replace | ⚠️ 有字段但章节抽取未填 |
| location | `status` | replace | ❌ 未抽取 |
| organization | `status` | replace | ❌ 未抽取 |

**关键发现：缺口有两层，只补数据模型不够。**

1. **字段层**：`characters` / `locations` / `organizations` 的 `knowledge_types.py` 字段规范里没有
   `status`/`location`/`holding`（`items` 例外，有 `status`/`owners`）。
2. **抽取层（更深、更致命）**：`core/prompts.py` 的章节设定抽取 prompt（`new_characters` 相关，
   约 `:1275-1290`）**只要求 LLM 抽身份/性格/动机/能力/所属**，根本没让模型产出位置/状态/持有物。
   → 即使 P1 加上了 `fact_key` 列，抽取也不会产生这些槽位的数据，动态槽位会一直空着。

所以补齐动作包含三处（归入 P1）：

| # | 改动 | 内容 |
|---|---|---|
| S1 | `knowledge_types.py` | 给 `characters`/`locations`/`organizations` 补 `status` 字段定义，`characters` 再补 `location`/`holding` |
| S2 | `core/prompts.py` 抽取 prompt | `new_characters` 明确要求产出 `location`/`status`/`holding`；`world_updates` 要求产出地点/势力的 `status` 变化 |
| S3 | `workflows/skills/common.py` 映射表 | 把新抽出的字段映射到对应 `setting_field`（`SETTING_FIELD_SPECS` 增补 `location`/`holding` 等动态槽位，或复用已有字段） |

其中 **S2 是真正的杠杆**：不改 prompt，其他都白搭。

### 2.6 十一个分类的完整映射（初版方案的重要补充）

> 初版方案只用「角色」举例，掩盖了三类差异。此处逐类过一遍。
> **决策后分类由 12 个减为 11 个**：`constraints` 取消，按层级归位（见 2.7）。

| # | category | 新模型归属 | entity_type | 需时序 | 说明 |
|---|---|---|---|---|---|
| 1 | characters | Entity | character | 是 | 缺 location/status/holding 槽位 |
| 2 | items | Entity | item | 是 | 已有 status/owners |
| 3 | abilities | Entity | ability | 是（可失去） | |
| 4 | locations | Entity | location | 是 | 缺 status 槽位 |
| 5 | organizations | Entity | organization | 是 | 缺 status 槽位；**势力展示页的数据源** |
| 6 | timeline_events | Entity | event | 否 | 事件不"变"，需的是**排序**而非 fact_key 互斥 |
| 7 | relationships | **Relation（边）** | — | **是** | 见下 |
| 8 | world_rules | 边界模糊 | — | 可选 | 可实体化（"灵气体系"）也可作全局规则 |
| 9 | writing_style | 项目级全局 | — | 可选 | 无实体归属，不进 entities |
| 10 | dialogue_style | 项目级 / 可挂角色 | — | 可选 | 有 `speaker` 字段；挂角色时经 `graph_edges` 的 `speaks_as` 边关联（与引用收编同路，见 2.3） |
| 11 | narrative_techniques | 项目级全局 | — | 可选 | 无实体归属 |
| 12 | ~~constraints~~ | **取消** | — | — | **归位到 `rules` 表与 `world_rules`，见 2.7** |

**三类差异，初版方案均未处理：**

**(a) 关系不是实体，是边——且所有"实体间引用"都应是边。**
`relationships` 有 `subject/object/relation_type/direction/status`，语义上是两个实体之间的边，
应存入 `graph_edges` 而非 `entities` + `facts`。**且关系本身会变**（师徒→反目、盟友→敌对），
因此 `graph_edges` **同样需要时序列**：

```sql
ALTER TABLE graph_edges ADD COLUMN valid_from_chapter INTEGER;
ALTER TABLE graph_edges ADD COLUMN valid_to_chapter   INTEGER;
ALTER TABLE graph_edges ADD COLUMN merge_policy TEXT NOT NULL DEFAULT 'replace';
ALTER TABLE graph_edges ADD COLUMN chapter_no INTEGER;
```
现有 `graph_edges`（`001_initial.sql:343`）只有 `created_at/updated_at/deleted_at`，**无时序字段**。

**不止 `relationships`**：items 的 `owners`、abilities 的 `users`、organizations 的 `leaders/members`、
locations 的 `inhabitants/parent_location`、timeline 的 `participants`、characters 的 `affiliations`
——全是实体间引用，统一收编进 `graph_edges`（详细 relation_type 清单见 2.3）。

**(b) 全局设置不属于任何实体。**
`writing_style` / `narrative_techniques` / `world_rules` 是项目级配置，
没有"属于谁"这一维度，硬套 `entity_id` 没有意义。
处理方式：**不进 `entities` 表**，保持项目级存储，仅在需要时附加可选的章号范围
（例如"第一卷的文风"、"第 30 章起的硬约束"）。

**(c) 事件需要排序而非互斥 —— 但时间要拆成两个独立的轴。**

`timeline_events` 作为实体，其事实不会被"取代"（第 5 章发生的事永远发生在第 5 章），
因此**不需要 `fact_key` 互斥机制**。

但更根本的问题在于：**章号（叙事顺序）和故事内时间（世界观时间）是两个不同的轴，
现状却只用了章号一个，导致"历史/当前/同时异地/倒叙"全都无法表达。**

| 轴 | 键 | 回答什么 | 性质 |
|---|---|---|---|
| 叙事进度 | `chapter_no` | 写到第几章了 | 整数，可靠排序，**用于生成时的"注入到哪一章为止"** |
| 世界时间 | `world_t` + `timeline_id` | 故事里现在几点/哪个时代/哪条线 | 需新设计（见下） |

章号 ≠ 世界时间的三种典型错位：

- 回忆/倒叙：第 10 章写"三年前" → 章号在前，世界时间在过去；
- 同时异地：第 12、13 章写同一时刻两地 → 章号不同，世界时间相同；
- 多线叙事：支线、if 线 → 章号顺序表达不了时间顺序。

由此"历史 vs 当前"不是一个能靠存储字段切开的二分——它是观察者视角，
同一事件对 A 是历史、对 B 是当前。正确的模型是**所有事件落在同一条世界时间轴上**，
没有历史/当前的墙。

**世界时间的两层设计（均加入）：**

**第一层：可比较的时间戳 `world_t`（排序用）**
给每个世界时间点一个**单调可比的数值键**（浮点或整数，如 `100` 早于 `200`），
配人类可读标签（`world_time_label`，如"大齐三年三月初三"）。
- 历史大事、当前大事、倒叙、同时异地，全都能按 `world_t` 排；
- 因果先后（"A 在 B 之前"）第一次可查询；
- **不要求精确历法**，只需"单调 + 可比"；LLM 抽取时给相对序号，人工在时间线视图校准。

**第二层：世界线标识 —— 复用现有 `worldline_id`，不新增列。**
项目已有 `worldline_id` 概念（`GLOBAL_WORLDLINE_IDS = {"", "all", "global", "shared", "canon", "unknown"}`
见 `knowledge_entities.py:21`，检索层已支持"故事/世界线过滤"），
正史 / if 线 / 前世 的多线需求由它承载。单线作品其值为空，零成本。
**故不再新增 `timeline_id` 列，避免与 `worldline_id` 语义重叠。**

**落地到 DDL**：`entities` 表为 `event` 类型补两列（`worldline_id` 已存在）：

```sql
ALTER TABLE entities ADD COLUMN world_t REAL;              -- 世界内时间的可排序键
ALTER TABLE entities ADD COLUMN world_time_label TEXT;     -- 人类可读：大齐三年三月初三
```

时间线查询改为 `ORDER BY worldline_id, world_t, chapter_no`（世界时间优先，章号兜底）。

事件参与者关联（`participants` 现为纯文本，无法回答"林越参与了哪些事件"）：
复用 `graph_edges`，事件实体 → 角色/地点实体，`relation_type='participated_in'`，
与关系层走同一条结构化路径。

### 2.7 规则机制梳理与决策：取消 constraints 分类

调研中发现存在**两套并行的规则机制**，重构时应厘清，否则会继续分裂：

| | `rules` 表 | `constraints` 分类 |
|---|---|---|
| **定位** | 给模型的**执行指令** | 知识库里的**一类知识条目** |
| 存储 | `001_initial.sql:52` 独立表（+ `rules.json` 镜像，双写） | `knowledge_items` 中 `category='constraints'` |
| 结构 | 一行纯文本 `content` | 结构化字段 `constraint_type`/`rule`/`applies_to`/`severity`/`exceptions`（`knowledge_types.py:97`） |
| 层级 | global / project / story 三级，可互相复制 | 依附知识库，`setting_scope` + worldline |
| 过滤维度 | **写作阶段**（`RULE_SCOPES = all/outline/chapter_outline/write/review/setting_extraction`，`core.py:176`） | 无阶段概念 |
| 注入 | `format_rules_for_prompt`，priority **1000**，`hard_constraint=True`，**自动** | **仅设定字段类自动注入**（见下），其余靠手工选或检索召回 |
| 治理 | `enabled`/`priority`/`conflict_resolutions` | 审核确认 / 修订历史 / 来源追溯 |

#### 关键修正：constraints 并非都走 priority 900

`constraints` 分类有两拨条目，命运完全不同：

- **设定字段类**（`setting_knowledge.py:23/24/30` 把 `canon_mode`/`au_rules`/`active_constraints`
  三个 setting_field 映射到 `constraints` 分类）→ 走 `list_setting_items(injection_policies={"always"})`
  → `always_settings` 块 → **priority 900，始终注入**。
- **其余 constraints 条目**（资料导入抽取产出、手工录入）→ `context_assembly.py` 中**无任何引用**，
  只能通过两条旁路进上下文：① 手工选中（`manual_knowledge` 块，priority **95**，`placement="reference"`）；
  ② 检索召回（`retrieval` 块）。

所以"两套并行硬规则"的说法**需要收窄**：真正与 rules 表竞争的只有那三个设定字段。

#### 补充事实

- `capability` 是**写作阶段**而非"能力"（`core.py:176`），UI 在 `ui/rules_page.py:28-35` 按 6 个阶段分文本框编辑。
- constraints 分类当前**实际用途**是给人看的报告：`source_workflows.py:155-159` 在资料导入总结里
  把 constraints 取前 20 条渲染成"同人写作注意事项"纯文本。
- rules 表支持 JSON 镜像 + DB 双写（`save_global_rules` → `_write_json_mirror` + `sync_rules_payload`）。

#### 补充：更准确的划分是「层级 × 语气」两个正交维度

用户提出的划分（**rules = 跨故事的元规则，constraints = 故事内的规则**）比 `rules vs constraints`
的表边界更贴近语义。但核查后发现，这条界线**斜穿过三个地方，没落在任何存储边界上**：

|  | **对 AI 的指令**（语气：指令性） | **对世界的描述**（语气：描述性） |
|---|---|---|
| **跨故事（元层）** | `rules` 表 global / project 级<br>例：用第三人称、每章 3000 字 | ——（无此需求） |
| **故事内** | `constraints` 分类<br>字段 `applies_to` / `severity` | `world_rules` 分类<br>字段 `conditions` / `consequences` |

两个分类的字段高度重叠（都含 `rule` + `exceptions`），差别**只在语气**：
`world_rules` 多了"生效条件/后果"（讲世界如何运转），`constraints` 多了"适用范围/严格程度"（讲 AI 该怎么守）。

**关键事实（修正先前的判断）**：`SETTING_EXTRACTION_KNOWLEDGE_FIELDS`（`common.py:704-709`）
只有 4 个字段，章节抽取**根本不产出 constraints**：

| 抽取字段 | → category | → setting_field |
|---|---|---|
| `new_characters` | `characters` | `characters` |
| `world_updates` | **`world_rules`** | `world` |
| `timeline_updates` | `timeline_events` | `timeline` |
| `foreshadowing_updates` | `narrative_techniques` | `forehadowing` |

即：**章节写作产出的"故事内规则"走的是 `world_rules`，不是 `constraints`**。
`constraints` 的三个 setting_field（`canon_mode` / `au_rules` / `active_constraints`）
来自手工录入与资料导入，且内部就混杂了两种层级——`canon_mode`（原作对齐方式）是**元层**
（被 `core/prompts.py:12` 当提示词模板变量用），`au_rules`（架空规则）是**故事内**。

#### 决策（已拍板）：取消 `constraints` 分类，按层级归位

**归位规则**

| 原条目 | 层级 | 归位去向 | 理由 |
|---|---|---|---|
| `setting_field='canon_mode'` | 元层 | **回并 story memory 的 `canon_mode` 字段**，不再单存条目 | 该字段本就是 memory 的一等字段（`core.py:216`），`core/prompts.py:12` 直接读取它——知识库里那份是**冗余副本** |
| `setting_field='au_rules'` | 故事内 | `world_rules` | 架空规则就是世界规则，字段语义完全吻合 |
| `setting_field='active_constraints'` | 混合 | 按下述规则分派 | 需按内容判断 |
| 其余（无 setting_field 的普通条目） | 故事内 | `world_rules` | 默认策略 |

`active_constraints` 的分派规则：

- 内容讲"世界如何运转 / 违反会怎样" → `world_rules`
- 内容讲"不许怎么写 / 写作纪律"（与故事内容无关） → `rules` 表 story 级
- **默认先归 `world_rules`**，人工在待审队列复核时可改判

**代码改动点（7 处）**

| # | 文件 | 改动 |
|---|---|---|
| 1 | `domain/setting_knowledge.py:23/24/30` | `canon_mode` 移出 `SETTING_FIELD_SPECS`；`au_rules` / `active_constraints` 的 `category` 改为 `world_rules` |
| 2 | `domain/knowledge_types.py:97-103` | 删除 `constraints` 字段定义 |
| 3 | `services/memory/core.py:243` | `KNOWLEDGE_CATEGORIES` 移除 `constraints` |
| 4 | `workflows/web_research_tasks.py:64-78` | `DEFAULT_RESEARCH_CATEGORIES` 移除 `constraints` |
| 5 | `workflows/source_workflows.py:155-159` | 报告渲染改读 `world_rules` |
| 6 | `workflows/skills/common.py:228/243` | `KNOWLEDGE_SOURCE_TYPES` 移除 `knowledge_constraints` |
| 7 | `ui/labels.py` / `ui/knowledge_center.py` | UI 分类清单同步移除 |

**数据迁移**

已核查：`data/` 下所有项目 `knowledge_items` 中 `category='constraints'` 计数为 **0**，
**迁移成本为零**。仅需在新迁移脚本中保留转换逻辑，以备将来存量数据。
若届时存在数据，按上表 UPDATE `category`；`canon_mode` 条目回写 memory 后软删除。

**消费方式的根本差异（本轮最有价值的推论）**

- **元层规则**：量小、稳定 → 无条件注入，priority 1000（现状正确，不动）
- **故事内规则**：**量大且随章节增长** → 必须**按需召回**（按实体 / 章号区间），
  绝不能走 `always`

现状 `active_constraints` 走 always（priority 900、无上限）是膨胀源之一，
归位后在 **P1** 与 always 块配额一并治理。

> 此决策归入 **P1**（写入侧归位）；**P0 不受影响**，可先行开工。

#### 执行状态与分期（2026-09-04 更新）

实测耦合面**远超初版预估的 7 处**：`constraints` 共出现在 16 个文件 40+ 处。
已按「先钉存储边界、抽取/检索侧留待抽取改造」分期执行：

**已改（存储边界，已完成）**：
- `setting_knowledge.py`：`SETTING_FIELD_SPECS` 移除 `canon_mode`、`au_rules`/`active_constraints`
  的 category 改为 `world_rules`；`SETTING_CATEGORY_ORDER` 移除 `constraints`；
- `services/memory/core.py`：`KNOWLEDGE_CATEGORIES` 移除 `constraints`；
- `knowledge_types.py`：删除 `constraints` 字段定义；
- `web_research_tasks.py` / `skills/common.py`（`KNOWLEDGE_SOURCE_TYPES`）/ `ui/labels.py`：移除引用；
- `source_workflows.py`：报告渲染改读 `world_rules`；
- `discussion_assets.py`：讨论资产写入 `category` 由 `constraints` → `world_rules`（2 处硬编码）；
- `services/memory/knowledge.py`：`manual_review_categories` 默认值 `constraints` → `world_rules`。

**未改（软引用，留待「抽取内容全面改造」时统一清理）**——这些是 LLM 抽取 schema、
抽取预设、检索类型枚举、实体卡展示，删除/改映射需随抽取重做一并处理，否则会破坏现有抽取行为：

| 文件 | 引用 | 性质 | 清理动作 |
|---|---|---|---|
| `core/schemas.py` | 348/864/926/1401 | LLM 抽取合法 category 枚举 | 随抽取重做移除 |
| `domain/extraction_presets.py` | 8 处 `categories` 清单 | 抽取预设 | 移除 constraints 或改 world_rules |
| `services/retrieval/common.py` | 7 处 `knowledge_constraints` | 检索源类型 | 改 `knowledge_world_rules` |
| `services/retrieval/search.py` | 831/854/876 | 检索结果分类 | 同上 |
| `services/retrieval/documents.py` | 240/344 | 知识索引映射 | 同上 |
| `services/retrieval_eval.py` | 129/159/182 | 检索评测 | 同上 |
| `domain/knowledge_entities.py` | 18/207/303/324/352 | 实体卡类别 | 移除或映射 |
| `services/automatic_configuration.py` | 114 | 自动配置分类清单 | 移除 |
| `ui/entity_experience.py` | 37/182 | 实体卡 UI | 移除 |
| `ui/step_views.py` | 53/66 | 步骤报告 UI | 改读 world_rules |
| `ui/web_research_tasks.py` | 120 | 研究任务分类 | 移除 |
| `ui/labels.py` | 124 | 标签 | 移除或改 |
| `storage/repositories/knowledge.py` | 805 | `_graph_node_type_for_category` 兜底映射 | 保留无害（兜底） |

> 关键原则：`constraints` 分类**存储层已不再接受**，但上述软引用只是"枚举/展示/检索类型"，
> 不触发写入，故留待抽取改造统一清理不会引入新的错误数据。

---

## 三、目标查询范式（这是本次重构的核心收益）

**1. 取某个实体在当前章节的全部有效事实**（生成时用）

```sql
SELECT k.fact_key, k.summary, k.content_json
FROM knowledge_items k
WHERE k.entity_id = :entity_id
  AND k.valid_from_chapter <= :chapter
  AND (k.valid_to_chapter IS NULL OR k.valid_to_chapter > :chapter)
  AND k.deleted_at IS NULL;
```
→ 同槽位（`fact_key`）只会命中**一条**，矛盾值天然消失。

> 注：真实列名为 `content_json`（结构化 payload，含 details 键值对），
> 非 `details_json`/`typed_data_json`——后两者在 schema 中不存在。

**2. 角色卡 / 势力卡 / 道具卡**（展示用，同一套 SQL）

```sql
SELECT e.*, k.* FROM entities e
LEFT JOIN knowledge_items k ON k.entity_id = e.entity_id AND k.deleted_at IS NULL
WHERE e.entity_type = 'character' AND e.story_id = :story_id
ORDER BY e.importance DESC, k.valid_from_chapter;
```

**3. 时间线**（事件即 Entity，按世界时间排序，章号兜底）

```sql
SELECT e.canonical_name, e.world_t, e.world_time_label, e.worldline_id,
       k.summary, k.chapter_no, k.content_json
FROM entities e JOIN knowledge_items k ON k.entity_id = e.entity_id
WHERE e.entity_type = 'event' AND e.deleted_at IS NULL
ORDER BY e.worldline_id, e.world_t, k.chapter_no;
```

世界时间轴（`world_t`）主导排序，`chapter_no` 仅作同刻事件间的兜底。
历史大事（`world_t` 小）与当前大事（`world_t` 大）自然分居时间轴两端，无需人为二分。

**4. 世界状态回溯**：把 (1) 对所有相关实体跑一遍，即得"第 N 章的世界快照"——
**不需要额外的快照表**，按需派生即可，避免双重维护。

**5. 关联查询（实体间引用，本次审查补充）**

```sql
-- "林越在第 30 章持有/参与/隶属的所有东西"
SELECT e2.entity_type, e2.canonical_name, ge.relation_type
FROM graph_edges ge
JOIN entities e1 ON ge.source_node_id = e1.entity_id
JOIN entities e2 ON ge.target_node_id = e2.entity_id
WHERE e1.entity_id = :entity_id
  AND ge.valid_from_chapter <= 30
  AND (ge.valid_to_chapter IS NULL OR ge.valid_to_chapter > 30)
  AND ge.deleted_at IS NULL;
```

这是小说生成最高频的查询之一（"林越现在有什么、属于哪、在哪"），
此前因引用字段全是纯文本而无法结构化执行，收编进 `graph_edges` 后得以成立。

---

## 四、分期实施路径

| 期 | 内容 | 改动范围 | 风险 | 验证方式 |
|---|---|---|---|---|
| **P0 地基** | 迁移 017 建 `entities` + 给 `knowledge_items` 加 6 列；写回填脚本（从现有条目按名经别名归并提供 entity_id、从 tags 解析 chapter_no） | 1 个 SQL + 1 个回填脚本，约 200 行 | 极低（纯加性，不改读取逻辑） | `tools/verify_*.py` 断言 schema 版本、回填后 entity_id 非空率 |
| **P1 写入侧** | ① 章节抽取（`common.py:781-834`）产出时填 `entity_id`/`fact_key`/`chapter_no`/`valid_from_chapter`；同 `(entity_id, fact_key)` 写入新值时把旧值 `valid_to_chapter` 置为当前章；② 动态槽位补齐（见 2.5：S1 补字段定义 + S2 补抽取 prompt + S3 补映射）；③ `constraints` 归位（见 2.7）；④ 事件填 `world_t`/`world_time_label`（见 2.6c）；⑤ 实体间引用统一收编 `graph_edges`（owns/member_of/located_in/participated_in 等，见 2.3） | `workflows/skills/common.py` + repository 写入 + `core/prompts.py` + `domain/knowledge_types.py` + `storage/repositories/knowledge.py`，约 650 行 | 低～中；**这一期就消除"同槽位矛盾"，让动态槽位、时间线、实体关联都真正有数据** | 新增验证脚本：连写 3 章同槽位，断言只剩一条有效；断言抽取产物含 `status`/`location` 槽位；断言事件带 `world_t` 且可排序；断言"林越持有 X"能通过 graph_edges 查回 |
| **P2 生成消费** | `build_generation_setting_context` 改为按实体 + 章号查询，替掉全量拼接；always 块加配额 | `context_assembly.py` + `setting_knowledge.py`，约 300 行 | 中（改变 prompt 构成，需对比生成效果） | 打印改动前后的 prompt 差异，人工比对 |
| **P3 展示层** | 角色中心/世界观/时间轴/关系图改为查实体表；`build_character_entity_cards` 换实现、保留签名 | `ui/entity_experience.py` + `api/app.py`，约 400 行 | 中（UI 面广，但逻辑更简单） | 现有 UI 冒烟 + 前端 `KnowledgeEntitiesView` 对照 |
| **P4 世界状态（可选）** | 若需要"第 N 章世界快照"持久化或加速，在 P2 查询之上加物化缓存 | 可选，约 150 行 | 低 | — |

**依赖顺序**：P0 → P1 → P2 / P3（P2 与 P3 可并行）。
**不做 P4 也不影响前三个目标。**

---

## 五、关键决策（已拍板）

六项决策已于 2026-09-04 由用户确认，记录如下。

**1. 实体识别由谁定？→ 自动归并 ✅**

按规范化名 + 别名组自动归并，误合并后期可通过拆分实体修复。
理由：当前 `data/` 下零真实数据，试错成本最低。
风险：误合并会污染数据，需在 P1 提供"拆分实体"的修复入口。

**2. `fact_key` 的粒度？→ 两类并用 ✅**

- 沿用 `knowledge_types.py:14` 现有类型化字段（`appearance`/`personality`/`abilities`/`affiliations`…）；
- 新增通用动态槽位 `location`/`status`/`holder`/`current_goal`（现有 `characters` 规范缺这几项，见 2.5）。

**补充决策：变化语义走「追加 / 取代」而非「静态 / 动态」**——详见 2.4。

**3. `entity_type` 与现有 `category` 的关系？→ 保留 category 作兼容 ✅**

`category` 是旧的条目级维度，决定字段结构，原 12 个值、**决策后 11 个**（`constraints` 归位，见 2.7）；
`entity_type` 是新的实体级维度，是查询主维度（`event` 用于时间线、`character` 用于角色卡）。

保留 `category` 的原因：它仍描述事实自身的性质，且现有 UI 大量依赖它；
但**不再作为查找主路径**——查找改由 `entity_id` + `fact_key` 承担。
这样也解决了旧设计的一个缺陷：一条事实的 category 归属常是模糊的
（"林越抵达京城" 既是角色状态变化、又是事件、又涉及地点，旧系统强制三选一，导致信息割裂）。

**4. 时间用「章号」还是「世界内时间」？→ 两个轴拆开，双轨并存 ✅**

- `chapter_no`：叙事进度，整数可靠排序，用于"生成时注入到哪一章为止"的区间查询；
- `world_t`（+ `world_time_label`）：世界观内时间，可排序键，用于时间线排序与因果先后；
- 两者**不对应**（回忆/同时异地/多线都会错位），各司其职，不能互相替代。

（本决策由早期"`time` 仅展示用"的说法升级而来，详见 2.6c。）

**5. `constraints` 分类如何处理？→ 取消，按层级归位 ✅**

`rules` 表（跨故事元规则）与 `world_rules`（故事内规则）已足够承载全部需求，
`constraints` 分类因语义与两者重叠、且章节抽取从不产出它而取消。
归位规则与代码改动点见 2.7，归入 P1。

**6. 事件的时间与关联如何表达？→ 世界时间轴 + 复用 worldline ✅**

- 事件 = Entity（`entity_type='event'`），用 `world_t` 排序、`world_time_label` 展示；
- 多线需求复用已有 `worldline_id`（不新增列，避免语义重叠）；
- 事件参与者复用 `graph_edges`（`relation_type='participated_in'`），结构化关联到角色/地点实体。

详见 2.6c。

---

## 六、风险与约束

1. **实体识别是唯一的失控点**，其余都是机械改动。P1 建议只对"名字能精确匹配上"的做归并，别名识别放到后面。
2. **P2 会改变 prompt 构成**，可能让生成结果变化（变好或变差都有可能），务必先看 diff 再决定。
3. **现有 UI 大量依赖 `load_knowledge_base` 的返回结构**，P3 改造要保留该函数的返回形状，只在内部换实现。
4. **本文结论均来自静态代码分析**，`data/` 下无真实数据可供实证。若之后产生了真实项目，P0 的回填脚本需要先在副本上试跑。
5. **章号回填依赖非正式约定**：`chapter_no` 现仅存于 `tags` 的 `chapter:{n}` 字符串（`common.py:826`）
   与 pending 条的 `source_chapter_no`（`common.py:834`，**落库即丢**，`knowledge_items` 无此列）。
   回填脚本必须**容错**——解析不到章号时留 `NULL` 而非报错；否则存量脏数据会让脚本崩溃。
6. **`version_scope` 是隐式维度**：原作（`canon`）与二创（`project_main`）同名角色靠它隔离
   （`services/memory/knowledge.py:365`）。任何按 `canonical_name` 的查询若忽略它，会串版本。
7. **引用收编的"误关联"风险**：把 `owners`/`members`/`participants` 等纯文本转成 graph_edges 边时，
   LLM 抽取的实体名可能与真实实体不匹配（"林公子"≠"林越"），导致边指向错误的实体或空实体。
   P1 必须**先做实体归并、再建边**，且边在待审队列里可人工改指向——否则会把文本里本来就模糊的引用，
   固化成结构化错误。

---

## 七、与既有改造计划的关系

本项目笔记中已记录的待办（`.workbuddy/memory/`）与本次重构的对应关系：

| 既有待办 | 被本次哪一期覆盖 |
|---|---|
| W1 抽取默认 `injection_policy: retrieval` | **已完成**（`common.py:833`） |
| W2 同槽位可取代 | **P1**（用 `valid_to_chapter` 实现，比 `superseded_by` 更直接） |
| R1 always 配额 + 检索保底预算 | **P2** |
| R2 近期上下文确定性注入 | P2 之后可基于 `chapter_no` 精确取最近 K 章，成本大幅降低 |

即：**本次存储重构实际上是把 W2/R1/R2 三条待办合并成一条更根本的路**。
先做存储，再做读取，比逐条打补丁更省事。
