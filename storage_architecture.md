# NovelForge 存储架构

本文档描述当前已经生效的存储契约，不再记录早期迁移计划。项目工程边界和路线见 [project.md](./project.md)。

当前代码期望的 SQLite schema version：`9`

## 权威存储边界

NovelForge 采用 SQLite 与文件资产组合存储：

| 数据类型 | 权威来源 | 说明 |
|---|---|---|
| 全局模型档案、全局规则、全局提示词选项 | `data/global.db` | 全局结构化配置 |
| 项目、故事、知识、来源、检索、运行记录 | `data/projects/{project_name}/project.db` | 每个项目独立数据库 |
| 大纲、章节、审阅、分析、评价、导入原文 | 项目目录内 Markdown/TXT 等文件 | 正文由文件保存，生命周期登记在 `asset_files` |
| 结构化 JSON | 非权威兼容层 | 默认不写；只用于旧项目导入或显式兼容镜像 |

结构化数据写入失败必须向上抛错，不能在 DB-only 模式下静默退回文件并假装成功。

## 实际目录

```text
data/
├── global.db
├── deleted_projects/                  # 删除隔离目录；保留维护锁，当前无内置恢复入口
└── projects/
    ├── index.json                     # 启动/界面兼容索引，不是项目业务事实源
    └── {project_name}/
        ├── project.db                 # 项目结构化事实源
        ├── knowledge/                 # 旧项目兼容文件与知识相关资产
        ├── analysis/                  # 项目级 Markdown 报告
        ├── long_reference_batches/    # 旧长篇批次 JSON 兼容目录
        ├── retrieval/sources/         # 导入的外部资料正文
        └── stories/
            └── {story_id}/
                ├── outline.md
                ├── volumes/
                ├── arcs/
                ├── chapter_outlines/
                ├── chapters/
                ├── reviews/
                ├── analysis/
                ├── evaluation/
                ├── runs/
                └── retrieval/
```

具体文件目录会随资产类型演进；业务发现和删除不应依赖扫描目录，而应优先查询 `asset_files` / `asset_payloads`。

## 连接与迁移

### SQLite 设置

`storage/db.py` 为全局库和项目库统一设置：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

连接在 `with` 块结束后显式关闭，避免 Windows 上未释放句柄阻止项目重命名、归档或删除。
`novelforge/services/memory/runtime_storage.py` 统一承载运行记录的既有数据库访问：旧项目首次导入完成后，
调度、心跳和任务控制只能通过 `open_existing_project_db` 打开现有文件；项目目录已移动或删除时直接停止，
不得创建同名空目录或“幽灵”数据库。数据库曾被标记为不可用时，恢复同样使用既有文件模式，避免绕过
DB-only 错误语义并提前删除待迁移镜像。

### schema 规则

- `storage/schema.py` 的 `CURRENT_SCHEMA_VERSION` 是代码支持的唯一版本声明。
- 迁移文件必须从 `001` 连续到当前版本；缺号会拒绝启动迁移。
- 迁移在 `BEGIN IMMEDIATE` 中执行，并在取得写锁后再次检查版本，避免多个应用实例重复执行非幂等 `ALTER TABLE`。
- 已发布 migration 不修改；任何 schema 变化新增下一编号文件。
- 数据库版本高于当前代码时拒绝打开，避免旧程序损坏新数据。
- 只对零字节、无法初始化的 SQLite 文件执行隔离恢复：原文件及 `-wal/-shm/-journal` 会改名为带 UTC 时间戳的 `.corrupt-*` 文件；非空损坏库不会被自动覆盖。

### 迁移历史

| 版本 | 主要内容 |
|---|---|
| `001_initial` | 项目、故事、资产、规则、知识、来源、检索、图谱、审核和工作流基础表 |
| `002_runtime_payloads` | 检索反馈和冲突裁决无损 payload |
| `003_asset_payloads` | 小型结构化工件进入数据库 |
| `004_global_settings` | 全局模型档案和其它全局设置 |
| `005_asset_file_active_uniqueness` | 项目/故事范围的活动资产唯一性 |
| `006_prompt_option_logical_ids` | 提示词选项逻辑 ID 与存储 ID 分离 |
| `007_creative_sessions` | 自由创作会话、轮次和片段版本 |
| `008_workflow_runtime` | 后台任务 worker、租约、心跳、控制、估算、优先级和归档 |
| `009_runtime_hardening` | 项目维护锁、向量构建统计，以及旧任务残留租约清理 |

## 表分组

本节只固定表职责。列定义以 `storage/migrations/*.sql` 为准，避免文档复制完整 SQL 后失真。

### 项目与故事

