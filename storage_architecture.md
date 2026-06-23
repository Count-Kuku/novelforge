# NovelForge Storage Architecture

本文档用于固定 NovelForge 的长期存储方向，目标是在项目尚未积累正式数据前，尽早确定稳定的存储边界，减少未来兼容和迁移成本。

当前结论：

* SQLite 作为结构化数据的权威存储。
* Markdown / TXT / JSON 导出文件作为长文本资产和可读产物。
* 检索、证据、结构化知识、图谱、工作流运行记录都以稳定 ID 串联。
* 从第一版数据库开始保留 `schema_version` 和 migrations，不依赖一次性硬编码建表。
* 当前代码期望的数据库 schema version 是 `5`。

---

# 目标结构

推荐最终目录结构：

```text
data/
  global.db
  projects/
    {project_id}/
      project.db
      project_manifest.json
      assets/
        outlines/
        chapters/
        reviews/
        analysis/
        sources/
        exports/
      backups/
```

说明：

* `global.db` 保存跨项目配置，例如 LLM profiles、全局规则、全局 prompt options。
* `project.db` 保存单个项目的结构化数据，是项目资料库、RAG、图谱、运行记录的权威来源。
* `assets/` 保存长文本资产，例如章节正文、大纲、评审 Markdown、分析报告、原始资料。
* `project_manifest.json` 只保存少量便于人工识别的信息，例如项目显示名、创建时间、数据库版本摘要。它不应成为业务数据权威来源。

---

# 存储边界

进入数据库的数据：

* project / story metadata
* creative profile
* rules
* prompt options
* LLM profiles
* global settings
* structured knowledge
* pending knowledge
* auto-review policy and runs
* source document metadata
* source segments
* evidence records
* retrieval documents
* retrieval chunks
* retrieval vectors metadata or blobs
* retrieval feedback
* retrieval eval cases and runs
* workflow runs and steps
* graph nodes and edges
* asset file registry

保留为文件的数据：

* outline body
* volume outline body
* arc outline body
* chapter outline body
* chapter body
* review Markdown
* analysis Markdown
* imported raw source text
* exported packages

文件资产必须在数据库中登记路径、hash、类型、所属 story、更新时间和生成来源。业务查询不应直接扫描目录作为主要数据来源。

---

# 核心设计原则

1. 所有长期记录使用稳定 ID。

不要使用中文名称、文件路径、列表下标作为长期身份。推荐 ID：

```text
project_id
story_id
asset_id
source_id
segment_id
knowledge_id
pending_id
evidence_id
document_id
chunk_id
node_id
edge_id
run_id
step_id
```

2. 所有主表保留时间字段。

```text
created_at
updated_at
deleted_at
```

`deleted_at` 用于软删除。只有缓存、临时索引、可重建数据可以硬删除。

3. JSON 字段只用于灵活低频数据。

适合放入 `metadata_json` 或 `content_json` 的内容：

* 类别差异很大的知识字段
* UI 展示配置
* 原始 LLM payload
* 不常作为查询条件的扩展字段

经常用于过滤、排序、关联的数据必须提升为独立列，例如：

```text
category
canon_status
worldline_id
story_id
source_type
authority
confidence
evidence_strength
embedding_model
status
```

4. 数据库是结构化权威来源，文件是正文资产来源。

章节正文可以继续在 Markdown 文件中，但章节的 ID、标题、状态、路径、hash、所属 story、所属 volume / arc 必须在数据库中。

5. 检索资产可重建，但检索反馈不可丢。

可重建：

* retrieval documents
* retrieval chunks
* lexical FTS index
* embedding vectors

不可随意丢弃：

* user feedback
* eval cases
* eval runs
* conflict resolutions

---

# 数据库模块边界

推荐新增：

```text
storage/
  __init__.py
  db.py
  schema.py
  repositories/
    projects.py
    stories.py
    assets.py
    rules.py
    prompt_options.py
    knowledge.py
    sources.py
    retrieval.py
    workflows.py
    graph.py
  migrations/
    001_initial.sql
```

职责：

* `storage/db.py`：连接、事务、路径、PRAGMA 设置。
* `storage/schema.py`：当前 schema 版本、初始化、迁移入口。
* `repositories/*.py`：封装 SQL，不让 UI 和 workflow 模块直接拼 SQL。
* `memory.py`：短期内保留为兼容 facade，逐步改为调用 repository。

