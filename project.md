# NovelForge 项目架构

本文档是 NovelForge 的长期工程事实源，记录当前架构、模块边界、运行时契约、已知技术债和下一阶段优先级。面向使用者的安装与操作说明见 [README.md](./README.md)，数据库细节见 [storage_architecture.md](./storage_architecture.md)。

仓库版本标记：`v0.7.1`

## 文档职责

| 文档 | 长期职责 | 更新规则 |
|---|---|---|
| `README.md` | 中文用户入口、安装、主要工作流和限制 | 用户可见行为变化时更新 |
| `README.en.md` | 英文用户入口，与中文 README 保持能力级一致 | 与中文 README 同步 |
| `project.md` | 当前架构、模块职责、开发约束和路线优先级 | 架构或模块边界变化时更新 |
| `storage_architecture.md` | 当前 DB-first 存储、schema、迁移和恢复契约 | schema 或权威存储边界变化时更新 |
| `docs/releases/*.md` | 已发布版本的历史记录 | 发布后只修正事实错误，不改写历史 |

一次性实施计划、已完成迁移清单和阶段性审查笔记不作为长期文档保留；其中仍然有效的约束应合并到以上事实源。

## 项目定位与当前状态

NovelForge 是一个面向长篇小说和同人创作的本地 LLM 工作台。它的核心不是单次聊天，而是持续维护项目、故事、资料、设定、检索证据和创作运行记录。

当前已经形成可用闭环：

- 项目与多故事空间，项目级资料可共享，故事级正文和创作配置相互隔离。
- 总纲、分卷、剧情段、章节细纲、正文、审阅、评价和自由创作。
- 全局、项目、故事三层生成规则和提示词选项。
- 资料导入、长篇切分、结构化提取、待审核队列、自动审核、实体卡和资料包。
- 可恢复的 Brave Search 网络研究任务，覆盖模型规划、分角色并行搜索、安全抓取、事实提取、交叉验证、质量评测和人工审核。
- 词法、语义和混合检索；世界线、来源权威、反馈和冲突裁决参与排序。
- 固定 RAG 评测用例，支持 Recall@K、MRR、nDCG@K 和零召回统计。
- 基于内容哈希的增量向量重建，正常情况下只生成变化片段；不可复用的异常向量按片段重生成，模型或向量维度变化时切换为完整重建。
- SQLite 持久资料与网络研究任务，支持后台执行、租约、心跳、重启接管、暂停、继续、取消、失败项重试、估算和归档。
- SQLite 作为结构化数据权威来源，Markdown/TXT 继续保存长文本资产。

当前边界：

- 后台资料任务是应用进程内 worker，不是独立系统服务。关闭浏览器页面不影响任务；停止 NovelForge 进程会中断执行，重新启动应用后由租约恢复机制继续。
- 尚未实现跨机器分布式 worker，也不会强制终止正在进行的第三方模型 HTTP 请求。
- GraphRAG 表结构已经预留，但图谱构建与图扩展检索尚未成为正式工作流。
- EPUB、DOCX、PDF 和目录批量导入尚未作为稳定入口提供。
- 网络研究只支持公开静态文本页面；不执行 JavaScript、不登录网站、不绕过付费墙。LangGraph 只负责单次搜索步骤内的并行分派，SQLite 始终负责持久恢复。

## 总体架构

```text
app.py / launcher.py
        |
        v
ui/*  页面与交互组件
        |
        +--------------------+
        v                    v
novelforge/workflows/*   novelforge/services/*
        |                    |
        v                    v
novelforge/domain/*      storage/repositories/*
        |                    |
        +---------+----------+
                  v
          novelforge/core/*
                  |
                  v
       SQLite + Markdown/TXT assets
```

依赖方向遵循以下约束：

```text
ui -> workflows / services
workflows -> domain / services / core
services -> domain / core / storage
domain -> core（仅在需要共享模型时）
storage -> Python 标准库
```