- `project_meta`：项目稳定 ID、名称、基础元数据和目录移动期间的维护锁。
- `stories`：故事空间、活动状态和软删除生命周期。
- `story_profiles`：故事创作配置、世界线和检索模式。

### 文件资产与结构化工件

- `asset_files`：长文本/文件资产的逻辑键、相对路径、hash、作用域和软删除状态。
- `asset_payloads`：讨论结论、章节元数据、审阅/评价 JSON、摘要、实体卡、模板和上下文快照等小型结构化工件。

同一活动资产由 `(scope, story_id, asset_type, logical_key)` 唯一确定。SQLite 对 `NULL` 的唯一约束不能直接覆盖项目级资产，因此 migration 005 使用项目级和故事级两个部分唯一索引。

### 规则与配置

- `global_settings`：全局模型档案等键值 payload，只在 `global.db` 使用。
- `rules`：global/project/story 三层规则。
- `prompt_options`：global/project/story 三层提示词选项和覆盖关系。

### 来源与知识

- `source_documents`：资料来源、权威、类型、hash 和来源资产。
- `source_segments`：长篇分段、导入/提取状态和片段元数据。
- `knowledge_items`：已确认结构化知识。
- `pending_knowledge_items`：待审核知识和质量状态。
- `knowledge_evidence`：知识到来源、片段和检索 chunk 的证据关系；网络研究结论还会在 `location_json` 中保存 URL、原文引文和定位信息。
- `entity_alias_groups`：主名称、别名和实体类型。
- `auto_review_policy`、`auto_review_runs`：自动审核策略、批处理记录和回退快照。

### 检索

- `retrieval_documents`：可检索文档的来源、作用域、权威和世界线元数据。
- `retrieval_chunks`：稳定 chunk、正文、内容 hash 和顺序。
- `retrieval_vectors`：embedding 模型、维度、向量 blob 和内容 hash。
- `retrieval_vector_store_meta`：最近一次向量构建模式、复用/生成/删除数量。
- `retrieval_feedback`：有用、优先、无关、错误等用户反馈。
- `retrieval_eval_cases`、`retrieval_eval_runs`：固定评测用例和运行结果。
- `retrieval_conflict_resolutions`：项目资料与原作/参考资料冲突的持久裁决。
- `retrieval_chunks_fts`：schema 中预留的 FTS5 表；当前应用层词法检索尚未以它作为主要查询后端。

检索文档、chunk 和向量可以从权威资料重建；用户反馈、评测用例/结果和冲突裁决不可当作缓存清除。

向量构建元数据与具体向量行独立持久化：即使当前没有 chunk 或生成零个向量，模型、构建模式和构建计数仍可读取。空向量、零向量、非有限数值或内容 hash 过期的旧向量不会被复用；重建时只重新生成对应片段，检测到模型或向量维度变化时改为完整重建。同一次构建若返回互不一致的维度，则整次构建失败且不保存新向量。

### 工作流与自由创作

- `workflow_runs`：运行级输入、输出、错误、状态和运行时所有权；当前承载 `source_ingestion` 与 `web_research` 两类可恢复任务。
- `workflow_steps`：步骤/资料片段检查点，随 run 级联删除。
- `creative_sessions`：自由创作会话。
- `creative_turns`：会话轮次和操作。
- `creative_fragments`：片段版本、父子关系、接受状态和审计信息。

### 图谱预留

- `graph_nodes`
- `graph_edges`

表结构已经存在，但当前产品尚未建立正式 GraphRAG 构建和查询链路。它们不能被文档或 UI 表述为已完成能力。

## 持久资料任务

长篇资料任务复用通用 `workflow_runs/workflow_steps`，不创建第二套任务数据库。

### 记录映射

`workflow_runs` 中 `workflow_type='source_ingestion'` 的记录表示资料任务：

- `input_json`：创建时输入。
- `output_json`：任务配置、估算、总体进度、导入/提取/整理/自动审核阶段游标、最近结果和兼容字段。
- `error_json`：运行级错误。
- `workflow_steps`：以稳定片段 ID 保存分段状态、尝试次数、输入、输出和错误。
- `worker_id`、`lease_expires_at`、`heartbeat_at`：运行时所有权。
- `control_requested`：pause/resume/cancel 控制请求。
- `priority`：队列顺序。
- `estimated_*`：创建时 Token/费用估算快照。
- `archived_at`：历史归档，不等同业务状态。

### 原子领取

领取逻辑位于 `storage/repositories/ingestion_task_leases.py`，必须在同一写事务中完成“选择候选 + 更新 owner/租约 + 读回任务”：

```text
BEGIN IMMEDIATE
  -> 查找 queued，或租约已过期的 running 任务
  -> 按 priority DESC, created_at ASC 选择
  -> 写入 worker_id、lease_expires_at、heartbeat_at、status=running
  -> 返回已领取记录
COMMIT
```

