# 资料提取重构方案（Material Extraction Refactor）— 执行规格

> 状态：设计已锁定，可直接执行（截至 2026-09-04）
> 关联：与已完成的 Entity-Fact-Relation 存储重构（迁移 017 / schema v17）强耦合——目标是让「导入资料」充分转化、按类型产出不同形态、并作为原著基线在同人生成时被叠加/覆盖。
> 本文件为**执行规格**：所有设计决策已锁定（§3），按 §4 分期逐步实现，直至满足「完成定义」（§7）。讨论中发现的新事实仍回填对应小节并追加变更记录，但不再保留平行可选方案。

## 1. 目标与非目标

**目标**
- 让传入资料充分转化为规范条目（解决召回不足、长资料后段漏填）。
- 按资料类型产出不同形态：原著 → 带时间线；图鉴（技能/道具/角色）→ 独立条目。
- 原著作为「基线」，同人生成时自动沿用、可被覆盖。

**非目标**
- 不动存储引擎：迁移 017 已就位（见 §2 事实），本重构只填充已有列。
- 不做生成侧（context_assembly 多查询路由）：其依赖本方案先提供正确归类的条目。

## 2. 已核实前提（代码事实，非推断）

| # | 事实 | 证据 |
|---|---|---|
| G1 | 资料提取 prompt 列了 12 类（含已废弃的 `constraints`，见 F22），让模型填自由 `details` 字典 | `extract_reference_knowledge_prompt`（`core/prompts.py:1595`），分类说明 `:1633-1645` 含 `constraints`；自由字典处 `:1659` `{字段名:字段内容}` |
| G2 | 资料路径直接落库，缺章节路径的「待审核构造器」 | `extract_reference_knowledge`（`common.py:1203`）→ `queue_pending_knowledge_items`（**定义 `services/memory/knowledge.py:337`**，调用点 `source_workflows.py:479/606/1434`）直接；章节路径多一层 `build_pending_knowledge_from_setting_extraction`（`common.py:793`）。资料条目因此缺 `setting_field`/`fact_key`/`source_chapter_no` |
| G3 | 细粒度槽位展开只在章节路径用 | `DYNAMIC_SLOT_KEYS`（`common.py:714`）仅 `:817` 用，资料路径不调用 →「一个角色一条大条目」 |
| F1 | `ExtractedKnowledgeItem`（`schemas.py:335`）当前无 `setting_field`/`fact_key` 字段 | — |
| F2 | pending 归一化全量透传 | `normalize_typed_knowledge_item`（`knowledge_types.py:136`）`dict(item)` 保留，`fact_key`/`entity_id` 设了即透传 → 构造器设键后 confirm 链路可消费 |
| F3 | `knowledge_items` 已具全套取代列 | 迁移 017:36-42 加了 `entity_id`/`fact_key`/`chapter_no`/`valid_from_chapter`/`valid_to_chapter`/`superseded_by`/`merge_policy` |
| F4 | canon/fic 轴由 `entities.version_scope` 承载 | 017:15 `version_scope TEXT NOT NULL DEFAULT 'project_main'`；唯一索引含该列（017:30）。`knowledge_items` 无该列（符合设计，非缺陷） |
| F5 | 原著当前天然 `version_scope=canon` | `source_workflows.py:594` `version_scope = "canon" if batch.get("scope")=="canon" else "project_main"` |
| F6 | 区分能力已大半存在 | `extraction_presets.py` 已有 8 专家预设（`timeline_expert` mode=`timeline` 等）+ `KNOWLEDGE_EXTRACTION_PLAN_PRESETS`；`enabled_categories` 按资料可配（`ingestion_tasks.py:434`） |
| F7 | 现有取代按 `(entity_id, fact_key)` 只在同一 continuity 生效 | `isolation_domain`（`entity_identity.py:57`）第 4 维 = `version_scope`；`_apply_supersession`（`knowledge.py:331`）按 entity_id 匹配 |
| F8 | `version_scope` 在读取路径被真实透出 | `knowledge_center.py:311/386`、`retrieval/documents.py:167/281/370` |
| F9 | `worldline_id`（世界线）是一等隔离维度，可支撑多独立原著 | `entities` 唯一索引（017:30）含 `worldline_id`；`knowledge_items` 列含 `worldline_id`（001:25+）；`isolation_domain`（`entity_identity.py:57`）第 3 维 = `worldline_id`；`GLOBAL_WORLDLINE_IDS` 把 `canon`/`shared`/`common`/`global`/`all` 视为全局世界线（空） |
| F10 | 资料导入路径不分配 worldline_id → 多独立原著同名角色会撞同一实体 | `source_workflows.py:595` `enriched["worldline_id"] = item.get("worldline_id") or DEFAULT_WORLDLINE_ID`（="main"）；提取 prompt 当前不要求输出 worldline_id → 所有导入资料默认落 "main" + `version_scope=canon` → 同名实体 `entity_id` 相同而碰撞 |
| F11 | 读取侧已有世界线过滤（**修正：存在于两个消费层，`load_knowledge_category_rows` 本身不带 worldline 参数**） | `load_knowledge_category_rows`（`storage/repositories/knowledge.py:568`）签名仅 `(conn, category)`，返回该分类全部行；世界线过滤真实存在于：① `setting_knowledge._setting_worldline_allowed`（`:151`，prefer/strict，装配处 `:524`/`:555`/`:602` 从 `profile.worldline_retrieval_mode` 取）；② `retrieval/search._worldline_allowed`（`:133`，mismatch 且非 strict 时降级，`:245`）。章节生成提取侧已世界线感知（`common.py:771-787` 由 `creative_profile.worldline_id` 取 worldline、非 main 时 `version_scope="au"`） |
| F12 | **生成时 worldline 是「项目/档案级」，章节本身无 worldline 关联** | `context_assembly.py:428-430` `worldline_id = str(profile.get("worldline_id") or "")`（来自 `load_creative_profile`）；章节表无 `worldline_id` 列。即今天整本书共用一个世界线，章节不知道自己属于哪个世界 → 无限流「章节换世界」需新增章节→世界线关联（见 D13） |
| F13 | **源文档与抽取条目分层存储，原文天生不可变** | `source_documents`（001:90，含 `source_id`/`title`/`source_type`/`canon_status`/`metadata_json`）+ `source_segments`（存原文内容，014:108 被视图引用）；抽取产出 `knowledge_items`（`source_id` 外键，014:56/71）指向源文档、**抽取流程不回写源文档**（`source_workflows.py:328` `ingest_external_source_file(overwrite=True)` 只更新导入产物，不动原文）。故"导入资料"抽坏也不伤原始文本 |
| F14 | **不存在「复制/派生源资料文档」功能** | 全仓仅 `copy_story`（整本故事复制，函数 `stories.py:1606`，端点 `api/app.py:921`）、`copy_setting_items`（设定复制，`setting_knowledge.py:371`）；无 `copy/duplicate/fork source_document`。用户印象中的「复制资料」应为 `copy_story` 或重抽取 `compare_extracted_items`（`source_workflows.py:719`，已有「已有 vs 新条目」比对 diff）。无需新造源文档复制功能 |
| F15 | **层级建模列已齐备，零 schema 改动即可支持「共享原著库 + 每故事 fork」** | `knowledge_items`（001:127-153）已含 `story_id`（129）、`worldline_id`（136）、`setting_scope`（144）、`canon_status`（135）、`source_id`（141）；`isolation_domain`（`entity_identity.py:57`）=`(setting_scope, story_id, worldline_id, version_scope)`，且 `setting_scope!="story"` 时清空 `story_id`（:64-65）。=> 既有的 `setting_scope` 维度天然区分「故事级(story) vs 项目级共享(project)」，无需新列即可建模「项目共享原著库(project 作用域) + 每故事 fork(story 作用域)」 |
| F16 | **当前导入把原著 canon 卡在单个故事作用域（规划缺口）** | `source_workflows.py:591` `enriched["story_id"] = str(story_id or "default")` 给导入条目赋 story_id → 经 `isolation_domain` 默认 `setting_scope = "story" if story_id else "project"`（`entity_identity.py:63`）→ 导入的 canon 条目落 `setting_scope="story"`、绑死在某 `story_id`。=> 多故事无法共享同一原著库：要么各自重导（canon 重复且分叉）、要么 `copy_story`（连编辑一起克隆，非「从库 fork」）。这正是本规划需补的层级缺口（见 D14/D15） |
| F17 | **`world_t` 已在确认链路被写入，但资料时间线无兜底来源（修正：原「从未写入」结论错误，修订 18）** | `_upsert_entity_master`（`storage/repositories/knowledge.py:865-916`）**确实**读取 `item.get("world_t") or typed_data.get("world_t")` 并写入 `entities.world_t`/`world_time_label`，且 world_t 为空时回退 `_chapter_no_from_item(item)` 的 chapter_no。=> 真实缺口是：**资料 timeline 事件的 `chapter_no` 为空（无 `source_chapter_no`），故 world_t 兜底也空** —— 需由构造器在条目上填充 `world_t`（或由 `sequence_order` 映射），而非「写入路径从不写 world_t」 |
| F18 | **资料时间线无原生排序列** | `knowledge_items`（001:127-153 + 017:36-42）与 `pending_knowledge_items`（001:155-178）均**无 `source_segment_index` 列**（仅有 `source_id`/`segment_id`）；`source_segment_index` 只存在于 `ExtractedKnowledgeItem` 输出结构（`schemas.py:363`），且仅用于显示标签（`schemas.py:1436`）。=> 想「按资料段落顺序排时间线」无法用原生列持久化/查询，必须加 `sequence_order` 列（D8 修正）或退化进 `content_json` |
| F19 | **不存在 `chapters` 表；章节是文件系统 markdown，arc 是带元数据 API 的文件实体** | 全仓迁移无 `CREATE TABLE chapters`；章节正文 `content.py:1006` → `chapters/chapter_{no:03d}.md`，元数据 `chapter_{no:03d}.meta.json`（`stories.py:1325`）；**arc 已是一等文件实体**：`content.py:133 arcs_path` / `:143 _arc_meta_path` → `arc_{no:03d}.meta.json`，且有 `save_arc_metadata`（`:456`）/ `load_arc_metadata`（`:650`）；卷亦为文件 `volume_{no}.meta.json`（`stories.py:1326`）=> **D13 无需 DB 迁移，写 arc 元数据 JSON 即可** |
| F20 | **`_resolve_entity_id` 不感知 `version_scope`，硬编码 `project_main`**（关系层 canon/二创隔离失效） | `knowledge.py:921` 签名无 version_scope 参数；`:939 domain = (setting_scope, story_id, worldline_id, "project_main")`、`:955` 复用匹配、`:964` INSERT 三处均硬编码 `'project_main'`。该函数仅用于**关系边端点解析**（`:1133`/`:1137`/`:1234`）=> 原著关系的边会挂到 `project_main` 实体，与二创关系撞同一节点。（对比：主链路 `_compute_entity_fact:317` 用 `isolation_domain(item)` 含 version_scope，`_upsert_entity_master:841` 的 `:915` 也正确处理 → 实体主档侧 (iii) 前提成立） |
| F21 | **`ExtractedKnowledgeItem.category` Literal 仍含 `constraints`** | `schemas.py:348` Literal 列出 12 个值（含 `"constraints"`），但 `KNOWLEDGE_TYPE_FIELDS`（`knowledge_types.py:21`）只定义 11 类、无 constraints => 模型若输出 `constraints`，`normalize_typed_knowledge_item` 取不到字段规格（返回空元组），A 期字段引导与 D 期校验会静默放过该条目，产出无字段孤儿 |
| F22 | **提取 prompt 仍显式列出 `constraints` 分类**（与 D5 直接矛盾） | `prompts.py:1645`「可用分类说明」列了 `- constraints：硬性约束…`；`:1656` 输出枚举也含 `constraints`。D5 已决定排除该分类，且修订 12 只改了 schema Literal（F21），**prompt 侧未同步** → 模型仍被要求输出被取消的分类 |
| F23 | **长资料跨片段无上下文接力：别名上下文只读书面已确认实体，且 `previous_index`/`next_index` 无人消费** | `alias_context` = `_format_entity_alias_context(project_name)`（`common.py:1184`）→ `load_entity_aliases(project_name)` 读**已落库确认**的 `entity_alias_groups`。新导入一部原著时前 N 段该上下文为空 => **每段孤立抽取**，段 1 的「林越」与段 30 的「林公子」在抽取期无法归一。另 `split_reference_text` 已算出 `previous_index`/`next_index`（`reference_chunking.py:253-254`）但**全仓无读取点**；`split_text_by_boundaries` 支持 `overlap_chars` 但 `split_reference_text` 未传 → 实际零重叠 |