- `core` 不导入 UI、业务工作流或存储实现。
- `domain` 不依赖 Streamlit、SQLite 连接或后台线程。
- `storage/repositories` 只封装 SQL、事务内原子操作和行映射，不编排业务流程。
- `ui` 只调用公开门面或工作流，不直接导入 `memory.*`、`retrieval.*` 等实现切片。
- `app.py` 只负责应用初始化、路由和依赖装配，不承载复杂业务逻辑。

## 目录与模块职责

```text
novelforge/
├── app.py                         # Streamlit 入口与路由
├── launcher.py                    # Windows 便携版启动器
├── novelforge/
│   ├── core/                      # LLM 客户端、schema、prompt、通用原语
│   ├── domain/                    # 纯领域规则和状态转换
│   ├── services/                  # 持久化门面、资源管理和检索服务
│   └── workflows/                 # 多步骤应用流程与后台任务编排
├── storage/
│   ├── db.py                      # 连接、事务、PRAGMA 和数据库健康检查
│   ├── schema.py                  # schema 版本与迁移入口
│   ├── migrations/                # 连续、不可变的 SQL 迁移
│   └── repositories/              # 按数据域拆分的 SQL 仓储
├── ui/                            # Streamlit 页面和可复用展示组件
├── tools/                         # 检查、迁移和回归验证脚本
├── docs/releases/                 # 不可变的发布历史
├── README.md
├── README.en.md
├── project.md
└── storage_architecture.md
```

### 稳定门面

以下包保留稳定公开入口，调用方不应绕过门面访问其内部切片：

- `novelforge.services.memory`：项目、故事、知识、来源、资产和运行记录持久化。
- `novelforge.services.retrieval`：文档收集、切分、索引、向量、搜索、重排和来源导入。
- `novelforge.services.web_research`：搜索 Provider、安全公开网页抓取和批量资料导入。
- `novelforge.workflows.skills`：讨论、生成、审阅、分析和可恢复流水线能力。

门面文件负责公开 API 和兼容性，不应重新累积完整实现。新增职责优先创建小型实现模块，再由门面导出。
项目运行记录的“只打开既有数据库”、故障恢复和目录生命周期围栏集中在
`novelforge/services/memory/runtime_storage.py`；它不得在调度器持有旧项目名时重建目录或空数据库。

### 模型用量与费用可观测性

模型调用可观测性采用“核心标准化 + 全局追加账本 + 工作流上下文归因 + 分层 UI”结构：

- `novelforge/core/llm_usage.py` 识别供应商，统一 DeepSeek/OpenAI/OpenRouter 等 usage 字段，在缺失 usage 时做明确标记的 Token 估算，并按事件价格快照计算费用。
- `novelforge/core/cost_currency.py` 统一价格币种、人民币主显示和 USD/CNY 换算。模型方案可用人民币或美元录入单价；DeepSeek 预设使用官方人民币价格，账本仍标准化为微美元以兼容既有历史与其他供应商。
- `novelforge/core/llm.py` 是聊天、流式响应和 Embedding 的唯一采集边界。流式请求申请末尾 usage 分片；不支持该参数的兼容接口会安全重试。
- `novelforge/services/llm_usage.py` 与 `storage/repositories/llm_usage.py` 负责全局账本、日期聚合、模型/操作/Agent 拆分和显式范围清理。
- `llm_usage_scope` 通过 `ContextVar` 传递项目、故事、任务、操作和 Agent 角色。子 Agent 可以细化角色与操作，但继承同一任务和界面操作 ID。
- `ui/llm_usage.py` 提供侧边栏今日/月度摘要、单次操作汇总、项目级与全局明细。UI 不使用悬浮窗，避免长期写作时遮挡正文。

费用可信度按三档展示：供应商直接返回费用、按用户价格快照估算、仅 Token/未计价。任何缺少价格的调用都不能显示为零费用。人民币默认主显示、美元作为核对值；价格币种、换算系数、核对日期和来源随事件快照保存。账本默认长期保留，只记录计量和归因元数据，不记录 prompt 或响应正文。