推荐 SQLite PRAGMA：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

---

# Schema 草案

以下是第一版 `001_initial.sql` 应覆盖的长期核心表。字段可以在实现时细化，但表边界建议保持稳定。

## 元信息

```text
schema_migrations
- version
- applied_at

project_meta
- project_id
- name
- title
- genre
- description
- created_at
- updated_at

stories
- story_id
- name
- description
- status
- is_active
- created_at
- updated_at
- deleted_at

story_profiles
- story_id
- profile_json
- worldline_id
- worldline_name
- retrieval_mode
- created_at
- updated_at
```

## 资产文件

```text
asset_files
- asset_id
- story_id nullable
- asset_type
- logical_key
- title
- relative_path
- content_hash
- mime_type
- source_kind
- source_ref
- metadata_json
- created_at
- updated_at
- deleted_at
```

典型 `asset_type`：

```text
outline
volume_outline
arc_outline
chapter_outline
chapter
review_markdown
analysis_markdown
evaluation_markdown
raw_source
export
```

## 规则和 prompt options

```text
rules
- rule_id
- scope
- story_id nullable
- capability
- content
- enabled
- priority
- source
- metadata_json
- created_at
- updated_at
- deleted_at

prompt_options
- option_id
- scope
- story_id nullable
- capability
- category
- slot
- name
- content
- enabled
- built_in
- priority
- source
- source_kind
- source_ref
- tags_json
- created_at
- updated_at
- deleted_at
```

`scope` 推荐固定为：

```text
global
project
story
```

## 结构化知识

```text
knowledge_items
- knowledge_id
- story_id nullable
- category
- name
- title
- summary
- content_json
- canon_status
- worldline_id
- worldline_name
- confidence
- importance
- evidence_strength
- source_id nullable
- segment_id nullable
- extraction_mode
- setting_scope nullable
- setting_role nullable
- injection_policy nullable
- created_at
- updated_at
- deleted_at

pending_knowledge_items
- pending_id
- story_id nullable
- category
- name
- title
- summary
- content_json
- canon_status
- worldline_id
- confidence
- importance
- evidence_strength
- source_id nullable
- segment_id nullable
- extraction_mode
- quality_json
- status
- created_at
- updated_at
- deleted_at

knowledge_evidence
- evidence_id
- knowledge_id nullable
- pending_id nullable
- source_id nullable
- segment_id nullable
- chunk_id nullable
- quote
- location_json
- confidence
- evidence_strength
- created_at
```

`category` 推荐继续沿用当前分类：

```text
characters
items
abilities
world_rules
locations
organizations
timeline_events
relationships
writing_style
dialogue_style
narrative_techniques
constraints
```

## 别名

```text
entity_alias_groups
- alias_group_id
- canonical_name
- aliases_json
- entity_type
- story_id nullable
- worldline_id nullable
- metadata_json
- created_at
- updated_at
- deleted_at
```

## 来源和分段

```text
source_documents
- source_id
- story_id nullable
- title
- source_type
- authority
- canon_status
- original_asset_id nullable
- content_hash
- metadata_json
- created_at
- updated_at
- deleted_at

source_segments
- segment_id
- source_id
- segment_index
- title
- asset_id nullable
- text_hash
- summary
- import_status
- extraction_status
- last_extraction_mode
- metadata_json
- created_at
- updated_at
- deleted_at
```

`source_type` 示例：

```text
canon
reference
project
user_note
long_form_source
knowledge_only
```

## 检索

```text
retrieval_documents
- document_id
- story_id nullable
- source_id nullable
- asset_id nullable
- knowledge_id nullable
- document_type
- scope
- title
- summary
- authority
- canon_status
- worldline_id
- metadata_json
- created_at
- updated_at
- deleted_at

retrieval_chunks
- chunk_id
- document_id
- chunk_index
- text
- token_count
- content_hash
- metadata_json
- created_at
- updated_at
- deleted_at

retrieval_vectors
- chunk_id
- embedding_model
- vector_dim
- vector_blob
- content_hash
- created_at
- updated_at

retrieval_feedback
- feedback_id
- chunk_id
- story_id nullable
- task_type
- feedback_type
- reason
- weight
- created_at

retrieval_eval_cases
- case_id
- story_id nullable
- name
- query
- task_type
- expected_json
- enabled
- created_at
- updated_at
- deleted_at

retrieval_eval_runs
- run_id
- case_id nullable
- story_id nullable
- status
- result_json
- created_at
```