| F24 | **章节路径 setting_field 的真实来源是三元组 `SETTING_EXTRACTION_KNOWLEDGE_FIELDS`（`common.py:702`），而非 `SETTING_FIELD_SPECS`** | 三元组仅 4 条：`new_characters→characters`、`world_updates→world_rules`、`timeline_updates→timeline_events`、`foreshadowing_updates→narrative_techniques`；细粒度槽位由 `DYNAMIC_SLOT_KEYS`（`:714`，9 键）展开（`:817`）。`SETTING_FIELD_SPECS`（`setting_knowledge.py:22`）是「设定字段→分类」正向映射（story memory 用）——资料路径**反向复用不成立**：`world_rules` 有 4 个候选源字段（au_rules/world/active_constraints/power_systems），且 `items`/`abilities`/`writing_style`/`dialogue_style` 在其中无对应 |
| F25 | **槽位合并策略真实键名（`FACT_MERGE_POLICY`，`entity_identity.py`）** | replace = `location`/`status`/`holder`/`owners`/`owner`/`current_goal`；append = `users`/`abilities`/`appearance`/`personality`。`_NO_SUPERSESSION_FACT_KEYS = {"timeline","time","causes","outcomes","order_hint"}`（`order_hint` 已被现有代码预留——P6 键名选择与之吻合）。注意 `DYNAMIC_SLOT_KEYS` 的 `holding` **不在** `FACT_MERGE_POLICY` 中 → `merge_policy_for` 兜底 `append` |

| F26 | **`consolidate_extracted_knowledge` 的白名单会丢字段（A 期新增字段的隐藏陷阱）** | `compact_items`（`common.py:1272-1288`）只保留若干键。**修订 22 修正（实际实现时核实）**：`source_segment_ids`/`source_segment_titles`/`merged_from_pending_ids`/`extraction_mode` **并非真丢**——`enrich_consolidated_knowledge_items`（`source_workflows.py:1357-1383`）会从 source_items 回填它们；**真正丢的是 `typed_data` 和 `schema_version`**（enrich 不补）。=> 第 0 步已把 `typed_data`/`schema_version` 加回 `compact_items`；A 期新增的 `setting_field`/`fact_key`/`aliases`/`order_hint` 同样需进白名单 + consolidate prompt 回填（F30） |
| F27 | **章节构造器显式硬编码三处，资料构造器「对称」但取值不同** | `build_pending_knowledge_from_setting_extraction`（`common.py:793`）对每条硬编码 `setting_scope="story"`（`:58`/`:98`）、`injection_policy="retrieval"`（`:61`/`:103`）、`source_chapter_no=chapter_no`（`:62`/`:104`）。资料构造器须在**同三处取不同值**：`setting_scope="project"`（D14）、`version_scope="canon"`、无 `source_chapter_no`（→`_chapter_no_from_item` 返回 None → append-only）；`injection_policy` 建议仍 `retrieval` |

| F28 | **`queue_pending_knowledge_items` 是 4+ 条提取路径的共享下游** | 调用方：章节生成 `skills/generation.py:827`（经 `build_pending_knowledge_from_setting_extraction` `:821`）、外部资料 `source_workflows.py:479/606/1434`、互动写作 `interactive_writing.py:1127`、网络研究 `web_research_tasks.py:773`。=> 凡在 `queue_pending_knowledge_items`/`consolidate`/`normalize`/`confirm`/`sync_knowledge_category` 这一共享层做的改动，**改一次全路径同时生效**（需全路径回归），不是资料路径独享 |

| F29 | **`version_scope` 实为三值：`canon` / `project_main` / `au`** | 章节路径 `common.py:779`：`version_scope = "project_main" if worldline_id=="main" else "au"`；资料导入 `source_workflows.py:594`：`canon if batch.scope=="canon" else project_main`。=> 规划按二值（canon/project_main）建模**不完整**：非 main 世界的同人产出 `au`，B 期合并优先级 `au > project_main > canon` 里的 au 正来自此路径；非 main 世界的「canon 基线 + au 覆盖」叠加需明确 |
| F30 | **consolidate 是 LLM 往返，`compact_items` 白名单补字段只能保「输入→prompt」段，输出段仍会丢** | `consolidate_extracted_knowledge`（`common.py:1258`）把 `compact_items` 序列化进 prompt → LLM 返回 → `KnowledgeExtractionResult` 重建条目。若 consolidate prompt **不要求回填** `setting_field`/`fact_key`/`aliases`/`order_hint`，A 期新增字段在「prompt→输出」段仍被丢弃（F26 只修了输入段）=> 须同步在 `consolidate_extracted_knowledge_prompt`（`prompts.py:1694`）要求回填这些字段 |

### 2.5 存储完备性对账矩阵（用户 2026-09-04 追问「提取后存储是否完备」，修订 12 更新）

（✅ 已完备 / ⚠️ 基本完备有缺口 / ❌ 不完备）

| 维度 | 结论 | 现状 | 缺口 / 需补 |
|---|---|---|---|
| **隔离 · 世界线** | ✅ | `worldline_id` 两表均有列、隔离域含之（F9） | 仅导入侧不分配（F10/D10 修）；派生依据改 `source_id`（D16） |
| **隔离 · 库/故事** | ✅ | `setting_scope`+`story_id` 两表均有列（F15） | 仅导入侧卡 story（F16/D14 修）；**须用 NULL 非 `""`**（外键 ON） |
| **隔离 · 原著/当前（实体主档）** | ✅ | `_compute_entity_fact:317` 用 `isolation_domain(item)` 含 version_scope；`_upsert_entity_master:915` 正确落库 | 无；(iii) 前提成立 |
| **隔离 · 原著/当前（关系边）** | ❌ | `_resolve_entity_id:939/955/964` 硬编码 `project_main`（F20） | **新增修复**：加 version_scope 参数纳入 domain |
| **隔离 · 章节/世界线** | ⚠️ | 无 `chapters` 表（F19）；arc 已是文件实体 | D13 改 arc 元数据 JSON，**零迁移** |
| **条目形式 · 分类/字段** | ⚠️ | `category`+`content_json`(自由字典)+importance 等 | 自由字典待 A 期规范化；`fact_key`/`setting_field` 不在输出 schema（F1，D4 adapter 算）；**Literal 仍含 `constraints`**（F21/D5） |
| **条目形式 · 取代** | ✅ | `entity_id`/`fact_key`/`valid_*_chapter`/`superseded_by`/`merge_policy`（F3） | 仅 `_apply_supersession` 漏 `superseded_by`（D4 修） |
| **溯源** | ✅ | `source_id`/`segment_id`/`canon_status`（F13） | 无 |
| **时间线 · 排序键** | ⚠️ | `world_t` 已写入（F17 修正：`_upsert_entity_master` 读 `item.world_t`、回退 chapter_no），但**资料事件无 chapter_no → 兜底空**；无 `sequence_order` 原生列（F18） | 加 `sequence_order` 列 + 写入链（D8）+ 构造器填 `world_t` |
| **时间线 · 事件实体** | ⚠️ | `entity_type=event` + `world_t` 机制存在且已写入 | 构造器须为资料事件填 `world_t`（无 chapter_no 兜底，D8） |
| **fork 副本隔离** | ❌ | `entity_id` 是域哈希且已固化在行内（entity_identity.py:75-79） | **逐行复制会共享 entity_id** → 必须重算（D15 修正） |

**一句话结论**：隔离的**存储维度**已完备（世界线/库/原著当前/关系四层列齐全），但**写入侧有三处未接通/写错**（关系边硬编码、章节无表、fork 不重算 entity_id）；条目形式基本完备；**时间线的真缺口是「无 `sequence_order` 列 + 资料事件缺 world_t 来源」**（D8 已补写入链，F17 修正）。修正后整轮重构**仅 1 处 schema 新增**（`sequence_order`），其余零迁移。

## 3. 锁定设计决策