执行前预估复用同一价格和归因语义，但不向用量账本写入虚假调用：

- `novelforge/core/token_estimation.py` 提供无供应商依赖的中英文混合文本估算，供上下文装配、缺失 usage 回退和执行前预估共用。
- `novelforge/domain/llm_preflight.py` 是纯领域层，统一调用阶段、低/预期/高 Token 区间、费用区间、置信度、价格缺失说明和预算状态。
- `novelforge/services/llm_estimation.py` 从全局账本读取同方案、同模型、同操作和同 Agent 的精确样本；至少 5 条后使用 P50/P90 校准模板，但历史查询失败不得阻断业务 UI。
- `ui/llm_preflight.py` 是统一展示与确认组件。阈值按主显示币种和预估上界判断；缺少必要价格时只显示 Token；缓存命中在执行前未知，因此费用按普通输入价格保守估算。
- 长资料导入、自动网络研究和自由创作已经接入。网络研究按 Planner、Extractor、Verifier 分阶段汇总，并把搜索 API、网页抓取等非 Token 调用列为未计入金额的外部项；抓取原文先留在隔离区，人工激活时才生成向量，因此激活阶段的 Embedding 不计入研究任务创建预估。

预估不是账单，也不承诺模型一定生成到某个长度。输入在提示词已组装时通常更稳定；输出和未知网页正文必须保留较宽区间。持久任务在创建时保存完整估算与价格快照，后续价格修改不能重写该任务的历史判断依据。

### 网络研究与多 Agent 边界

当前用户可用链路：

```text
资料导入 / 网络检索 / 自动研究 Agent
  -> LLM Planner（可关闭，回退为确定性计划）
  -> LangGraph Collectors: official | secondary | community | fanon
  -> URL 去重、来源角色与域名多样性选择
  -> Safe Fetch + 隔离区来源资产
  -> Extractor + 原文引文硬校验
  -> Verifier + 来源评级 + 冲突聚合
  -> 覆盖率、重复率、多样性、佐证率和冲突率评测
  -> Human Review
  -> Pending Knowledge + Evidence
  -> 用户明确启用后，网页原文进入 Retrieval
```

`novelforge.services.web_research` 包含搜索、抓取和导入三个实现切片。抓取器只允许 HTTP/HTTPS，不携带 Cookie 或登录凭据，逐次校验重定向目标，拒绝本机、内网和保留地址，并把实际连接固定到本次重新解析且已校验的公网 IP；HTTPS 仍使用原主机名完成 SNI 与证书校验。响应类型、大小和重定向次数均有上限。来源文件名同时绑定 `research_task_id` 与最终 URL，同一网页在不同任务中不会共享隔离、启用或删除状态。自动抓取的原文以 `retrieval_status=quarantine` 保存，未获用户明确启用时，`documents.py` 不会把它收集为检索文档。

`novelforge/workflows/web_research_graph.py` 是进程内 LangGraph 搜索子图，提供按来源角色并行的 Collector，以及跨分支 URL 去重与来源角色聚合。它刻意不配置 LangGraph checkpointer：`workflow_runs/workflow_steps` 是运行状态、租约、重试、暂停和恢复的唯一权威；LangGraph 只负责一次已领取搜索步骤内部的并行编排，结果随后回写 SQLite。

持久研究任务包含六个阶段：

```text
plan -> search -> fetch -> extract -> verify -> evaluate
```

`novelforge/domain/web_research_tasks.py` 定义纯状态转换和阶段失效规则；`storage/repositories/durable_tasks.py` 提供通用租约、心跳、控制和归档；`novelforge/services/memory/web_research_tasks.py` 是 DB 门面；`novelforge/workflows/web_research_tasks.py` 编排恢复与阶段检查点；`web_research_agents.py` 实现 Planner、来源评估、Extractor 和 Verifier；`web_research_evaluation.py` 计算研究指标并转换待审核知识；`ui/web_research_tasks.py` 提供任务控制、证据预览和逐条送审。