推荐使用 SQLite FTS5 建立全文索引：

```text
retrieval_chunks_fts
- title
- text
- entity_names
- source_terms
```

FTS 表可以作为可重建索引，不作为权威存储。

## 检索冲突

```text
retrieval_conflict_resolutions
- resolution_id
- story_id nullable
- conflict_key
- preferred_scope
- preferred_source_id nullable
- decision
- rationale
- created_at
- updated_at
```

## 图谱

```text
graph_nodes
- node_id
- story_id nullable
- node_type
- canonical_name
- display_name
- knowledge_id nullable
- alias_group_id nullable
- canon_status
- worldline_id
- metadata_json
- created_at
- updated_at
- deleted_at

graph_edges
- edge_id
- story_id nullable
- source_node_id
- target_node_id
- relation_type
- direction
- confidence
- evidence_id nullable
- metadata_json
- created_at
- updated_at
- deleted_at
```

`node_type` 示例：

```text
character
location
organization
event
item
ability
world_rule
constraint
style
```

`relation_type` 示例：

```text
member_of
located_in
participates_in
owns
uses_ability
teacher_of
ally_of
enemy_of
causes
precedes
constrains
conflicts_with
alias_of
```

第一版 GraphRAG 不需要复杂图数据库。先支持：

* 实体识别到节点。
* 一跳 / 两跳扩展。
* 根据边找到相关 knowledge / evidence / chunks。
* 按 story、worldline、canon_status 过滤。

## 工作流

```text
workflow_runs
- run_id
- story_id nullable
- workflow_type
- status
- parent_run_id nullable
- input_json
- output_json
- error_json
- started_at
- finished_at
- created_at

workflow_steps
- step_id
- run_id
- step_name
- step_order
- status
- input_json
- output_json
- error_json
- artifact_asset_id nullable
- started_at
- finished_at
```

---

# GraphRAG 接入方式

NovelForge 的图谱不应替代现有 RAG，而应成为 retrieval 的一个证据扩展器。

推荐流程：

```text
user task
↓
build retrieval plan
↓
lexical / semantic retrieval
↓
entity extraction from query and top hits
↓
graph node lookup
↓
graph expansion
↓
related knowledge / evidence / chunks
↓
rerank and diversify
↓
format prompt context
```

图谱检索适合解决：

* 角色关系链。
* 事件前后因果。
* 角色持有物、能力、组织归属。
* worldline / canon 分支过滤。
* 章节写作前的设定约束召回。
* 冲突检测时寻找相关证据。

不适合第一版就做：

* 自动全局推理。
* 复杂路径搜索 UI。
* 独立 Neo4j 部署。
* 完全替代 chunk retrieval。

---

# 分阶段实施路线

## Phase 0：冻结设计

目标：

* 确认本文档的存储边界。
* 决定每项目一个 `project.db`，全局一个 `global.db`。
* 决定长文本资产继续存文件。
* 决定所有结构化记录使用稳定 ID。

产物：

* `storage_architecture.md`
* 后续同步更新 `project.md` 的 Roadmap / Storage 章节。

## Phase 1：新增 storage 层

目标：

* 新增 `storage/` 包。
* 新增 SQLite 连接、事务、schema migration 机制。
* 新增 `001_initial.sql`。
* 暂不替换业务功能。

验收：

* 启动时可以为新项目创建 `project.db`。
* 可以读取当前 schema version。
* 重复初始化幂等。

## Phase 2：项目、故事、资产登记入库

目标：

* 项目 metadata 入库。
* story index 入库。
* outline/chapter/review/analysis 等文件通过 `asset_files` 登记。
* `memory.py` 暂时提供兼容返回格式。

验收：

* UI 仍可正常创建项目和 story。
* 文件资产仍保存在原路径或新 `assets/` 路径。
* 数据库能列出项目下所有 story 和资产。

当前落地状态：

* story index 已支持 DB-first 读取，并在 DB 为空时从旧 `stories.json` 回填。
* creative profile、project/story rules、project/story prompt options 已支持写入和 DB-first 读取。
* outline/chapter/review/analysis/evaluation/workflow/retrieval 等文件资产已登记到 `asset_files`。
* 小型 JSON 工件通过 `asset_payloads` 保存结构化 payload，包括 discussion artifacts、outline/chapter metadata、review/evaluation JSON、chapter summaries、entity cards、extraction templates、rule conflict resolutions。