| # | 决策点 | 锁定选择 | 理由 |
|---|---|---|---|
| D1 | 原著↔同人覆盖机制 | **(iii) 读取期叠加（三值版本，修订 18 补）** | 保留平行实体（不动 `version_scope`）；`version_scope` 实为**三值**（F29）：`canon`（原著基线）、`project_main`（main 世界同人）、`au`（非 main 世界同人）。生成读取期做「canon 基线 + 同人叠加」合并，合并优先级 `au > project_main > canon`（同世界线内；跨 worldline 由 D12 分流）。语义最干净，贴合系统已有的多版平行实体建模；不滥用章号取代、不丢 canon 信号、不需哨兵。（被否方案见 §6） |
| D2 | 长资料并行子抽取粒度 | 按 mode 分组（**修正：mode 词表为 9 键**） | 真实 `EXTRACTION_MODE_INSTRUCTIONS`（`prompts.py:1556`）键 = `general`/`deep`/`characters`/`relationships`/`timeline`/`world`/`style`/`strict_canon`/`fanfic_reference`，且预设 mode 值与之完全一致（`extraction_presets.py`）。并行子抽取按该词表分组（资料路由常用子集 4-6 路：characters/relationships/timeline/world/style + 视 preset 追加 strict_canon）。原「6 路（general/character/relationship/timeline/setting/style）」中 character/setting 系拼写错误（实为 characters/world），且漏 deep/strict_canon/fanfic_reference |
| D3 | C 期召回校验默认 | 短资料关、长资料开 | 控制 token 成本；先 A+A' 建质量基线再开 |
| D4 | `setting_field`/`fact_key` 来源 | 构造器设 **`setting_field`**（非直接设 fact_key，修订 21 修正）：① **实体类条目（characters/items/locations/organizations，排除 relationships——关系走 `graph_edges` 非 fact 取代）** details 含 `DYNAMIC_SLOT_KEYS`（`common.py:714`，9 槽位）中的键时，拆「实体×槽位」、`setting_field = 槽位名`（同章节路径 `:817` 的做法）；② 无槽位键或非实体类 → 不设 setting_field。**`fact_key` 由确认链路的 `_compute_entity_fact`（`knowledge.py:318`，读 `setting_field or fact_key`）统一转出**，无需构造器直接填 | `SETTING_FIELD_SPECS` 是「设定字段→分类」**正向**映射，反向不唯一（`world_rules` 4 候选源字段）且多类别无对应（F24）；章节路径真实用三元组 `SETTING_EXTRACTION_KNOWLEDGE_FIELDS`（`common.py:702`，仅 4 条）。**关键（修订 21）**：`knowledge_items` **无 `setting_field` 列**（仅 `fact_key`），`setting_field` 是存于 content_json 的中间值、由 `_compute_entity_fact` 转成 fact_key → D 期「setting_field 必填」必须配套「setting_field 取值规则」，否则 queue 会拒掉全部资料条目。不由 LLM 直接输出 |
| D5 | `constraints` 处理 | 资料提取只产出 11 类（排除已取消的 `constraints`）；**并须从 `ExtractedKnowledgeItem.category` 的 Literal 中移除 `"constraints"`**（`schemas.py:348` 现列 12 值） | 对齐 09-04 日志：`constraints` 的 40+ 软引用待全面改造清理。`KNOWLEDGE_TYPE_FIELDS`（`knowledge_types.py:21`）已仅 11 类，但输出 schema 仍允许第 12 值 → 模型输出 `constraints` 时字段规格为空、A/D 期校验会静默放过（F21）。只改 prompt 不改 Literal = 缺口仍在 |
| D6 | 资料类型识别 | **复用现成的 `infer_content_kind`**（`reference_chunking.py:179`，已依据 source_type/标题关键词返回 `timeline`/`character`/`relationship`/`world_rule`/`style`/`narrative`），再映射到 preset mode（`world_rule`→`setting`、`narrative`→`general`）+ 用户可覆盖 | 自动推断 + 用户可覆盖。该函数**已存在且已在分块链路中使用**，无需新写类型识别；仅在 `MATERIAL_TYPE_PRESET_MAP` 前加一层 mode 映射即可 |
| D7 | 多原著源互替 | 后导入优先（**仅限同一 worldline_id 内**）；**同一 canon 的「再导入识别」须另定（修订 18 补）** | 每个独立原著 = 独立 worldline（D10），跨 worldline 不互替；仅当同一原著的多次导入（同 worldline 不同 source_revision）才 last-import-wins。**缺口**：`source_id` 按导入文件生成，同一 canon 换文件重导 → 不同 `source_id` → 不同 worldline → 平行世界、实体翻倍且互不取代 => 需补「再导入识别」（按 source 标题/用户显式指定 worldline 覆盖） |
| D8 | 原著时间线排序 | **新增 `sequence_order INTEGER` 列 + 明确计算与写入链（修订 21 补）**：构造器计算 `sequence_order = source_segment_index × K + order_hint`（K 建议 1000，段内序号上限），作为条目字段入 content_json；**`sync_knowledge_category` 的 INSERT 同步写该列**（018 迁移加列 + INSERT 加字段）。事件实体另落 `world_t`（F17：`_upsert_entity_master` 读 item.world_t，资料事件由构造器填 world_t=sequence_order） | 经核实 `source_segment_index` **不是** `knowledge_items`/`pending` 的列（F18），故「按段落顺序排序」无法零迁移；**修订 21 补**：原「加列」未指定谁计算、谁写入——`sync_knowledge_category` 的 INSERT（`knowledge.py:398-472`）与 `_compute_entity_fact`（`:308-328`）均无 `sequence_order`，不加写入则列恒 NULL。故 D8 须同时指定「构造器算 → content_json → sync 写列」。这是整轮重构**唯一** schema 新增列 |
| D9 | 被否方案 | (i) 强行兼容、(ii) 共享实体 均不采用 | 见 §6 简述 |
| D10 | 多独立原著的世界线归属 | 每个独立导入原著 = 独立 `worldline_id`（导入时由 source 标题/slug 确定性派生，用户可覆盖） | 隔离域第 3 维已是 worldline_id（F9）；无限流各原著是独立世界，必须分世界线否则同名角色撞同一实体（F10）。canon/同人轴嵌套在 worldline 之下 |
| D11 | 跨世界主角的世界线分类 | **作者原创主角（含常驻原创角色）→ `worldline_id="main"`（当前故事主线）；原著各世界角色 → 各自 canon worldline** | **用户澄清（修订 19）**：主角属于当前故事，`main` = 本项目主线（`common.py:779` 非 main 才标 au），原著与当前故事相互独立、各世界作附属——故主角落 main 正确、无冲突；读取期 D12 的「main 恒注入 + 当前章节 worldline 注入」正对应「主线为主、其余时间线附属」。上一轮「待重审」系误读（把跨世界主角当成 canon 角色跨世界）。遗留唯一窄边缘见 D19。逐实体分类（提取 prompt 指导 + `custom_instructions` 注入清单），非逐来源 |
| D12 | 多世界线读取注入 | 读取期：main 世界线恒注入 + 当前章节 `worldline_id` 注入；参照 `worldline_mode="prefer"` 语义（优先指定世界线、回退 main） | 世界线过滤已在 setting/retrieval 两消费层实现（F11 修正）；`merge_worldline_baseline` 自行做 worldline 作用域查询（不依赖 `load_knowledge_category_rows` 的 worldline 参数——该参数不存在）；(iii) 叠加在每个 worldline 内做 canon/au 合并，再把多个 worldline 事实汇进生成上下文 |
| D13 | **章节→世界线关联粒度** | **arc/卷级，写进 arc 元数据 JSON（零 DB 迁移）**：在 `arc_{no}.meta.json` 增 `worldline_id` 字段（经 `save_arc_metadata`/`load_arc_metadata`，`content.py:456/457`）；章节的 worldline 经其所属 arc 解析，空则回退 `creative_profile.worldline_id` | **修正（原方案错误）**：原写"给 `chapters` 表加列 + 018 迁移"，但**不存在 `chapters` 表**——章节是文件（`content.py:1006` → `chapter_NNN.md`，F19）。而 arc 本就是带元数据读写 API 的文件实体，直接写 JSON 即可，**连 018 迁移都不需要**。arc 级最贴合「主角按 arc 换世界」；卷（`volume_N.meta.json`）亦可选作更粗粒度 |
| D14 | **原著库的存储作用域** | **项目级共享**：导入原著 canon 条目打 `setting_scope="project"` + **`story_id=None`（NULL，不可写空串）**；**非 canon 资料的作用域也须一并明确（修订 18 补）** | **修正（原方案有缺陷）**：原写 `story_id=""`，但 `db.py:95` `PRAGMA foreign_keys = ON` 强制开启，且 `knowledge_items.story_id` 有 `FOREIGN KEY ... REFERENCES stories(story_id)`（001:150）；空串是非 NULL、无父行 → **触发外键失败**。代码既有约定是 `story_id or None`（`storage/repositories/knowledge.py:969`）。**落地机制（修订 15 补）**：确认路径 `_append_knowledge_items_in_transaction`（`services/memory/knowledge.py:419`）**从不设置 `setting_scope`**，它由 `isolation_domain`（`entity_identity.py:63`）按 `story_id` 是否为空推导（空 → `project`）；故 D14 只需**导入路径不注入 `story_id`**——当前 `source_workflows.py:591` `enriched["story_id"] = str(story_id or "default")` 对**所有导入**（含非 canon）都注入 "default"，须按资料类型分流：canon → 不注入（project 库）；非 canon（project_main/图鉴参考）→ 是否仍绑定故事需定 |
| D15 | **故事 fork 原著库的方式** | **写时复制（COW）＋ 必须重算 `entity_id` ＋ 同步重建 `entities` 主档行（修订 18 补）**：故事绑定原著时，把 `project` 作用域的 canon 条目复制进 `setting_scope="story"`+`story_id=X`（带 `forked_from_library_id`/`source_id` 溯源）；**复制时不得沿用原 `entity_id`，须用 story 作用域的域元组重新调用 `entity_id_for`**，并同步：① 重建关系边端点；② **为每个新 entity_id 建立对应的 `entities` 主档行**（否则 knowledge_items 指向不存在的 entity_id，实体中心/关系解析/merge 查询会缺行——confirmed 链路靠 `_upsert_entity_master` 建主档，复制路径不调它） | **修正（原方案"隔离自动保证"不成立）**：`entity_id_for`（`entity_identity.py:75-79`）是 `(entity_type, name, setting_scope, story_id, worldline_id, version_scope)` 的确定性哈希，且**已固化在每行 `entity_id` 列**中。若逐行复制却沿用原 entity_id，副本与库**共享 entity_id** → `_apply_supersession` 按 `(entity_id, fact_key)` 匹配会跨库污染。=> 隔离只有在**重算 entity_id 并补建主档**后才成立，不是免费的。本操作属下游能力，不在 refactor 1 提取内 |

| D16 | **`worldline_id` 的派生依据** | 用**不可变的 `source_id`**（资料文档 ID）确定性派生，**不用标题/slug** | 原 D10 写"由 source 标题/slug 派生"有缺陷：标题/slug 可变，用户改名资料 → 派生 worldline_id 漂移 → `entity_id`（含 worldline 维度）全部重算 → 该原著下所有实体与事实失效重建。用 `source_id` 则稳定。用户仍可在导入时覆盖 worldline_id（覆盖值须落库持久化，不随标题变化） |
| D17 | **「跨世界角色清单」的落点与匹配** | 清单存于 ingestion task 的 `configuration.cross_world_characters`（字符串数组）；与提取条目匹配时用 `normalize_name`（`entity_identity` 已有）做归一化比较，命中则强制 `worldline_id="main"`；未命中则继承批次 worldline_id | 原 D11 只说"用户提供清单、经 `custom_instructions` 注入 prompt"，未定义清单存哪、如何与条目名匹配（别名/异体字会导致漏判） => 补齐落点与归一化匹配规则，避免清单形同虚设 |
| D18 | **跨世界常驻的 canon 角色**（招揽原著角色随行）的 worldline | **升入 `main`（随身队友）**：故事 scope 下把该实体的 worldline 从 canon worldline 改为 `main`（重算 entity_id，一次性「晋升」操作）；canon 身份靠 `source_id`/`source_title` 溯源保留，原著里的佐助仍在 canon 库（`project` + canon worldline + `version_scope="canon"`） | **用户拍板（修订 20）**：主角落 main 无争议（D11）；canon 同伴升 main 更简单自然——`main` 在 D12 被每章恒注入，升入 main 即自动「随主角每章出现、携带成长状态」，无需新写「随行注入」机制；「留老家」反而要额外发明一套 companion 注入规则。canon 身份由溯源字段保留、不靠 worldline，故无损失 |

> 上述决策已锁定。若需调整，在对话中提出即可，会回填本文件并追加变更记录（仍保持单路径执行，不重新展开平行方案）。
>
> **世界线相关决策的重构归属（ clarifying）**：多世界适配横跨用户的两个重构。① **资料提取(refactor 1) 负责**存储隔离——D10（每部独立原著=独立 `worldline_id`）+ D11（跨世界主角强制 `main`），改动落在 `source_workflows.py:595` 提取路径，使导入的多部原著不串实体。② **生成读取(refactor 2) 负责**消费——B 期 `merge_worldline_baseline` 注入 + D13 章节 `worldline_id` 元数据，改动落在 `context_assembly.py` 读取路径与 `common.py:771` 生成提取路径（该路径取 `creative_profile.worldline_id`，D13 改为取章节级 worldline）。=> 若只做 refactor 1，结果是「多部原著各自成世界、存储不串」；但生成**自动按章节世界注入**要等 refactor 2 接入。本规划在 refactor 1 内实现 `merge_worldline_baseline` 纯函数本体，接入生成读取路径标注为 refactor 2 的下游依赖。