正常心跳只有当前 `worker_id` 且租约尚未过期时可以续租。worker 检查点同时校验 `running` 状态、owner 和有效租约；终态快照与清理 worker/心跳/租约必须在同一事务提交。失去租约的旧 worker 不得继续覆盖任务状态；真正恢复前还要用 long reference batch 的已落盘分段结果对账。

未处理的 `pause/cancel` 也是终态提交围栏的一部分：普通完成不能清掉并发控制请求。若所有阶段已在控制请求到达前落盘，worker 会显式确认该请求并按真实结果原子完成；否则转入暂停或取消。任务结果由批次与阶段检查点重建，因此跨重启统计不会退回为零。

同一长篇资料批次只允许一个未归档的未完成任务。创建与归档恢复都在写事务中检查批次唯一性；任务创建还会对数据库中的批次修订时间和所选 `segment_id` 做 CAS 校验，拒绝界面旧快照。批次保存、删除与任务创建统一由 `BEGIN IMMEDIATE` 串行，人工写入不能越过占用任务；运行中任务只有同时匹配 `task_id`、`worker_id` 和有效租约才能写检查点。数据库事务成功后才尽力同步非权威 JSON 镜像，拒绝或回滚不得先改镜像。项目重命名或删除前先写入 `project_meta.maintenance_mode`，阻止人工批次修改以及任务创建、重新入队和领取；持有有效租约的 worker 仍可完成检查点，生命周期操作会因 running 任务而中止并解除维护锁。调度器对旧项目名只读写既有数据库，不会在目录移动后重建空项目。

### 控制与归档

- 运行中的暂停/取消请求在下一个分段或阶段检查点生效。
- `failed` 和 `completed_with_errors` 保留已完成片段与阶段；重试只重置失败阶段，提取或整理重试会同时使依赖它的下游阶段失效。
- 只有 `failed/completed_with_errors/completed/cancelled` 可以归档。
- 恢复归档的未完成任务时会重新检查批次及所选片段；批次已删除或片段已替换时拒绝恢复。
- 永久删除要求任务已经归档，删除 run 时由外键级联删除 steps。
- 批量清理只删除早于指定时间的归档任务，不操作活动任务。

## 持久网络研究任务

网络研究复用同一组 `workflow_runs/workflow_steps`，不引入 LangGraph 自身的第二套持久状态。`workflow_type='web_research'` 的 run 保存研究目标、来源角色、用户提供的官方域名白名单、模型开关、搜索/抓取上限、估算、评测结果和人工审核所需的证据摘要；六个稳定 step 分别对应：

```text
plan -> search -> fetch -> extract -> verify -> evaluate
```

`storage/repositories/durable_tasks.py` 为这类任务提供通用的原子领取、租约心跳、owner fencing、控制请求、归档和删除能力。`novelforge/services/memory/web_research_tasks.py` 负责领域对象与数据库行之间的转换，workflow 与 UI 不直接访问 SQL。LangGraph 只在已领取的 `search` step 内并行执行来源角色 Collector，输出随步骤检查点回写 SQLite；暂停、恢复、取消、重试和失联接管均以 SQLite 为准。

研究任务按页面保存抓取与提取检查点。重启后已成功页面不会重复抓取或调用提取模型；失败阶段重试会清除该阶段的旧错误和所有失效下游结果，同时保留仍可复用的成功页面。网页快照路径以 `research_task_id + 最终 URL` 命名，避免不同任务因相同 URL 共享状态；重定向到同一最终 URL 的多个搜索结果则在同一任务内合并来源角色和请求 URL。自动抓取的网页正文作为文件资产登记，元数据包含 `research_task_id`、`story_id`、来源角色、权威评估、`untrusted_web_content=true` 和 `retrieval_status=quarantine`。隔离状态的网页不会进入 `retrieval_documents`；只有用户在任务结果页明确启用后才参与后续索引重建，并始终以不可信外部数据边界装配进模型上下文。归档任务永久删除时会同时删除该任务拥有的网页快照并重建检索资产。

Verifier 产出的事实结论仍不是正式知识。用户选择“送入待审核知识”后，结论写入 `pending_knowledge_items`，对应 URL、精确引文、权威与置信度同步写入 `knowledge_evidence`。只有既有知识审核流程可以把它提升为 `knowledge_items`，并继续保留证据关系。

## 文件资产契约

长文本不重复塞入 JSON payload。保存文件资产时至少登记：

- 稳定 `asset_id`。
- `asset_type` 和作用域内稳定 `logical_key`。
- 可变标题与不可越界的相对路径。
- 内容 hash、MIME 类型、来源类型和来源引用。
- `story_id`（项目级资产为空）。
- 创建、更新和软删除时间。