## Phase 3：结构化知识入库

目标：

* `knowledge_items`
* `pending_knowledge_items`
* `knowledge_evidence`
* `entity_alias_groups`
* auto-review records

验收：

* pending review、confirmed knowledge 编辑、批量确认、回滚逻辑使用 repository。
* 旧 JSON 写入路径停止作为新数据权威来源。
* 检索重建能从数据库读取 confirmed knowledge。

当前落地状态：

* confirmed structured knowledge、pending knowledge、entity aliases 已支持写入 `project.db`。
* `memory.py` 的 confirmed knowledge、pending knowledge、entity aliases 读取入口已改为 DB-first。
* 如果旧项目数据库为空但 JSON 文件里仍有数据，读取入口会回退 JSON 并尝试回填数据库，避免旧项目突然读空。
* `sync_project_db.py` 仍明确从 JSON / Markdown 文件回填数据库，可作为修复或一次性迁移工具。

## Phase 4：来源、分段、证据入库

目标：

* `source_documents`
* `source_segments`
* `knowledge_evidence`
* long-form batch metadata 替换 JSON。

验收：

* 长文导入、重复检测、分段、继续处理、失败重试都能从数据库恢复。
* 原始资料正文仍保存为文件资产。
* 每条知识可以追溯到来源、分段、证据片段。

当前落地状态：

* long reference batches 已支持写入 `source_documents/source_segments` 并 DB-first 读取。
* retrieval source files 已支持通过数据库列出；原文仍作为文件资产保留。

## Phase 5：检索索引入库

目标：

* `retrieval_documents`
* `retrieval_chunks`
* `retrieval_vectors`
* `retrieval_feedback`
* eval cases / runs
* conflict resolutions

验收：

* `retrieval/manifest.json` 不再是权威索引。
* FTS5 支持关键词检索。
* hybrid retrieval 可以从 DB 读取 chunks 和 vectors。
* 用户反馈和 evaluation run 保持持久。

当前落地状态：

* retrieval manifest、chunks、vectors、eval cases/runs、feedback、conflict resolutions 已支持 DB-first 读取。
* schema version 2 为 `retrieval_feedback` 和 `retrieval_conflict_resolutions` 增加 `payload_json`，用于无损替代旧 JSON。
* schema version 3 增加 `asset_payloads`，用于让小型 JSON 工件 DB-first。
* schema version 4 增加 `global_settings`，用于让 LLM profiles 和全局规则冲突记录进入 `global.db`。
* schema version 5 增加项目级/故事级 active asset 唯一索引，并在迁移时软删除同键重复 active asset，避免 SQLite `NULL` 唯一约束放过项目级重复资产。

## Phase 6：图谱层

目标：

* `graph_nodes`
* `graph_edges`
* 从 confirmed knowledge 构建图谱。
* retrieval 中支持 graph expansion。

验收：

* 输入角色名可以找到相关角色、事件、地点、约束。
* 支持 worldline / canon_status 过滤。
* GraphRAG 结果能进入 retrieval debug preview 和 prompt context。

## Phase 7：工作流运行记录入库

目标：

* `workflow_runs`
* `workflow_steps`
* pipeline snapshots、transition logs、resume metadata 入库。

验收：

* 可以列出、检查、恢复失败 run。
* 可以对比不同 run 的输入、输出、错误和评估。

当前落地状态：