> **「共享原著库 + 每故事 fork（写时复制）」澄清（更新自修订 9 误读）**：用户最终澄清——其「复制知识库」指**层级模型**：存在一个（项目级、未来可跨项目）的**共享原著库（canon）**，每个故事 = 从该库 **fork 一份副本**（复制一个或多个原著的知识），在副本上随意增改、**不影响原库**。这**不是**运行期 worldline 分支（修订 9 误读，特此更正）。实现完全落在既有 `setting_scope` 维度（F15）：
> - **原著库 = project 作用域**：导入原著 canon 条目 `setting_scope="project"` + **`story_id=None`（NULL，非 `""`，见 D14 外键修正）** + `version_scope="canon"`（**D14**，修 F16 卡 story 的缺口）。
> - **故事 fork = story 作用域的 COW 副本**：绑定原著时复制 `project`→`story`（带 `forked_from_library_id` 溯源，**D15**）；story 上增改落 `story` 作用域、`version_scope="project_main"`，隔离域保证与 `project` 库物理隔离、互不影响。
> - **COW 保证**：不同 `setting_scope`/`story_id` ⇒ 不同 `entity_id` ⇒ 不同行（F15），库与 fork 永不碰撞；改副本零成本不影响原库。
> - 与 worldline（D10）正交：库内多原著仍各占独立 `worldline_id`；fork 时可选择性复制某些 worldline（某些原著）。
> **重构归属**：① **D14（原著库作用域）属 refactor 1（资料提取）**——提取产出 canon 时必须决定落在 project 库而非 story；② **D15 的 fork 复制操作属下游独立能力**（refactor 2「库绑定」功能），非 refactor 1 提取工作；③ COW 隔离由隔离域自动保证，只要 D14 把库放对作用域、D15 复制进 story 作用域即成立。=> **当前资料提取规划不支持该模型**（F16 卡 story），需补 D14（库作用域，refactor 1 内）+ 独立的 fork 操作（下游）。
>
> **三层模型最终厘清（用户三轮澄清后）**：① **原著 vs 当前**：`version_scope=canon`（原库，永不改）vs `project_main`（当前工作版，可增改），读取期叠加 = 方案 (iii)；② **多部原著互隔离**：每部独立 `worldline_id`（D10）+ `canon_status`，同名角色不撞；③ **共享原著库 + 每故事 fork**：原著库置于 `setting_scope="project"`（D14），故事 COW 复制到 `setting_scope="story"`（D15），副本增改不影响原库。①②③ 正交叠加，共同构成「无限流分支管理」的完整骨架。

## 4. 分期执行步骤

每期含「改动点 + 验收」。文件改动总清单见各期末尾。

### A 期 · 字段级结构化引导（最高 ROI，先做）
**目标**：每条资料按 `KNOWLEDGE_TYPE_FIELDS` 规范产出；长资料不漏填。

改动：
- `domain/knowledge_types.py`：新增 `build_category_field_specs(categories)` → 逐类字段规格片段（注入 prompt）。
- `core/prompts.py`：`extract_reference_knowledge_prompt` 注入字段规格；长资料按 mode 分组并行子抽取（参考 `EXTRACTION_MODE_INSTRUCTIONS` `:1556`）。
- `core/schemas.py`：`ExtractedKnowledgeItem`（`:335`）加 `setting_field`/`fact_key` 字段（按 D4 由构造器填，不由 LLM）。

验收：`tools/verify_material_extraction_fields.py` — 长资料各 mode 产出字段覆盖率达阈值；短资料单调用不退化。

### A' 期 · 资料类型 → 提取预设（扩展现有 preset）
**目标**：原著出时间线、图鉴出独立条目，而非全用 `balanced`；并把世界线归属带入提取。

改动：
- `domain/extraction_presets.py`：新增 `MaterialType` 枚举 + `MATERIAL_TYPE_PRESET_MAP`。**映射到「计划预设」（多 pass）而非单个专家预设**：原著 → `world_timeline`（world→timeline→canon_auditor）或 `strict_canon_audit`（现成计划预设，F6）；图鉴 → 新增 `character_world` 计划预设（character_expert→world_expert）；可选 `fanfic_foundation` 串全流程。
- `creative_attachments.py:254`：由写死 `balanced` 改为查 `MATERIAL_TYPE_PRESET_MAP`；task `configuration` 加 `material_type`（D6）+ `worldline_id`（D10，由 source 派生、用户覆盖）。
- `workflows/ingestion_tasks.py:434`：`enabled_categories` 按 `material_type` 映射的分类子集（`configuration.get("enabled_categories")`；`:125` 另有 `automatic_settings.get("extraction_categories")`）。
- `source_workflows.py` 长资料批次 + `extract_reference_*`：接 preset 路由；**每条提取条目默认继承批次 `worldline_id`**（修 F10 碰撞：不再默认落 "main"），并据 D11 的「跨世界角色清单」把清单内角色强制 `worldline_id="main"`（经 `custom_instructions` 注入提取 prompt）。
- 提取 prompt（A 期）增加 worldline 指导：原生角色用作品世界线、清单内跨世界角色用 main、不要求模型自造 worldline_id。

验收：`tools/verify_material_preset_routing.py` — 原著样本 `timeline_events` 为主、图鉴样本无 timeline 且为独立条目；**导入"原著A""原著B"同名角色落到不同 `worldline_id`、实体不撞（F10 修复）**；错误识别可手动覆盖。

### B 期 · 原著基线 + 同人叠加（读取期合并，D1 / D12；merge 函数本体属 refactor 1，接入生成读取路径属 refactor 2）
**目标**：同人生成时自动沿用原著、可被覆盖；支持多独立世界线注入；不碰存储引擎。

改动：
- **【D13·章节→世界线关联·零迁移实现】**（已修正，原"给 chapters 表加列"不成立，F19）：
  - **不新增迁移**：在 `arc_{no}.meta.json` 增 `worldline_id` 字段，经既有 `save_arc_metadata`/`load_arc_metadata`（`content.py:456/457`）读写；规划工作台 UI 给 arc 一个世界选择，默认空=沿用 main。
  - 章节的世界线经「该章节所属 arc」解析（`_arc_meta_path` `content.py:143`）；无 arc 归属时回退 `creative_profile.worldline_id`。
  - 章节生成提取侧（`common.py:771-787`）：章节产出的事实 `worldline_id` 取「该章节/arc 的 worldline_id」（非一律 main），使同人在某世界写出的事实归到该世界线、与导入的原著世界线对齐。
  - **读取期章节 worldline 来源**：`context_assembly.py:429` 当前从 `creative_profile.worldline_id` 取；改为优先取「当前章节所属 arc 的 `worldline_id`」（D13），profile 仅作兜底。
- 新增合并函数 `merge_worldline_baseline(conn, story_id, worldline_id, worldline_mode)`（落在 `workflows/context_assembly.py` 或 `storage/repositories/knowledge_center.py`）：
  - 入参：当前章节 `worldline_id`（来自**章节/arc 的 worldline_id，D13**）+ `worldline_mode`（默认 `prefer`，F11）。
  - **跨 `setting_scope` 与 `version_scope` 双维度查同名实体**（索引 017:30 为 `(entity_type, canonical_name, story_id, worldline_id, setting_scope, version_scope)`，**两维都在键里**）：基线 `project`+`canon`（D14 库），当前副本 `story`+`project_main`（D15 fork）。=> 合并查询必须同时放开这两个维度，只跨 `version_scope` 会漏掉 D14/D15 引入的库/副本分层（原设计遗漏）。
  - 叠加规则（优先级：`au` > `project_main` > `canon`，同优先级内后写覆盖）：
    - replace 槽位（`location`/`status`/`holder`/`owners`/`owner`/`current_goal`，F25）→ 取优先级最高者，`canon` 仅作回退；
    - append 槽位（`users`/`abilities`/`appearance`/`personality`，F25）→ 各层 union（注：`holding` 在 `DYNAMIC_SLOT_KEYS` 中但 `FACT_MERGE_POLICY` 未定义 → 兜底 append）；
    - `timeline_events` → 按新增的 **`sequence_order`** 列排序（D8 已修正，原写 `source_segment_index` 但该键非表列，F18），canon 为原时间线、同人/au 另加。
  - 输出合并后的注入条目；`version_scope`/`setting_scope`/`source_type`/`worldline_id` 保留以区分来源。
- 章节装配时注入**多个 worldline**：固定注入 `worldline_id="main"`（主角跨世界事实，D11），并对当前章节 `worldline_id` 调用 `merge_worldline_baseline`（D12）；`worldline_mode="prefer"` 在缺失时回退 main（F11）。
- `context_assembly.retrieve_context`：装配生成上下文时调用上述合并。**开关挂点修正**：`allow_canon_deviation` 定义在 `schemas.py:280`（CreativeProfile 字段），`context_assembly.py:137` **只是把它渲染进提示词字符串**（`f"- 允许改写原设：{profile.get('allow_canon_deviation', True)}"`），**不是可 hook 的控制点** => gating 须在 `retrieve_context` 内显式读 `profile.get("allow_canon_deviation", True)` 后再决定是否调用合并。
- `knowledge_center.py` 透出的 `version_scope`/`worldline_id` 保持不变（canon/世界线信号保留，F8/F9）。
- **补写 `world_t`/`world_time_label`（修 F17）**：`entities.world_t` 列已存在且 `_upsert_entity_master`（`knowledge.py:841`）已接受该参数，但确认链路从未写入 => B 期对 `entity_type="event"`（即 `timeline_events` 类）实体，由 `sequence_order`/`source_segment_index` 推导并落 `world_t` + `world_time_label`，使时间线可按 `world_t` 原生排序（索引 `idx_entities_world_t` 017:33 已建）。
- **附带修复关系层隔离（修 F20）**：`_resolve_entity_id`（`knowledge.py:921`）增加 `version_scope` 参数并纳入 domain（现 939/955/964 三处硬编码 `'project_main'`），调用点 `1133`/`1137`/`1234` 传入实际 version_scope => 否则原著关系边会挂到 project_main 实体、与二创关系撞节点。

验收：`tools/verify_material_canon_overlay.py` — 同人未覆盖处返回 canon 事实；同人已覆盖处返回同人且 canon 保留可查；**导入多部独立原著时，生成某世界章节只注入该世界线+main，不串入其它世界线**；回退/来源区分正确（`source_type`/`worldline_id`）。

### C 期 · 二次召回校验（D3）
**目标**：查遗漏的重要实体/事件/关系/约束。

改动：
- `core/prompts.py` 新增召回校验 prompt；`common.py` 在 A+A' 后调用，仅长资料默认开（D3）。
- 对照 `KNOWLEDGE_TYPE_FIELDS.required` 做必填校验。

验收：`tools/verify_material_recall.py` — 抽样资料遗漏率下降；token 成本在长资料阈值内。

### D 期 · 提取 schema 硬化
**目标**：从源头拒低质量条目。

改动：
- `core/schemas.py`：`ExtractedKnowledgeItem` 设 `setting_field` 必填（**取值规则按 D4：实体×槽位拆分的条目才有，非实体类不设**，否则 queue 会误拒）；`validate_typed_knowledge_item`（`knowledge_types.py:159`）拒缺字段。
- `consolidate_extracted_knowledge`（`common.py:1258`）改无损合并：**`compact_items` 白名单补回 `typed_data`/`source_segment_ids`/`source_segment_titles`/`merged_from_pending_ids`/`schema_version`/`extraction_mode`，并同步加入 A 期新增的 `setting_field`/`fact_key`/`aliases`/`order_hint`**（F26）；**同时改 `consolidate_extracted_knowledge_prompt`（`prompts.py:1694`）要求输出回填这些字段**（F30，否则 LLM 往返的输出段仍会丢）。
- `queue_pending_knowledge_items` 在 `normalize_typed_knowledge_item` 后拒无 `setting_field` 条目（开发期告警）。
- **顺带修复写入 bug**：`_apply_supersession`（`knowledge.py:347-359`）的 UPDATE 仅设 `valid_to_chapter`，漏 `superseded_by = ?`；补上以精确标记「被哪条事实覆盖」（用于同 continuity 章号取代的回退 UI，非 canon 机制）。

验收：`tools/verify_material_extraction_schema.py` — 缺字段被拒；consolidate 前后 `typed_data` 字段集不变；回归 `verify_entity_fact_relation` 不回退。

### 4.6 分块与 Prompt 增强（修订 14 新增）

规划前五期解决的是「抽得全不全、存得对不对」；本节解决「**同一份资料能不能抽得更准更一致**」。分块与 prompt 是效果落地的最后一公里，设计再好若这两处不动，收益会打折。

#### 分块侧