网页正文始终作为不可信数据传给 Extractor/Verifier，系统提示明确拒绝执行正文中的指令。模型提取的主张正文和引文都必须在持久网页正文中定位，否则候选被剔除；名称不在原文时会回退为已定位的主张文本。Verifier 只能引用已有 `claim_id`，其模型输出的摘要和详情不会直接成为结论；确定性校验层只在相同来源角色、分类和原文主张内合并支持证据，并限制冲突证据的来源角色与主体。只有重定向后的最终 HTTPS URL 命中用户显式提供的官方域名白名单才会评为 `official`。激活后的网页进入 RAG 时仍包裹 `UNTRUSTED_WEB_SOURCE` 边界。结论默认只进入待审核知识，不能由研究任务直接写入正式知识。

### 资料工作台

| 模块 | 职责 |
|---|---|
| `novelforge/domain/ingestion_workbench.py` | 汇总批次状态、风险和推荐下一步 |
| `novelforge/domain/ingestion_tasks.py` | 任务/分段状态规范化、转换和检查点对账 |
| `novelforge/domain/ingestion_task_estimates.py` | 调用数、Token 和费用的纯计算估算 |
| `novelforge/domain/llm_preflight.py` | 通用阶段、区间、费用、置信度和预算纯计算模型 |
| `novelforge/services/llm_estimation.py` | 当前模型价格装配与历史 P50/P90 校准 |
| `novelforge/workflows/source_workflows.py` | 资料导入、提取、审核和批次原子操作 |
| `novelforge/workflows/long_reference_quick_process.py` | 可恢复的导入/提取/整理/自动审核阶段编排 |
| `novelforge/workflows/ingestion_tasks.py` | 持久任务创建、控制、恢复和执行 |
| `novelforge/workflows/ingestion_task_results.py` | 从任务与批次检查点重建跨重启的完整结果汇总 |
| `novelforge/workflows/ingestion_task_dispatcher.py` | 进程内调度、领取、心跳和失联接管 |
| `novelforge/services/memory/ingestion_tasks.py` | 任务领域对象与 SQLite 行之间的服务门面 |
| `storage/repositories/ingestion_tasks.py` | 任务快照、同批次唯一性、worker fencing 和终态提交 |
| `storage/repositories/ingestion_task_leases.py` | 原子领取、租约接管和心跳续期 SQL |
| `storage/repositories/ingestion_task_controls.py` | 暂停/继续/取消、归档和历史清理 SQL |
| `storage/repositories/ingestion_batch_mutations.py` | 批次保存/删除的原子占用、版本和 worker 权限围栏 |
| `ui/ingestion_batch_guard.py` | 导入向导与批次管理共用的冲突预检和任务中心入口 |
| `ui/ingestion_tasks.py` | 任务筛选、进度、控制和历史管理 |
| `ui/ingestion_task_estimate.py` | 导入入口共用的执行前估算展示 |
| `ui/llm_preflight.py` | 写作、资料和研究入口共用的执行前区间展示与预算确认 |

### 检索

`novelforge.services.retrieval` 按职责拆为：

- `documents.py`：从项目、故事、知识、资料和创作产物收集检索文档。
- `common.py`：公共模型、分词、通用切分和检索配置。
- `index.py`：文档切分、manifest 构建、增量向量生成和健康检查。
- `search.py`：查询扩展、作用域过滤、词法/语义评分、反馈、重排和多样化。
- `sources.py`：外部资料保存与整理。

当前检索流程：

```text
项目与资料变更
  -> 收集 RetrievalDocument
  -> 按内容类型切分 RetrievalChunk
  -> 写入 SQLite manifest/chunks
  -> 按内容哈希复用或生成 embedding
  -> 查询扩展与 story/worldline/source 过滤
  -> 词法/语义候选评分
  -> 权威、反馈、冲突和多样化重排
  -> 预算裁剪与证据格式化
```