* workflow run snapshots 已支持写入 `workflow_runs/workflow_steps` 并 DB-first 读取、列出。
* `project_manager.py` 的 workflow run 列表、章节清单中的 review/evaluation JSON 状态、以及对应删除操作已切到 DB-first；删除兼容 JSON 镜像后仍能从 `workflow_runs` 和 `asset_payloads` 恢复项目管理视图。
* `retrieval.py` 重建检索 manifest 时已从 `asset_payloads` 读取 review/evaluation payload 和 chapter discussion payload；删除兼容 JSON 镜像后，这些结构化工件仍会进入 RAG 文档。
* `resource_browser.py` 依赖的 retrieval source 列表已通过 `project_manager.py` 改为 `source_documents` DB-first，文件资产仍负责保存外部源正文。
* `list_volumes/list_arcs/list_chapter_inventory` 已能从 `asset_files/asset_payloads` 发现 volume、arc、chapter 元数据记录，不再要求对应 JSON 镜像文件存在。
* `verify_db_first_reads.py` 已覆盖 discussion artifacts、volume/arc/chapter metadata、arc chapter plan、project/story rule conflict resolutions 等小型 JSON 工件的 DB-first 读取。
* discussion artifacts、arc chapter plan、long reference batches、retrieval source registry 的删除函数已支持 DB-only 软删除；`verify_db_delete_semantics.py` 用于验证删除 JSON/文件镜像后仍能删除数据库记录。
* outline、chapter outline、chapter body、review Markdown、analysis Markdown、evaluation Markdown 等长文本资产仍由文件保存正文，但 `project_manager.py` 的列表发现和删除语义已接入 `asset_files`；删除文件镜像后仍能通过 DB 记录发现并软删除生命周期记录。
* global rules 保存已修正为只写入 `global.db` 的 global scope；project rules 不再误同步到 global scope。`verify_global_db_first_reads.py` 在隔离临时目录中验证全局 LLM profiles、global rules、global prompt options、global rule conflict resolutions 删除 JSON 镜像后仍能从 `global.db` 读回。
* 结构化 JSON 兼容镜像默认不再写入；只有显式设置 `NOVELFORGE_WRITE_JSON_MIRRORS=1` 时才会写 JSON 镜像。默认模式下，LLM profiles、rules、prompt options、story profiles、memory metadata、knowledge payloads、discussion artifacts、metadata JSON、review/evaluation JSON、workflow snapshots、retrieval manifest/vectors/eval/feedback 等结构化数据写入 SQLite 并从 SQLite 读回；保存函数触达的旧结构化 JSON 镜像会被删除，以避免旧 JSON 在空列表/空规则场景中作为 fallback 复活；Markdown 正文、分析/评估报告、外部资料正文等长文本资产仍保留文件形态。
* 默认 DB-only 模式下，SQLite 不再是 best-effort 辅助层，而是必需存储层；数据库初始化、读取、写入、软删除失败会直接抛错，避免无 JSON 镜像时静默丢失结构化数据。
* `verify_db_no_json_mirrors.py` 在隔离临时目录中验证 DB-only 保存模式：写入代表性全局和项目数据，确认没有生成结构化 JSON 镜像，且所有公开读取函数仍能从 `global.db` / `project.db` 读回。

## Phase 8：清理旧 JSON 存储

目标：

* 删除或降级旧 JSON 写入路径。
* 保留必要导出功能。
* 文档更新为 DB-first 架构。

验收：

* 新项目不再依赖旧 JSON 作为主存储。
* 测试覆盖关键 repository、retrieval rebuild、knowledge confirmation、source ingestion。

---

# 不推荐的路线

暂不推荐：

* 直接上 Neo4j。它适合重图谱系统，但会增加本地部署和打包复杂度。
* 直接上 Postgres。NovelForge 当前是本地桌面式应用，SQLite 更合适。
* 把 Chroma / FAISS 当主数据库。向量库适合做检索索引，不适合作为项目权威资料库。
* 把所有正文塞进数据库。长篇小说正文和导入原文更适合作为文件资产。
* 使用中文标题作为主键。标题可以改，ID 不应该改。
* 没有 migration 机制就写表。即使现在没有数据，也必须从第一天保留迁移路径。

---

# 第一批代码任务建议

如果从本文档开始实现，建议先做以下任务：

1. 新增 `storage/` 包。
2. 新增 `storage/migrations/001_initial.sql`。
3. 新增 `storage/db.py`，提供 `get_project_db(project_id)`、`transaction()`、`initialize_project_db()`。
4. 新增 `storage/schema.py`，提供 `ensure_schema()` 和 `get_schema_version()`。
5. 新增 repository 基类或轻量工具函数。
6. 为 project/story metadata 写最小 repository。
7. 在不改变 UI 行为的前提下，让新项目创建时同时创建 `project.db`。
8. 添加最小测试：初始化幂等、schema version 正确、外键启用、WAL 设置生效。

完成以上步骤后，再开始迁移 knowledge，而不是一开始就大面积改 `app.py`。

---

# 数据库健康检查

可以用以下命令检查某个项目的 `project.db` 是否可写、schema version 是否正确，以及核心表中已有多少记录：