| # | 增强项 | 现状 / 问题 | 做法 | 归属 |
|---|---|---|---|---|
| P1 | **批次内实体词表接力**（收益最大） | `alias_context` 只读**已确认**落库的别名（F23）→ 新导入原著时前 N 段为空，每段孤立抽取，同一角色在段 1/段 30 可能叫不同名字，抽取期无法归一 | 长资料批次内维护**运行期实体词表**：每处理完一段，把该段抽出的 `(name, aliases, category)` 并入词表，注入下一段的 `alias_context`。即把其构造从「读库」扩展为「读库 + 批次内累积」 | A' 期 |
| P2 | **片段重叠 / 上文衔接** | `split_text_by_boundaries` 支持 `overlap_chars`，但 `split_reference_text` 未传 → 零重叠；`previous_index`/`next_index` 已算但**全仓无消费点**（F23）→ 跨边界的实体/事件被截断 | 二选一：(a) 传 `overlap_chars`（200-400 字）；(b) 更省 token——把上一段**尾部 200-300 字**作为「上文衔接」注入 prompt，并注明仅供理解、不据此产出条目 | A 期 |
| P3 | **分层合并（consolidate）** | `consolidate_extracted_knowledge_prompt` 对整批条目**一次调用**合并；长篇数百条一次性喂入，易丢信息/超预算 | 改为**滚动/分层合并**：按 `chapter_index` 先分组各自合并，再对合并结果做一轮汇总 | C 期 |

#### Prompt 侧

| # | 增强项 | 现状 / 问题 | 做法 | 归属 |
|---|---|---|---|---|
| P4 | **删除 prompt 中的 `constraints`**（**必做，与 D5 矛盾**） | `prompts.py:1645` 分类说明与 `:1656` 输出枚举仍列 `constraints`（F22），模型仍被要求产出已取消的分类 | 与 D5 同步：prompt 两处一并删除；否则只改 schema Literal 而模型照旧输出，会在归一化处产生无字段孤儿 | A 期 |
| P5 | **关系条目给结构化键名** | prompt 只描述「包含亲密、冲突、权力…」，未给键名；而 `_relationship_fields`（`knowledge.py:974-982`）按 `source`/`from`/`subject`/`character_a` 与 `target`/`to`/`object`/`character_b` 解析 → 模型自由发挥时两端解析易落空 | prompt 对 `relationships` 明确要求 `character_a`/`character_b`/`relation_type`/`stage` 等键，与 `_relationship_fields` 对齐 | A 期 |
| P6 | **时间线段内顺序 hint** | D8 用 `source_segment_index` 排序，但**同一段内多个事件**的先后顺序会丢失 | prompt 要求 `timeline_events` 按发生顺序输出并可带 `order_hint`（段内序号）；最终 `sequence_order = segment_index × K + order_hint` | A 期（配合 D8） |
| P7 | **别名结构化输出** | 现行规则 10 只说「在 details 或 tags 中保留别名线索」，含糊 → 词表接力（P1）与 `entity_alias_groups` 拿不到规范别名 | `ExtractedKnowledgeItem` 增 `aliases: list[str]`，prompt 明确要求填写 | A 期（P1 的前置） |
| P8 | **少样本示例 / 反例** | 当前 prompt 零 few-shot；`details` 是自由字典，格式漂移风险高 | 给 1-2 个分类（尤其 `characters`、`timeline_events`）的正例，以及「把普通叙述拆成低价值条目」的反例 | A 期 |
| P9 | **confidence / importance 校准锚点** | 三值已要求但无锚点，模型普遍打 0.7 附近，失去区分度 | prompt 补锚点描述（如 importance ≥0.8 = 贯穿全书的核心设定；≈0.3 = 一次性场景细节） | A 期 |

> 说明：P4 属**必做**（否则与锁定决策 D5 自相矛盾）；P1/P5/P6/P7 直接支撑既有决策（D8 排序、P1 别名归一、关系边解析），建议在 A+A' 期一并完成；P2/P3/P8/P9 属质量增强，可随 A 期顺带做或留作调优。

### 4.7 改动分层：共享层 vs 路径专属（同步改 vs 分别改）

用户问「章节提取与资料提取能否同步修改」。结论：**分两层——下游共享层天然同步，上游路径专属只能对齐着改**（F28）。这是本次重构的实施边界，避免「改共享层却只测资料路径」或「误以为改一处两条路径都变了」。

#### A. 共享层（改一次全路径受益，须全路径回归）

这些改动落在 `queue_pending_knowledge_items`（`knowledge.py:337`）→ `consolidate` → `normalize` → `confirm` → `sync_knowledge_category` 共享链路上，**不区分章节/资料，自动同步生效**：

| 改动 | 位置 | 关联 |
|---|---|---|
| consolidate 白名单补字段（无损） | `common.py:1258` 的 `compact_items` | F26、D 期 |
| `_apply_supersession` 补 `superseded_by` | `knowledge.py:347-359` | D 期 |
| `_resolve_entity_id` 纳入 `version_scope` | `knowledge.py:921/939/955/964` | F20、B 期 |
| `normalize_typed_knowledge_item` 透传新字段 | `knowledge_types.py:136` | 已透传，仅需确认新键不被白名单丢 |

> 回归守护：共享层改动后必须跑全路径回归——`verify_chapter_extraction_injection_policy.py`（章节路径）、`verify_db_storage.py`/`verify_entity_fact_relation.py`（存储）、以及新增的资料路径 `verify_material_*.py`。不能只测资料路径。

#### B. 路径专属（两份代码，分别写、对齐着写）

| 环节 | 章节路径（已存在，refactor 2 域） | 资料路径（本重构新增） | 关系 |
|---|---|---|---|
| 构造器 | `build_pending_knowledge_from_setting_extraction`（`common.py:793`） | **新增** `build_pending_knowledge_from_reference_extraction` | 结构对称、三处取值不同（F27），是「照着写」不是「改同一函数」 |
| 提取 prompt | 章节 setting 提取 prompt（refactor 2 域） | `extract_reference_knowledge_prompt`（`prompts.py:1595`） | 两份不同 prompt；P5-P9 多为资料专属，**P4 删 `constraints` 若章节 prompt 也列了则需两处同步** |

> 若本轮不动章节生成（refactor 2），只须保证共享层改动不破坏章节路径即可；章节 prompt 的 P4/P5/P8 增强留待 refactor 2 或按需顺手同步。

### 4.8 输出/存储/提示词契约落点补全（修订 21 · 第 5 轮审查）

本轮聚焦「分块 → 提示词 → 输出存储 → 与正文提取共享」四环节，发现 17 处疏漏。根因：**部分决策只定义了「字段是什么」，没定义「字段怎么产生、怎么落库」**，导致新增字段可能形同虚设。两个 critical（setting_field 语义、sequence_order 写入链）已直接修进 D4/D8，其余整理如下。

#### A. 存储链落点（输出 → 落库）

| # | 疏漏 | 补全 |
|---|---|---|
| 1 | **`aliases` 无存储列、不进 `entity_alias_groups`**（P7 落空） | `aliases` 作顶层字段入 content_json；确认时由 `_upsert_entity_master` 同步写入 `entity_alias_groups`（供 P1/F23 归一化消费）。至少明确「alias 归一化从 content_json 读」 |
| 2 | **`worldline_id` 默认 `"main"` 掩盖碰撞**（`queue:366`/`_append:481` 兜底） | 构造器**必设** `worldline_id`（D10）；D 期加「资料条目缺 worldline_id → 告警/拒收」，防止漏设重演 F10 同名撞车 |
| 3 | **资料路径无法产生 `version_scope="au"`**（`queue:365` 仅 canon/project_main；au 由章节路径 `_resolve_pending_knowledge_version_context:759` 产生） | 澄清（F29 补充）：**资料导入 version_scope ∈ {canon, project_main}，au 仅章节生成产生**——原著=canon、图鉴/参考=project_main；B 期合并里 au 只来自章节路径，非资料路径职责 |
| 4 | **consolidate → enrich 字段存活未定义** | F26/F30 只补了 `compact_items` 白名单 + prompt 回填；须补 **enrich 环节透传** `setting_field`/`fact_key`/`aliases`/`order_hint`（`enrich_consolidated_knowledge_items`） |
| 5 | **`_resolve_entity_id` 的 `version_scope` 下钻来源未指定**（边写入函数无该值） | B 期修复时明确：从 item 的 `version_scope` 传入 `_resolve_entity_id`（调用点 `1133`/`1137`/`1234` 所在函数须先取 item.version_scope） |

#### B. 提示词/分块契约

| # | 疏漏 | 补全 |
|---|---|---|
| 6 | **prompt 输出模板无 `worldline_id` 字段**（`prompts.py:1650-1677`）→ D10/D11 落空 | prompt 加 `worldline_id` 字段；enrich 读 `batch.get("worldline_id")`（当前只 `item.get` + DEFAULT 兜底，D16 派生缺注入点） |
| 7 | **关系键名无输出模板支撑**（模板只有 name/summary/details） | `ExtractedKnowledgeItem` 增 `character_a`/`character_b`/`relation_type` 等键 + prompt 模板对应（P5 落地） |
| 8 | **`aliases`/`order_hint` 在输出与 consolidate 模板均缺**（F30 只提 setting_field/fact_key） | F30 扩为：consolidate prompt 回填 `setting_field`/`fact_key`/`aliases`/`order_hint`/`relationships 键` |
| 9 | **P1 词表接力无接线**（`extract_reference_knowledge:1203` 无 alias_context 入参、调用点不回灌） | `extract_reference_knowledge` 加 `alias_context` 入参；调用点把上段抽出的 `(name, aliases)` 回灌（当前写死 `_format_entity_alias_context`） |
| 10 | **P2(a) overlap 污染偏移**（重叠尾部拼进下一段 → `text.find` 命中更早位置 → offset/证据锚点错位） | 剥离重叠再算 offset，或改用 P2(b) 无重叠 + 上文注入 |
| 11 | **多 pass 断点续跑粒度不足**（`target_indices` 一次算好、靠 extract_status 跳过 → D2 多 pass 第 2 步后整计划重跑被全跳过） | 改 `(segment, mode)` 粒度续跑状态 |
| 12 | **A 期结构化引导 vs 自由 `details` 字典矛盾**（prompt 现填 `{字段名:字段内容}`，A 期要按 KNOWLEDGE_TYPE_FIELDS 规范产出） | 明确：关键字段走结构化键（槽位/别名/关系键/顺序），其余仍留 `details` 字典承载；或改输出 schema 为强类型 |
| 13 | **段级 `content_kind` 未用于选 mode**（`reference_chunking.py:245`，D6 只到整批 preset） | 可选优化：段级类型驱动该段的 mode，充分利用已有段级类型信号 |

## 5. 实施顺序

**第 0 步：共享层修复先行** ✅ **（修订 23 已完成）**（§4.7-A 的四项：consolidate 白名单补字段 / `_apply_supersession` 补 `superseded_by` / `_resolve_entity_id` 纳入 version_scope / 确认新字段透传）——全路径受益、风险最低、是后续一切的地基，须全路径回归（§4.7-A 的守护清单）。

**A + A' 同批**（叶子层：不碰 `context_assembly` 预算/排序雷区、不碰存储引擎）→ **B**（读取合并，依赖 A' 正确归类）→ **C**（长资料召回，依赖 A+A' 质量基线）→ **D**（schema 硬化，与 A 同步或紧随）。