文件删除流程应先通过服务层确定数据库记录和实际路径，执行路径安全校验，再更新数据库生命周期。不能根据用户标题拼接任意路径。

## JSON 兼容策略

默认值：

```text
NOVELFORGE_WRITE_JSON_MIRRORS=0
```

默认 DB-only 模式下：

- LLM profiles、规则、提示词选项、故事配置、知识、运行快照、检索 manifest/vector/eval/feedback 等结构化数据只写 SQLite。
- 如果首次打开的是旧项目且数据库尚未建立，bootstrap 会先从已有 JSON/Markdown 导入，再创建数据库事实源。
- 某类结构化资源成功保存后，其旧 JSON 镜像可以被移除，避免空列表或空规则被旧文件“复活”。
- Markdown/TXT 正文和外部资料不受镜像开关影响。

只有明确验证旧式集成时才临时开启：

```powershell
$env:NOVELFORGE_WRITE_JSON_MIRRORS='1'
streamlit run app.py
```

这不是长期双写方案。新功能不得依赖镜像存在，也不得把 JSON 恢复为权威来源。

## 备份与恢复

### 常规备份

最安全的做法是停止 NovelForge 后备份整个 `data/`：

- `global.db` 与所有项目 `project.db`。
- 项目 Markdown/TXT 文件资产。
- SQLite 的 `-wal`/`-shm` 文件如果备份时应用仍在运行，也必须与主库保持同一时点；因此推荐停应用后复制。
- `.env` 包含密钥，应单独安全保存，不要提交到版本库。

### 健康检查

```powershell
# 项目数据库
.\.venv\Scripts\python.exe tools\inspect_project_db.py <project_name>

# 全局数据库
.\.venv\Scripts\python.exe tools\inspect_global_db.py
```

检查结果包括 schema version、可写性、journal mode、foreign key 状态和核心表记录数。

### 旧项目导入或手动修复

```powershell
.\.venv\Scripts\python.exe tools\sync_project_db.py <project_name>
.\.venv\Scripts\python.exe tools\sync_global_db.py
```

同步工具用于从旧 JSON/Markdown 回填 SQLite，不会把 SQLite 新数据反向覆盖为旧文件权威。执行前应先备份对应项目。

删除项目会把目录隔离到 `data/deleted_projects/`，并在归档数据库中保留维护锁，防止后台任务误领取。当前没有一键恢复入口；只把目录移回 `data/projects/` 并不构成完整恢复，还必须通过受控操作清除 `project_meta.maintenance_mode` 并重新登记项目。人工恢复前应先备份目录和数据库。

## 验证

```powershell
# DB-first 读取、删除语义、无 JSON 镜像和全局配置
.\.venv\Scripts\python.exe tools\verify_db_storage.py

# 代表性端到端数据库链路
.\.venv\Scripts\python.exe tools\verify_db_pipeline.py

# 资料任务基础状态、后台租约、维护锁与跨重启结果恢复
.\.venv\Scripts\python.exe tools\verify_ingestion_tasks.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_runtime.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_hardening.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_recovery.py
.\.venv\Scripts\python.exe tools\verify_ingestion_batch_mutation_guard.py

# 向量异常处理、增量构建与零向量行时的元数据持久化
.\.venv\Scripts\python.exe tools\verify_retrieval_hardening.py
.\.venv\Scripts\python.exe tools\verify_vector_metadata_persistence.py

# 网络研究 Agent、持久任务、证据与隔离区（离线 Mock）
.\.venv\Scripts\python.exe tools\verify_web_research.py
.\.venv\Scripts\python.exe tools\verify_web_research_tasks.py
```

验证脚本创建的项目使用专用 `_verify_*` 前缀。脚本和人工清理都必须校验目标在工作区和允许前缀内。

## 不变量

1. SQLite 是结构化权威来源，JSON 不是第二权威来源。
2. 长文本文件与 `asset_files` 登记必须保持一致。
3. 所有长期关系使用稳定 ID，不使用中文标题、路径或列表下标作主键。
4. 高频过滤、排序和关联字段使用独立列；低频扩展信息才进入 JSON payload。
5. UI 和 workflow 不直接拼 SQL；所有 SQL 进入 repository。
6. 多记录变更要在一个事务中完成，失败时不得留下半套状态。
7. 检索缓存可以重建，反馈、评测、冲突裁决和运行检查点不可随意删除。
8. schema 迁移连续、可重复检查、不可回写历史。
9. 软删除记录默认不出现在活动查询中；永久删除必须经过显式业务条件。
10. 数据库不可用时明确失败，不以静默 fallback 掩盖数据丢失。