```powershell
.\.venv\Scripts\python.exe tools\inspect_project_db.py <project_name>
```

返回字段：

* `ok`: 数据库是否成功打开、迁移并完成写入探针
* `db_path`: 项目数据库路径
* `schema_version`: 当前数据库 schema version
* `expected_schema_version`: 当前代码期望的 schema version
* `writable`: 是否能写入健康检查记录
* `journal_mode`: SQLite journal 模式
* `foreign_keys`: 外键是否启用
* `table_counts`: 核心表记录数
* `error`: 失败原因

如果需要把现有 JSON / Markdown 项目文件全量回填同步到 `project.db`，可以运行：

```powershell
.\.venv\Scripts\python.exe tools\sync_project_db.py <project_name>
```

该命令会同步：

* story index
* confirmed structured knowledge
* pending knowledge
* entity aliases
* auto-review policy and runs
* RAG eval cases / runs / feedback
* retrieval conflict resolutions
* long reference batches
* retrieval source files
* retrieval manifest / chunks
* retrieval vectors
* workflow run snapshots
* story profiles
* project/story rules
* project/story prompt options
* small JSON artifact payloads

同步命令不会删除 JSON / Markdown 原文件；当前阶段项目内结构化数据读取已经优先使用数据库，旧 JSON 主要作为兼容回填来源和人工可读镜像。

可以用以下命令检查全局数据库 `data/global.db`：

```powershell
.\.venv\Scripts\python.exe tools\inspect_global_db.py
```

如果需要把现有全局 JSON 配置回填到 `global.db`，可以运行：

```powershell
.\.venv\Scripts\python.exe tools\sync_global_db.py
```

该命令会同步：

* LLM profiles
* global rules
* global prompt options
* global rule conflict resolutions

同步命令不会删除旧全局 JSON 文件；当前阶段全局结构化配置读取已经优先使用 `global.db`，旧 JSON 主要作为兼容回填来源和人工可读镜像。

也可以运行端到端验证脚本，创建一个验证项目并依次写入知识、来源、检索索引、向量、评估反馈和工作流快照：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_pipeline.py
```

也可以指定项目名：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_pipeline.py _db_verify_manual
```

该脚本会写入验证数据，适合开发阶段确认数据库链路是否真正可写。验证项目仍位于 `data/projects/` 下。

如果需要验证结构化数据已经真正 DB-first，并同时覆盖 DB-only 删除语义，可以运行总验证：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_storage.py
```

总验证会依次运行 `verify_global_db_first_reads.py`、`verify_db_first_reads.py`、`verify_db_delete_semantics.py` 和 `verify_db_no_json_mirrors.py`。

结构化数据现在默认不生成 JSON 兼容镜像。如果临时需要恢复旧式镜像写入，可以在启动应用或运行脚本前设置：

```powershell
$env:NOVELFORGE_WRITE_JSON_MIRRORS='1'
.\.venv\Scripts\python.exe app.py
```

该开关只影响结构化 JSON 镜像写入；默认 DB-only 模式下，旧 JSON 在尚未被对应保存函数触达前仍可作为兼容回填来源读取，一旦该结构化资源被重新保存，对应旧镜像会被删除。Markdown / TXT 正文类资产仍按文件保存。

如果只需要单独验证 DB-first 读取，可以运行：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_first_reads.py
```

该脚本会创建 `_db_first_verify_*` 验证项目，先写入数据库和 JSON 镜像，再删除该验证项目内的兼容 JSON 镜像，最后从公开读取函数和 `project_manager.py` 列表函数读回数据。它只允许操作 `_db_first_verify_` 前缀项目，避免误删真实项目文件。

如果需要验证 DB-only 删除语义，可以运行：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_delete_semantics.py
```

该脚本会创建 `_db_delete_verify_*` 验证项目，写入 discussion artifacts / arc chapter plan / long reference batch / retrieval source registry，删除对应 JSON 或文件镜像，再调用公开删除函数确认数据库记录可以被软删除。

如果需要单独验证关闭 JSON 镜像后的 DB-only 保存模式，可以运行：

```powershell
.\.venv\Scripts\python.exe tools\verify_db_no_json_mirrors.py
```

该脚本会在 `.tmp_db_no_json_mirrors/` 下创建隔离工作区，写入代表性全局和项目结构化数据，确认没有生成结构化 JSON 镜像，并从 SQLite 读回所有数据。