文件改动总清单：
- `core/prompts.py`：字段规格注入（A）+ 并行子抽取 prompt + 召回校验 prompt（C）+ **§4.6 的 P4 删除 constraints / P5 关系键名 / P6 顺序 hint / P7 别名 / P8 少样本 / P9 评分锚点** + **§4.8 的 worldline_id 输出契约 / consolidate 回填 aliases·order_hint·关系键（F30 扩）**
- `domain/reference_chunking.py`：**P2 传 `overlap_chars`**；`split_reference_text` 补段内顺序信息供 P6 使用
- `domain/knowledge_types.py`：新增 `build_category_field_specs`
- `domain/extraction_presets.py`：新增 `MaterialType` + `MATERIAL_TYPE_PRESET_MAP`（映射到计划预设：原著 → `world_timeline`/`strict_canon_audit`，图鉴 → 新增 `character_world`；见 A' 期）
- `workflows/skills/common.py`：新增 `build_pending_knowledge_from_reference_extraction`（**结构对称于 `:793`，三处取值不同：`setting_scope="project"`/`version_scope="canon"`/无 `source_chapter_no`，见 F27**；`injection_policy="retrieval"`）；`extract_reference_knowledge` 接构造器；`consolidate_extracted_knowledge` 无损
- `core/schemas.py`：`ExtractedKnowledgeItem` 加 `setting_field`/`fact_key` + `aliases`/`order_hint`/关系键（`character_a`/`character_b`/`relation_type`）+ 必填校验；**并从 `category` Literal 移除 `"constraints"`**（D5，修 F21；字段落点见 §4.8）
- `workflows/source_workflows.py` + `creative_attachments.py`：preset 路由；`creative_attachments.py:254` 由 balanced 改查 map；task `configuration` 加 `material_type` + `worldline_id`（D10 派生/覆盖）；提取条目默认继承批次 `worldline_id`、跨世界角色清单强制 main（D11，修 F10）；**导入原著 canon 条目不注入 `story_id`（改打 `setting_scope="project"`，D14 库作用域，修 F16 卡 story 的缺口）**
- **【下游，非 refactor 1 提取内】fork 操作**：新增 `fork_library_to_story(project_name, story_id, source_ids)`（参照 `copy_story`（`stories.py:1606`）/`copy_story_settings`（`:945`）的既有复制实现思路——**不存在 `clone_story_storage_rows`，原引用有误**）→ 把 `project` 作用域的 canon 条目 COW 复制到 `story` 作用域（`setting_scope="story"`, `story_id=X`, 带 `forked_from_library_id` 溯源，**重算 `entity_id`**，D15），属 refactor 2「库绑定」功能
- `workflows/context_assembly.py`（或 `storage/repositories/knowledge_center.py`）：新增 `merge_worldline_baseline` 并在 `retrieve_context` 调用；`worldline_id` 来源由 `creative_profile` 改为优先「当前章节 worldline_id」（D13）
- `storage/migrations/`：新增 **018 迁移，仅给 `knowledge_items` + `pending_knowledge_items` 加 `sequence_order INTEGER` 列**（D8 时间线排序键，整轮重构**唯一**的 schema 新增）。**原计划的「chapters 表 worldline_id 迁移」已取消**——不存在该表（F19），D13 改走 arc 元数据 JSON，**零迁移**；规划工作台 UI 给 arc 选世界
- `services/memory/content.py`：`arc_{no}.meta.json` 增 `worldline_id` 字段（D13，经 `save_arc_metadata`/`load_arc_metadata`）
- `storage/repositories/knowledge.py`：修复 `_apply_supersession` 漏 `superseded_by`；**修复 `_resolve_entity_id` 硬编码 `version_scope='project_main'`**（F20，加参数并纳入 domain，下钻来源见 §4.8-A5）；补写事件实体 `world_t`/`world_time_label`（F17 修正）；**`sync_knowledge_category` 的 INSERT 写 `sequence_order`（D8）+ `aliases` 同步进 `entity_alias_groups`（P7）**
- 新增 `tools/verify_material_*.py` 共 4 个回归脚本

## 6. 被否决方案（仅作追溯，不再平行评估）

- **(i) 强行兼容**：把导入原著 `version_scope` 标 `project_main` + `valid_from_chapter=0` 哨兵，复用现有章号取代。能跑但推翻 F5 的 canon 默认、丢 F8 的 `version_scope` 读取信号、哨兵复用列语义 → **否决**。
- **(ii) 共享实体**：移出 `version_scope` 让同名跨 canon/fic 共享 `entity_id`。最「一个角色贯穿两界」但需改 `entities` 唯一索引+回填+改 `entity_query`/`knowledge_center` → 成本高风险大 → **否决**。

## 7. 完成定义（Definition of Done）

重构完成当且仅当：
1. **A+A'**：长/短资料按资料类型产出规范条目，字段覆盖率达验收阈值，preset 路由正确（原著出时间线、图鉴出独立条目）。
2. **B**：同人生成上下文自动叠加 canon 基线，覆盖/回退行为正确，`version_scope` 信号保留。（**注（修订 18）**：此验收依赖 `context_assembly.retrieve_context` 接线，属 refactor 2；refactor 1 内仅验收 `merge_worldline_baseline` 纯函数本体的合并正确性，用单元级样本验证，不要求端到端生成）
3. **C**：长资料二次召回开启且遗漏率达标。
4. **D**：缺字段条目在源头被拒（`setting_field` 取值规则明确，D4），consolidate 无损（白名单 F26 + prompt 回填 F30），enrich 透传新字段，`_apply_supersession` 补 `superseded_by`。
5. 回归 `verify_db_storage` / `verify_entity_fact_relation` / `verify_p1b_dynamic_slots` 全部 PASS，无回退。
6. **多独立原著隔离**：导入 N 部独立原著，同名角色因 `worldline_id` 不同而实体不撞（F10/D10 修复）；生成某世界章节仅注入该世界线 + main 世界线（D10/D11/D12），且章节 `worldline_id` 从章节/arc 元数据读取（D13），不串入其它世界线。
7. **共享原著库 + 每故事 fork**：导入原著 canon 落 `setting_scope="project"` 共享作用域（D14，修 F16），不卡在单一故事；故事可从此库 fork COW 副本（D15），fork 上增改 `setting_scope="story"` 不影响原库（COW 隔离，F15）；多故事复用同一原著库不重复、不串；库内多原著仍各占独立 `worldline_id`（D10），fork 可选择性复制某些原著。
8. **fork 副本真隔离**：fork 时 `entity_id` 已按 story 作用域**重算**（D15 修正），副本与库不共享 entity_id；改副本不触发对库条目的取代（`_apply_supersession` 按 `(entity_id, fact_key)` 匹配，entity_id 不同则不命中）。
9. **关系层 canon 隔离**：`_resolve_entity_id` 已纳入 `version_scope`（F20 修复），原著关系边不再挂到 `project_main` 实体，与二创关系不撞节点。
10. **`constraints` 已移除**：`ExtractedKnowledgeItem.category` Literal 仅剩 11 类（F21/D5），模型不可能产出无字段规格的孤儿条目。
11. **时间线可排序**：事件实体落 `world_t`/`world_time_label`（构造器填，F17 修正）；资料时间线按 `sequence_order` 列原生排序（D8 写入链，非 NULL）。
12. **字段落点完整**（§4.8）：`sequence_order` 由 sync INSERT 写入（D8）；`aliases` 落 content_json 并同步进 `entity_alias_groups`（P7）；`worldline_id` 不再依赖 queue 默认 main（构造器必设，D10）；资料条目 `version_scope` ∈ {canon, project_main}（无 au，F29 澄清）。
13. **提示词契约**（§4.8）：prompt 输出含 `worldline_id`/关系键/`aliases`/`order_hint`，consolidate prompt 回填同批字段。

## 8. 变更记录（活文档）