`retrieval_chunks_fts` 已在 schema 中预留，但当前词法检索仍主要由应用层分词和评分完成，不能把 FTS 表的存在表述为已经完成的 FTS 查询后端。

### 统一上下文装配

`novelforge/workflows/context_assembly.py` 为大纲、规划、正文、自由创作和审阅提供同一套上下文装配：

1. 全局、项目和故事规则。
2. 核心设定与创作配置。
3. 项目、故事、章节和单次运行 context directive（界面称“创作提醒”）。
4. 任务感知检索证据。
5. 提示词选项和本次临时参数。
6. 预算裁剪、遗漏说明和上下文指纹。

正式保存的生成结果应同时保存上下文快照；`once` 范围的创作提醒只在保存成功后消费。

## 持久资料任务契约

### 生命周期

任务状态：

```text
queued -> running -> completed
                  -> completed_with_errors
                  -> failed
                  -> paused -> queued
                  -> cancelled
```

- `queued`：可以由 worker 领取。
- `running`：必须关联 worker 和有效租约。
- `paused`：不会被调度，继续后回到 `queued`。
- `failed`：保留检查点，继续后只处理未完成片段。
- `completed_with_errors`：整体已结束但存在失败片段，可只重试失败项。
- `completed`、`cancelled`：终态，可归档。

分段状态为 `queued/running/completed/failed/cancelled/skipped`。任务还持久化 `import/extraction/consolidation/auto_confirm` 四个阶段游标。任务恢复前必须与长篇资料批次的已落盘状态对账，已成功片段和已完成阶段不得重复调用模型；仅导入失败时不得重复执行知识提取。

### 并发与恢复

- SQLite `BEGIN IMMEDIATE` 串行化任务领取、同批次任务创建和终态提交。
- `status=running + worker_id + 未过期 lease_expires_at` 共同决定任务所有权，独立心跳线程续租。
- worker 检查点带 fencing；终态快照和清理租约在同一事务完成，旧 worker 不能覆盖接管者。
- 多个浏览器窗口或多个应用实例可以竞争，但同一任务同时只有一个有效 owner，同一批次同时只有一个未完成任务。
- 批次保存、删除和任务创建使用同一 SQLite 写锁串行；任务创建校验批次版本与所选片段，人工写入不能越过已占用批次。
- 运行中任务写回批次必须同时匹配 `task_id`、`worker_id` 和有效租约；DB 提交成功后才尽力同步非权威 JSON 镜像。
- 租约过期的 `running` 任务可被新 worker 接管。
- 调度器按项目 round-robin 轮询，避免首个项目持续有任务时饿死其它项目。
- 暂停和取消在片段/阶段检查点生效，不强杀正在进行的模型 HTTP 请求。
- 已全部落盘后才到达的暂停/取消请求按真实结果记为完成；较早的控制请求保留可恢复检查点和结果汇总。
- 提取、整理和自动审核按依赖顺序执行；恢复时复用阶段计数，失败重试会使必要的下游阶段重新进入待处理。
- 项目重命名或删除使用持久维护锁阻止任务创建、重新入队和领取，并拒绝移动仍有 queued/running 任务的目录；旧项目名的调度快照只允许打开既有数据库，不能重建已移动目录。
- 估算使用任务创建时的模型、费率和选项快照；它是预算参考，不是供应商账单。

### 运行边界

调度器是 Streamlit 应用进程中的 daemon thread。关闭页面、刷新页面或切换页面不会停止任务；关闭启动器、结束 Python 进程或系统休眠可能中断当前调用。应用重启后，任务会在旧租约过期并完成批次对账后继续。

## 存储与一致性

- 全局结构化配置写入 `data/global.db`。
- 项目和故事结构化数据写入 `data/projects/{project_name}/project.db`。
- Markdown/TXT 等长文本继续保存在项目目录，并由 `asset_files` 登记路径、hash、作用域和生命周期。
- 结构化 JSON 默认不再写入；旧 JSON 仅作为兼容导入来源。详细规则见 [storage_architecture.md](./storage_architecture.md)。
- 任何影响检索的保存或删除操作都必须同步检索资产，或在代码中明确说明无需同步的原因。
- 删除结构化记录优先使用 repository 的软删除/级联语义，不能只删除文件镜像。

## UI 信息架构

当前侧边栏按使用场景组织：

- `工作台`：项目总览、项目资源。
- `资料`：资料导入、核心设定、检索中心。
- `规划`：创作配置，以及按故事配置展开的大纲、分卷、剧情段和细纲。
- `写作`：自由创作、正文生成、章节评价。
- `配置`：模型配置、生成规则、提示词选项。

资料导入页内部工作区为：资料任务、资料来源、待审核设定、处理记录、长篇批次、知识整理和资料包。复杂面板只渲染当前选中的工作区，状态键必须按项目/故事作用域隔离。

## 开发规则

1. Windows 下运行项目 Python 命令时使用 `.\.venv\Scripts\python.exe`，不要假设裸 `python` 指向项目环境。
2. 根目录只保留 `app.py` 和 `launcher.py` 两个 Python 运行入口；业务模块进入 `novelforge/`、`storage/` 或 `ui/`。
3. 新共享模型和 prompt 原语放入 `novelforge/core/`。
4. 无 IO 的业务规则和状态转换放入 `novelforge/domain/`。
5. 持久化与检索能力放入 `novelforge/services/`，SQL 放入 `storage/repositories/`。
6. 多步骤生成、恢复或任务编排放入 `novelforge/workflows/`。
7. Streamlit 页面只做输入、展示和调用编排，不保存领域规则。
8. 新结构化 LLM 输出先在 `novelforge/core/schemas.py` 定义并校验；空响应必须显式报错。
9. 不静默吞掉异常；至少记录警告，并向上层返回可判断的失败状态。
10. 所有用户输入参与路径构造前必须做路径穿越检查。
11. 新字段必须有兼容默认值；数据库变更必须新增连续 migration，不修改已发布迁移。
12. 项目或故事相关的 Streamlit state 必须使用 scoped key，防止切换上下文后串数据。
13. 生成产物应可持久化；预览模式不得写入正式章节、讨论、索引或运行记录。
14. 新增顶层包或发布必需文件时同步更新 `build_release.ps1` 和包结构验证。

### 文件体量与耦合控制

- 新文件优先控制在约 600 行以内；超过约 800 行时应在评审中说明为何不能按职责拆分。
- UI 页面把可复用视图、状态转换和领域计算分别下沉到 UI helper、domain 或 workflow。
- 门面只负责导出与兼容，不复制实现。
- 不为减少行数制造循环依赖；拆分顺序以职责和依赖方向为准。
- `tools/verify_package_structure.py` 中的 2200 行限制是防止继续失控的过渡硬上限，不是推荐文件大小。

## 验证入口

高风险改动应按影响范围选择验证，不能只运行新增脚本：

```powershell
# 包边界与 UI
.\.venv\Scripts\python.exe tools\verify_package_structure.py
.\.venv\Scripts\python.exe tools\verify_ui_consistency.py

# DB-first 存储
.\.venv\Scripts\python.exe tools\verify_db_storage.py

# 资料任务与工作台
.\.venv\Scripts\python.exe tools\verify_ingestion_tasks.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_runtime.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_hardening.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_recovery.py
.\.venv\Scripts\python.exe tools\verify_ingestion_batch_mutation_guard.py
.\.venv\Scripts\python.exe tools\verify_ingestion_workbench.py

# 检索质量
.\.venv\Scripts\python.exe tools\verify_retrieval_quality.py
.\.venv\Scripts\python.exe tools\verify_retrieval_hardening.py
.\.venv\Scripts\python.exe tools\verify_vector_metadata_persistence.py

# 网络检索与研究子图（离线 Mock，不调用真实搜索服务）
.\.venv\Scripts\python.exe tools\verify_web_research.py
.\.venv\Scripts\python.exe tools\verify_web_research_tasks.py

# 应用导入冒烟
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
```