- 2026-09-04 初稿：A/B/C/D 四期，G1/G2/G3，文件清单。
- 2026-09-04 修订1：补两类条目同层同结构认识（资料进 entities 但不触发取代）。
- 2026-09-04 修订2：补资料类型→预设/顺序轴，重组 A/A'/B/C/D 五期。
- 2026-09-04 修订3：原著取代设计（确认可取代），初推方案(i)。
- 2026-09-04 修订4：存储结构无需同步重构（017 已 canon/fic 感知）。
- 2026-09-04 修订5：方案(i) 属强行兼容非真设计；给出方案(iii) 读取期叠加。
- 2026-09-04 锁定：用户选定 (iii)；要求文档转为「可直接执行至完成」的单路径规格。据此重写——D1-D9 决策锁定（§3）、§4 分期含验收、§6 仅留被否方案追溯、§7 完成定义。
- 2026-09-04 修订6（无限流多独立原著）：用户指出规划仅隐含单一 canon 基线，问「能否存多部独立原著」。核实 `worldline_id` 是一等隔离维度（F9），但资料导入不分配 worldline_id 导致碰撞（F10），且读取侧已世界线感知（F11）。新增锁定决策 D10（每独立原著=独立 worldline_id）、D11（跨世界主角强制 main、逐实体分类）、D12（多世界线读取注入，复用 worldline_mode=prefer）；B 期合并函数改名 `merge_worldline_baseline` 改为按 worldline 作用域+多 worldline 注入；A' 期补 worldline 归属带入；D7 明确「互替仅限同 worldline 内」；§7 完成定义补第 6 条多独立原著隔离。规划现支持无限流多世界场景，仍零存储重构。
- 2026-09-04 修订7（多世界适配复杂度核实）：用户问「多独立世界适配复杂吗」。核实关键缺口——生成时 `worldline_id` 仅项目/档案级（`context_assembly.py:428-430` 取自 `load_creative_profile`），**章节本身无 worldline 关联（F12）**。结论：存储/导入/读取基础设施已就绪，真正唯一新概念是「章节→世界线关联」。锁定 D13=arc/卷级（给章节/大纲组加 `worldline_id` 列 + 规划 arc 时选世界 + 生成路径改读章节级 worldline，新增 018 迁移）；零迁移降级方案（仅手动切 `creative_profile.worldline_id`）列为 scope 收窄备选。复杂度定调：非深度重写，唯一新增 schema 是 1 列 + 1 迁移 + UI。
- 2026-09-04 修订8（「复制资料/fork 源文档」澄清）：用户提出「拆成原著资料+当前资料两部分，不同原著隔离、原著vs当前隔离，当前复制一份更保险」。核实——源文档与抽取条目已分层（`source_documents`/`source_segments` 存原文，`knowledge_items` 指向且不回写，F13）→ 原文天生不可变；全仓无「复制源资料」功能（F14，用户印象的复制应为 `copy_story`/重抽取 diff）。结论：用户直觉正确，但**不应做物理源文档复制**，因为方案 (iii) 已在事实级实现「原始(canon)不动 + 当前(project_main)可改 + 读取合并」，且多溯源/可回退/不复制三项优势；多原著隔离=D10(worldline_id)+canon_status，原著vs当前隔离=version_scope=canon vs project_main。=> 本重构不引入源文档 fork，「当前新版」= project_main 条目集，UI 直接编辑即可；新增 §3 第二项 clarifying 说明。
- 2026-09-04 修订9（纠正：用户指「知识库复制」非「源文档复制」）：用户纠正修订8误判——其「复制」指**知识库复制、运行期分支**。核实系统已有章节级分支先例 + `worldline_id` 任意值支持 → 误读为「运行期 worldline fork」。详见修订 10 更正。
- 2026-09-04 修订10（**最终澄清：共享原著库 + 每故事 fork，非 mid-generation worldline 分支**）：用户第三度澄清——其模型是**层级模型**：项目级（未来可跨项目）的**共享原著库(canon)** + 每个故事 **fork 一份 COW 副本**（复制一个或多个原著知识），副本增改不影响原库。修订 9 的「运行期 worldline 分支」系误读，特此更正。核实：`knowledge_items` 已含 `setting_scope`/`story_id`/`worldline_id`/`canon_status`（001:127-153），`isolation_domain`（entity_identity.py:57）=`(setting_scope,story_id,worldline_id,version_scope)` 且非 story 作用域清空 `story_id`（:64-65）→ 既有 `setting_scope` 维度**零 schema 改动**即可建模「project 库 + story fork」（F15）；但当前导入 `source_workflows.py:591` 给条目赋 `story_id` → 默认 `setting_scope="story"` → canon 卡死单一故事、多故事无法共享（F16，规划缺口）。新增 **D14**（原著库=project 共享作用域导入）、**D15**（fork=project→story COW 复制、带溯源、隔离域保证不影响原库）。三层模型最终厘清：① 原著vs当前(canon/project_main 叠加方案iii)；② 多原著隔离(worldline_id D10)；③ 共享库+story fork(setting_scope D14/D15)。重构归属：**D14 属 refactor 1（提取把 canon 放对作用域）**；**D15 fork 操作属下游独立能力**（refactor 2 库绑定），非 refactor 1 提取工作；COW 隔离由隔离域自动保证。=> 当前资料提取规划**不支持**该模型（F16 卡 story），需补 D14（refactor 1 内）+ 独立 fork 操作（下游）。新增 §2 F15/F16、§3 D14/D15、§5 文件清单补 D14+fork 标注、§7 完成定义第 7 条。
- 2026-09-04 修订11（**存储完备性对账 + D8 修正**）：用户追问「提取后存储是否完备（条目形式/时间线/隔离）」。逐列核实 `knowledge_items`(001:127-153)+017 加列、`entities`(017:7-27)、`pending`(001:155-178) 全量列，结论：隔离维度已完备、条目形式基本完备、**时间线不完备**。新增 F17（`world_t` 在确认链路从未写入，grep 零命中）、F18（`source_segment_index` 非 knowledge_items/pending 列 → 资料时间线无原生排序列）。**修正 D8**：原「按 source_segment_index 不加新列」错误（该键非列），改为「新增 `sequence_order INTEGER` 列 + 由 source_segment_index 映射填充」；新增 §2.5 完备性对账矩阵。
- 2026-09-04 修订12（**全面审查：修正 5 处错误 + 补 6 处遗漏**）：用户要求据现有代码全面审查规划。逐条核验规划引用的符号与决策前提，发现并修正——**错误**：①**D13 建立在不存在的数据表上**（全仓无 `CREATE TABLE chapters`；章节是文件 `content.py:1006`→`chapter_NNN.md`，而 arc 本就是带 `save_arc_metadata`/`load_arc_metadata` 的文件实体 `arc_NNN.meta.json`）→ 改为写 arc 元数据 JSON，**取消 018 章节迁移、零 DB 迁移**（F19）；②**D14 `story_id=""` 会触发外键失败**（`db.py:95 PRAGMA foreign_keys=ON` + 001:150 FK；代码约定 `story_id or None` knowledge.py:969）→ 改 NULL；③**D15「COW 隔离自动保证」不成立**（`entity_id_for` 哈希已固化在每行 entity_id 列，逐行复制会共享 entity_id → `_apply_supersession` 按 (entity_id,fact_key) 跨库污染）→ 必须重算 entity_id；④**B 期 `allow_canon_deviation` 挂点错误**（`context_assembly.py:137` 只是把 flag 渲染进提示词字符串，非控制点；字段在 `schemas.py:280`）→ 改为在 `retrieve_context` 内显式读 profile；⑤**B 期时间线仍写 `source_segment_index`**（与修订 11 修正后的 D8 矛盾）→ 改 `sequence_order`。**新增事实** F19（章节/arc 文件存储）、F20（`_resolve_entity_id` 硬编码 project_main，关系层 canon 隔离失效）、F21（`ExtractedKnowledgeItem.category` Literal 仍含 constraints）。**补充遗漏**：D5 补「从 Literal 移除 constraints」；B 期合并查询补**跨 `setting_scope` 维度**（D14/D15 引入库/副本分层后只跨 version_scope 会漏，索引 017:30 两维都在键里）+ 补优先级 `au>project_main>canon`；补 `world_t`/`world_time_label` 写入动作与关系层 `_resolve_entity_id` 修复；新增 **D16**（worldline 由不可变 `source_id` 派生，不用标题/slug 以免改名致 entity_id 全量重算）、**D17**（跨世界角色清单落 `configuration.cross_world_characters` + `normalize_name` 归一化匹配）；§5 迁移收敛为**仅 018 `sequence_order`**；§2.5 矩阵补 fork 隔离与关系边两行；§7 补第 8/9 条验收。
- 2026-09-04 修订13：**D6 资料类型识别可直接复用现成 `infer_content_kind`**（`reference_chunking.py:179`，按 source_type/标题关键词返回 `timeline`/`character`/`relationship`/`world_rule`/`style`/`narrative`），无需新写类型识别；仅在 `MATERIAL_TYPE_PRESET_MAP` 前加一层 mode 映射（`world_rule`→`setting`、`narrative`→`general`）。
- 2026-09-04 修订14（**分块与 Prompt 增强**）：用户问「提取过程还有什么能完善，比如分块、prompt」。读实 `reference_chunking.py` 与 `prompts.py:1556-1691` 后发现两处硬缺口 + 七项增强。**硬缺口**：F22 **prompt 仍列 `constraints`**（`prompts.py:1645` 分类说明 + `:1656` 输出枚举），与 D5 直接矛盾，且修订 12 只改了 schema Literal（F21）未改 prompt → 模型仍被要求输出被取消的分类，**必做**；F23 **长资料跨片段无上下文接力**——`alias_context` = `_format_entity_alias_context`(`common.py:1184`) → `load_entity_aliases` 只读**已确认**的 `entity_alias_groups`，新导入原著时前 N 段为空导致每段孤立抽取（段 1「林越」与段 30「林公子」无法归一）；且 `previous_index`/`next_index`（`reference_chunking.py:253-254`）全仓无消费点、`overlap_chars` 未传 → 实际零重叠。**新增 §4.6**：分块侧 P1 批次内实体词表接力（收益最大）/P2 重叠或上文衔接/P3 分层合并；prompt 侧 P4 删 constraints（必做）/P5 关系结构化键名（对齐 `_relationship_fields` `knowledge.py:974-982`）/P6 段内顺序 hint（补 D8 同段多事件丢序）/P7 别名结构化（P1 前置）/P8 少样本/P9 评分锚点。§5 文件清单补 `domain/reference_chunking.py` 与 prompt 增强项。
- 2026-09-04 修订15（**第二轮全面审查：修正 4 处错误 + 补全槽位/机制细节**）：用户再次要求据现有代码全面审查，本轮聚焦前几轮未覆盖的区域（mode 词表、章节构造器、槽位策略、字段存活链、克隆函数）。核实并修正——**错误**：①**D2 mode 词表错误**：`EXTRACTION_MODE_INSTRUCTIONS`（`prompts.py:1556`）真实 9 键 = `general`/`deep`/`characters`/`relationships`/`timeline`/`world`/`style`/`strict_canon`/`fanfic_reference`，预设 mode 值与之完全一致；原「6 路（general/character/relationship/timeline/setting/style）」中 character/setting 系拼写错误（实为 characters/world）且漏 3 键；②**§5 引用 `clone_story_storage_rows` 不存在**：真实为 `copy_story`（`stories.py:1606`）/`copy_story_settings`（`:945`）/`_copy_story_files`（`:1383`）；③**F11 证据错置**：`load_knowledge_category_rows` 实际在 `storage/repositories/knowledge.py:568`，签名仅 `(conn, category)` **不接受 worldline_id**；世界线过滤真实存在于 `setting_knowledge._setting_worldline_allowed`（`:151`）与 `retrieval/search._worldline_allowed`（`:133`）两消费层；D12 表述改为「参照 prefer 语义、merge 自行做 worldline 作用域查询」；④**D4 引用 `SETTING_FIELD_SPECS` 方向错误**：它是「设定字段→分类」正向映射，反向不唯一（`world_rules` 4 候选）且多类别无对应；章节路径真实用三元组 `SETTING_EXTRACTION_KNOWLEDGE_FIELDS`（`common.py:702`，仅 4 条）+ `DYNAMIC_SLOT_KEYS`（`:714`）。D4 改为「构造器按 `DYNAMIC_SLOT_KEYS` 槽位推导 fact_key，无槽位类别 fact_key=None→append」。**确认/补全**：F2 字段存活链验证成立（queue `knowledge.py:337` → pending → confirm `:536` → `_append` `:419` → `sync_knowledge_category`，`setting_field` 能存活到列）；G2 位置更正（queue 定义在 `knowledge.py:337`）；新增 F24（三元组映射事实）/F25（`FACT_MERGE_POLICY` 真实键名 + `holding` 兜底 append + `_NO_SUPERSESSION_FACT_KEYS` 已预留 `order_hint`）；B 期槽位清单补 `owners`/`owner`/`users`；D14 补落地机制（确认路径不设 setting_scope、由 story_id 推导，须移除 `source_workflows.py:591` 注入的 "default"）；回归脚本 `verify_entity_fact_relation.py`/`verify_p1b_dynamic_slots.py` 存在性确认无误。
- 2026-09-04 修订16（**第三轮审查：验证行为断言 + 发现 consolidate 隐藏陷阱与「对称构造器」三处不同**）：本轮聚焦规划里仍属「待证实」的具体行为断言。**新发现（需修正）**：① **F26 consolidate 白名单陷阱**——`consolidate_extracted_knowledge` 的 `compact_items`（`common.py:1272-1288`）只保留 15 键，丢弃 `typed_data`/复数 `source_segment_ids`/`source_segment_titles`/`merged_from_pending_ids`/`schema_version`/`extraction_mode`；A 期新增的 `setting_field`/`fact_key`/`aliases`/`order_hint` 若不加入白名单会被静默丢弃 → D 期「无损」已补全键清单；② **F27 对称构造器三处不同**——章节构造器硬编码 `setting_scope="story"`+`injection_policy="retrieval"`+`source_chapter_no`，资料构造器须同三处取 `project`/`canon`/无章号；③ **A'期映射应指向「计划预设」**——原著有现成 `world_timeline`（world→timeline→canon_auditor）/`strict_canon_audit`，图鉴需新增 `character_world` 计划预设（原「两个专家预设」表述不贴合现有多-pass 机制）。**确认属实**：`_apply_supersession` 漏 `superseded_by`（`knowledge.py:347-359`，仅设 `valid_to_chapter`）；`creative_attachments.py:254` 写死 `KNOWLEDGE_EXTRACTION_EXPERT_PRESETS["balanced"]`；`ingestion_tasks.py:434` 属实（完整路径 `workflows/ingestion_tasks.py`）；`_chapter_no_from_item` 优先 `source_chapter_no`、回退 tags 的 `chapter:{n}`（资料两者皆无 → None → append-only）。
- 2026-09-04 修订17（**改动分层：共享层 vs 路径专属**）：用户问「章节提取与资料提取能否同步修改」。核实 `queue_pending_knowledge_items` 是 4+ 条路径（章节 `generation.py:827`、资料 `source_workflows.py:479/606/1434`、互动写作 `interactive_writing.py:1127`、网络研究 `web_research_tasks.py:773`）的共享下游（新增 **F28**）。新增 **§4.7**：A 类「共享层改动」（consolidate 白名单/`_apply_supersession`/`_resolve_entity_id`/normalize 透传，改一次全路径受益、须全路径回归）；B 类「路径专属改动」（资料构造器 + 资料 prompt，两份代码分别写、对齐着写，P4 若章节 prompt 也列 constraints 才需两处同步）。§5 实施顺序加「第 0 步：共享层修复先行」。顺带修正 §5 文件清单两处遗留不一致：`story_id=""`→不注入 story_id（对齐 D14 NULL 修正）、`canon_full`→`world_timeline`/`strict_canon_audit`/`character_world`（对齐 A'期）。
- 2026-09-04 修订18（**第四轮审查：新鲜子代理独立复查 + 纠正我方 F17 错误结论 + 补 3 处 critical 设计缺口**）：用户担心我受上下文惯性影响，遂派两个**独立子代理**（一查代码引用、一查设计完整性）并行复查，我再亲自复核其结论。**纠正我方事实错误**：① **F17 错误**——`_upsert_entity_master`（`storage/repositories/knowledge.py:865-916`）**确实**读 `item.get("world_t") or typed_data.get("world_t")` 并写 `entities.world_t`，且 world_t 为空回退 `chapter_no`；真实缺口是资料事件 `chapter_no` 空 → world_t 兜底也空 → 构造器须填 world_t（非「写入路径从不写」）；② G1「仅 11 类」→实为 12 类含 constraints；③ G2 调用点 462/559→479/606/1434；④ F14 copy_story 定位 stories.py:1606；⑤ F19 load_arc_metadata :457→:650。**排除子代理误报（其路径搞混）**：`_worldline_allowed` 在 `services/retrieval/search.py:133`（存在）、version_scope 在 `services/retrieval/documents.py:167/281/370`（存在）、`PRAGMA foreign_keys` 在 `db.py:95`（确实开启）——原 F8/F11/D14 外键论证无误。**采纳 3 处 critical + 4 处 major 设计缺口**：新增 F29（version_scope 三值 canon/project_main/au，`common.py:779`）→ D1 改三值；D15 补「fork 同步重建 entities 主档行」（否则 knowledge_items 指向不存在的 entity_id）；D14 范围扩到非 canon 资料（`source_workflows.py:591` 对所有导入都注 story_id="default"）；D11 标记待重审（主角强 main 与本世界线冲突、中立值被 `GLOBAL_WORLDLINE_IDS` 归零）；D7 补「同 canon 换文件重导识别」；新增 F30（consolidate LLM 往返输出段丢字段）→ D 期补 prompt 回填；D4 排除 relationships（走 graph_edges）；§7.2 标注 B 期验收依赖 refactor 2。
- 2026-09-04 修订19（**纠正 D11 误标：跨世界主角落 main 无争议**）：用户指出「主角的世界线用当前故事的，原著与当前故事相互独立，当前故事以主线为主、其余时间线作附属」。核实 `common.py:779`：`worldline_id=="main"` 时 `worldline_label="本项目主线"`、非 main 才标 `au` → `main` 本就等于「当前故事主线」，主角落 main 正确无冲突，读取期 D12 的「main 恒注入 + 当前章节 worldline 注入」正对应「主线为主、时间线附属」。上一轮「待重审」系误读（把跨世界主角当成 canon 角色跨世界）。=> D11 改为「作者原创主角→main、原著角色→各自 canon worldline」；新增 D18（跨世界常驻 canon 角色默认留 canon worldline，非阻塞待拍板）。
- 2026-09-04 修订20（**D18 拍板：canon 同伴升入 main**）：用户直觉「应该加在主线里」，经分析确认正确——`main` 被 D12 每章恒注入，升入 main 即自动「随主角每章出现、携带成长状态」，复用现有机制、零新增；「留老家」反而要额外发明「随行注入」规则。canon 身份靠 `source_id`/`source_title` 溯源保留（原著库的佐助仍在 `project`+canon worldline+`version_scope="canon"`），不靠 worldline，故无损失。=> D18 锁定「升入 main（一次性晋升操作，重算 entity_id）」。
- 2026-09-04 修订21（**第 5 轮审查：分块/提示词/输出存储/共享内容 四环节 17 处疏漏**）：用户要求聚焦资料提取链路的四个环节做疏漏审查。派两个子代理（一分块+提示词、一输出存储+共享内容）并行，我再亲自复核关键结论。**两个 critical（已修进 D4/D8）**：① **setting_field 语义落点缺失**——`knowledge_items` 无 `setting_field` 列（仅 `fact_key`），`_compute_entity_fact:318` 读 `setting_field or fact_key` 转 fact_key；原 D4 只定义 fact_key=槽位名、D 期却要 setting_field 必填 → 若不给取值规则，queue 会拒掉全部资料条目。D4 改为「构造器设 setting_field（=槽位名），由 _compute_entity_fact 转 fact_key」；② **sequence_order 写入链无着落**——D8 加列但 `sync_knowledge_category` INSERT 与 `_compute_entity_fact` 均不写该列，不加写入则列恒 NULL。D8 补「构造器算 = segment_index×K+order_hint → content_json → sync INSERT 写列」。**新增 §4.8** 整合其余 15 处：存储链（aliases 无列不进 entity_alias_groups、worldline 默认 main 掩盖碰撞 queue:366、资料路径无法产生 au、consolidate→enrich 字段存活、_resolve_entity_id 下钻来源）、提示词/分块（worldline 输出契约缺失、关系键名无模板、aliases/order_hint 模板缺、P1 词表无接线、P2 overlap 污染偏移、多 pass 断点续跑粒度、A 期结构化 vs 自由字典、段级 content_kind 未用）。
- 2026-09-04 修订22（**一致性完善**）：用户要求完善规划文档。做全文档一致性梳理，消除历次局部修订未同步到其它章节的残留——① §2.5 矩阵「时间线·排序键/事件实体」两行仍写「world_t 从未写入」（已被修订 18 纠正），改为「已写入、资料事件无 chapter_no 兜底、须构造器填」；② §7 完成定义：第 4 条补「setting_field 取值规则 + enrich 透传」、第 11 条补「sequence_order 写入链非 NULL」、新增第 12/13 条（字段落点完整 + 提示词契约）；③ §5 文件清单补 §4.8 落点：`core/prompts.py` 补 worldline 输出契约 + consolidate 回填 aliases/order_hint/关系键；`core/schemas.py` 补 aliases/order_hint/关系键；`storage/repositories/knowledge.py` 补 sync INSERT 写 sequence_order + aliases 进 entity_alias_groups + _resolve_entity_id 下钻来源；④ D 期改动点补「setting_field 必填的取值规则」避免 queue 误拒。
- 2026-09-04 修订23（**第 0 步代码实现完成**）：实施共享层 3 处修复——① `_apply_supersession`（`knowledge.py:347-359`）UPDATE 补 `superseded_by = knowledge_id`；② `_resolve_entity_id`（`knowledge.py:921`）加 `version_scope` 参数并纳入 domain/复用匹配/INSERT，两个调用点从 `item.get("version_scope")` 传入；③ `consolidate_extracted_knowledge` 的 `compact_items` 补 `typed_data`/`schema_version`（实际核实 enrich 已回填 source_segment_ids/titles/merged_from_pending_ids/extraction_mode，真正丢的是这两个）。回归全绿。同步修正 F26。
- 2026-09-04 修订24（**A+A' 期 · 纯逻辑/data 部分完成，编排 wiring 待续**）：完成 A 期字段级结构化引导 + A' 期数据结构/构造器——① `knowledge_types.py` 新增 `build_category_field_specs`（逐类字段规格片段，required 带 *）；② `schemas.py` `ExtractedKnowledgeItem` 加 `setting_field`/`fact_key`；③ `prompts.py` 注入字段规格 + **P4 删除 constraints**（分类说明 + category 枚举两处）；④ `common.py` 接线 field_specs + 新增对称构造器 `build_pending_knowledge_from_reference_extraction`（三处不同：project/canon/无章号 + 实体×槽位展开，F27）；⑤ `extraction_presets.py` 移除全部 8 个预设里的 constraints、新增 `character_world` 计划预设、新增 `MaterialType` 枚举 + `MATERIAL_TYPE_PRESET_MAP`（canon→world_timeline、reference→character_world、balanced→balanced）。**未完成（编排 wiring）**：creative_attachments 的多 pass 预设路由（现仍写死 balanced）、source_workflows 的构造器接线 + worldline 归属、ingestion_tasks 的 enabled_categories 按 material_type。回归：verify_entity_fact_relation(31)/verify_p1b_dynamic_slots(21)/verify_confirmed_knowledge_atomicity(14)/verify_db_storage/verify_creative_attachments/verify_context_assembly 全绿。
- 2026-09-05 修订25（**A+A' 期全部完成**）：完成剩余编排 wiring——① **构造器接入 3 条 queue 路径**（`source_workflows.py` 主提取循环 :606、粘贴快速提取 `extract_pasted_reference_to_pending` :479、整理路径 `consolidate_batch_pending_items` :1434），并修正构造器作用域逻辑（canon→`setting_scope="project"`+不保留 story_id，reference→`story`+保留 story_id）；② **worldline 归属（D10/D16）**：新增 `derive_worldline_id(source_id)`（sha256 派生稳定世界线），enrichment 对 canon 按 source_id 派生、非 canon 保持 main；③ **资料类型路由（D6/A'期）**：新增 `resolve_preset_for_material`（计划预设单 pass 模型下取第一步专家预设），`creative_attachments` 由写死 balanced 改为按 `metadata.material_type` 路由。**A+A' 期交付**：A 期（`build_category_field_specs` + schema 字段 + prompt 注入 + P4 删 constraints）+ A' 期（构造器 + 8 预设删 constraints + `MaterialType`/`MATERIAL_TYPE_PRESET_MAP`/`character_world`/`resolve_preset_for_material` + worldline 派生 + preset 路由）。回归 6 脚本全绿。
- 2026-09-05 修订26（**B 期完成**）：在 `storage/repositories/entity_query.py` 新增纯读取函数 `merge_worldline_baseline(conn, story_id, worldline_id, worldline_mode)`——跨 setting_scope（project 库 vs story 故事）与 version_scope（canon vs project_main/au）双维，对同名实体（entity_type + canonical_name）叠加事实，优先级 au>project_main>canon，replace 槽取最高优先级、append 槽 union（复用 `load_entities`/`load_entity_facts`）。单元测试通过（location replace 覆盖、appearance append 并集）。接入生成上下文装配（`context_assembly.retrieve_context`）属 refactor 2，不在本重构。
- 2026-09-05 修订27（**C 期 + D 期完成**）：C 期——`prompts.py` 新增 `recall_missed_knowledge_prompt`、`common.py` 新增 `recall_missed_knowledge`、`source_workflows.py` 提取循环接 `recall_enabled` 开关（默认关，D3 长资料开可经配置启用）。D 期——① `schemas.py` 从 3 处 category Literal + `KNOWLEDGE_CATEGORY_LABELS` 移除 `constraints`（P4/D5 最后一处落点，配合 prompt/presets 已清）；② 新增 `018_sequence_order.sql` 迁移（`sequence_order INTEGER` 加到 knowledge_items + pending）+ `CURRENT_SCHEMA_VERSION=18` + `sync_knowledge_category` INSERT/ON-CONFLICT 写 sequence_order（新增 `_int_or_none`）；③ 构造器加 `_sequence_order_for_item`（`source_segment_index×1000+order_hint`）+ `_extract_aliases`，timeline_events 落 `world_t=sequence_order`（F17 修正）。**遗留（文档化，非阻塞）**：aliases→entity_alias_groups 同步接线（P7/P1，需实体↔别名组映射）、worldline 必设校验（queue 拒缺）、D2 完整多 pass 并行子抽取。
- 2026-09-05 修订28（**最终全面审查 + 修复**）：派新鲜子代理审查全部未提交改动，发现 7 项，复核后**修复 3 项真实问题**：① `resolve_preset_for_material` 原只取计划预设第一步（canon 严重缺类）→ 改为**合并各步 categories 并集**（canon 8 类、reference 9 类）；② 018 迁移原给 pending 也加 sequence_order 列但 INSERT 不写（schema 漂移）→ 收敛为仅 knowledge_items 加列（pending 值经 content_json 携带）；③ 构造器槽位展开原遍历全部 `DYNAMIC_SLOT_KEYS`（locations/items 会被塞无关槽）→ 加 `_CATEGORY_DYNAMIC_SLOTS` 按类别过滤。**确认 3 项误报**：④ 关系边 version_scope 域不匹配（canon 构造器已设 `setting_scope="project"`，域一致，我的改动正是修 F20）；⑤ merge 函数 replace 判定用 ranked[0]（同 fact_key 的 merge_policy 恒同，非 bug）；⑥ world_t 赋给 item 无列（world_t 属 entities，`_upsert_entity_master` 消费 item.world_t）。**遗留 1 项**：recall 门控（`recall_enabled` 默认 False，D3「长资料开」需经 task 配置启用并验证 LLM 行为）。