运行验证产生的 `_verify_*` 或临时项目只能由对应脚本清理，不得对真实 `data/projects/` 使用通配删除。

## 下一阶段优先级

### P0：RAG 与资料导入

1. 父子级切分：子片段负责召回，按预算补充章节/场景/资料卡父上下文和相邻片段。
2. 类型专用切分器：分别处理小说正文、角色卡、关系、时间线、世界规则和文风资料。
3. 多路查询规划：把角色、关系、时间线、硬约束、章节进度和文风拆成受配额控制的子查询。
4. 稳定排名融合：用 RRF 或等价方法融合词法/语义排名，避免直接叠加不同量纲的原始分数。
5. 证据闭环：将反馈绑定到稳定内容指纹或来源级信号，并保存来源修订、片段范围和索引版本。
6. 格式扩展：在可预览、可修正解析结果的前提下支持 EPUB、DOCX、可提取文本 PDF 和目录批量导入。

### P1：可维护性与操作体验

1. 拆分当前超过约 1000 行且职责混杂的 memory、UI、prompt 和 source workflow 模块。
2. 抽取大纲/分卷/剧情段/章节讨论页的重复交互骨架。
3. 为资料任务增加真实调用用量记录，与创建时估算并列展示。
4. 给后台任务增加更明确的应用关闭提示、失败通知和运行日志入口。

### P2：规模化与编排

1. 只有在实际项目规模证明 SQLite 向量扫描成为瓶颈后，再评估专用向量后端。
2. 需要脱离 UI 进程长期运行时，再引入独立 worker 进程或系统服务。
3. LangGraph 只扩展单次研究任务内部的多角色编排；当前已提供逐任务覆盖率、重复率、来源多样性、佐证率和冲突率，后续在有稳定真实数据集时再增加跨版本基准与反思搜索。
4. 图谱层应作为检索证据扩展器，不替代现有 chunk retrieval。

## 已知技术债

| 领域 | 当前问题 | 处理方向 |
|---|---|---|
| 模块体量 | `memory/core.py`、部分 memory/UI/prompt/source 模块仍超过 1000 行 | 按资产、配置、故事、资料和展示职责继续拆分 |
| UI 复用 | 多类讨论页仍有相似布局、表单解析和保存操作 | 抽取共享讨论 renderer 和动作 helper |
| 检索融合 | hybrid 仍直接组合词法分数与缩放后的语义分数 | 引入排名级融合并用固定评测集验收 |
| 切分 | 当前按 Markdown、段落或长度切分，缺少父子上下文 | 建立类型感知、可追溯的层级切分模型 |
| FTS | FTS5 表已创建但未成为当前词法查询后端 | 在规模数据基准下决定接入或移除预留 |
| 兼容层 | DB-first 已完成，但仍保留旧 JSON 导入和可选镜像代码 | 等兼容窗口结束后分阶段收缩 |
| 任务运行时 | worker 与应用进程同生命周期 | 只有明确需要常驻执行时再独立进程化 |
| 网络研究 | 当前只抓取公开静态文本，搜索 Provider 为 Brave Search | 根据真实失败样本评估动态渲染抓取和更多 Provider；不以绕过登录或反爬为目标 |
| 启动器 | Windows 支持完整，Linux/macOS 主要回退到当前解释器 | 增加跨平台运行时发现和发布验证 |

## 修改前检查顺序

1. 阅读本文件和 [storage_architecture.md](./storage_architecture.md)。
2. 阅读与需求直接相关的 `ui/` 页面。
3. 沿调用方向检查对应 workflow、domain、service 和 repository。
4. 搜索公开门面的导出与现有 `tools/verify_*.py` 覆盖。
5. 实现后同步更新用户行为、架构或 schema 对应的永久文档。
