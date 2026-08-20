# NovelForge Vue 前端迁移实施规划

> 文档用途：本文件是 NovelForge 从 Streamlit 迁移到 Vue 前端的实施路线图。它负责固定目标架构、双创作界面边界、API 契约、任务顺序、验收门槛、回滚策略和最终下线条件。
>
> 当前基线：仓库版本 `v0.7.1`，SQLite schema version `16`，Streamlit 四入口 UI 已完成基础精简；Vue/FastAPI 第一条垂直链路已可运行。

> 本轮执行收口：Vue/FastAPI 双工作台核心链路、故事模式、规划结构/章节编辑、对话流式/动作/附件、多文件资料批量导入、共享知识/任务/能力工作区、类型化知识修订/证据、用量检查器、launcher 默认 Vue 与回退已落地；2026-08-20 已用自包含 Windows runtime 重建便携包并完成包内 FastAPI/Vue API 冒烟。真实模型断线/IME、超大数据压力、OCR/provider 评测和干净机 launcher 矩阵仍按下方阶段门保留，不能伪造完成。
>
> 当前状态：阶段 0、1、2、3、5/6 的主要能力和阶段 4 对话链路已实施；阶段 4.8、7.4/7.5、8.1/8.2 的真实环境证据，以及最终 Streamlit 下线条件仍在执行中。任务状态以各节标记和 [vue_frontend_migration_baseline.md](vue_frontend_migration_baseline.md) 为准。
>
> 事实源：当前工程事实以 [project.md](../project.md) 为准，存储事实以 [storage_architecture.md](../storage_architecture.md) 为准；本文件描述目标状态和迁移过程，不能被用来覆盖当前事实。

## 0. 如何使用本规划

迁移必须按任务编号逐项实施。禁止把“迁移到 Vue”作为一个不可回退的大提交，也禁止在建立 API 边界之前直接把 Python UI 逻辑翻译成 Vue 代码。

执行单个任务前，实施者必须：

1. 完整阅读 `project.md`、`storage_architecture.md` 和本文件。
2. 阅读任务直接引用的当前 Streamlit 页面、workflow、service 和 repository。
3. 运行 `git status --short`，保留用户已有改动，不覆盖无关文件。
4. 确认前置任务全部完成；未完成时停止，不跳步补做未来任务。
5. 只修改当前任务授权范围；相邻问题记录在交付说明中。
6. 所有源码修改使用 `apply_patch`；格式化和生成锁文件可使用对应工具。
7. 运行该任务要求的 Python、TypeScript、契约或端到端验证。
8. 不调用真实付费模型、真实搜索服务或真实用户项目完成自动化验收。
9. 未经用户明确要求，不提交、不推送、不删除 Streamlit 回退入口。
10. 每完成一个任务，只更新该任务状态、实际改动和验证结果，不重写尚未执行的规划。

推荐一次只交付一个任务；同一阶段内只有明确标注可并行的任务才能并行开发。任何 schema、启动器、发布脚本或权威存储变更必须独立提交并可独立回退。

## 1. 迁移结论

NovelForge 的目标不是“用 Vue 重新画现有四个 Streamlit Hub”，而是：

```text
一个 Python 业务核心
一个 SQLite + 文件资产存储体系
一个版本化本地 API
两个独立的 Vue 创作界面
```

两个创作界面分别为：

- **规划创作界面**：面向长篇、强结构和逐级讨论，包含创作方向、全书、分卷、剧情段、章节细纲、正文、审阅和证据检查。
- **对话创作界面**：面向轻量、低干扰创作，直接通过对话完成写作、续写、修改、资料查询、附件导入和自动知识沉淀，不展示规划流程。

它们必须是两个不同的路由树和顶层 Layout，而不是同一个 Layout 根据布尔值隐藏按钮。允许共享设计原语、API 客户端、资料编辑器和基础组件，但不得共享导航结构、页面层级和核心交互节奏。

### 1.1 明确采用的技术方向

- 前端：Vue 3、TypeScript、Vite、Vue Router、Pinia。
- 后端接口：FastAPI，继续运行现有 Python workflow/service/domain/storage。
- 普通命令与查询：JSON REST API。
- LLM Token 流和单向运行事件：Server-Sent Events（SSE）。
- 双向 WebSocket：当前不引入；只有未来出现真正的多人协作或客户端主动实时控制需求时再评估。
- 前端构建：Node.js 只在开发和发布构建时使用；便携版运行时不携带 Node.js。
- 本地部署：FastAPI 绑定 `127.0.0.1`，同时提供 API 与 Vue 构建产物。
- 当前不引入 Nuxt、SSR、Electron、Tauri、云端账户或多用户权限系统。

Vue 官方推荐用 `create-vue` 创建基于 Vite 的 SPA，并可选择 TypeScript、Router、Pinia、Vitest 和端到端测试：<https://vuejs.org/guide/quick-start.html>。本地应用不需要 SSR，因此直接使用 Vite，不引入额外全栈 Vue 框架。

### 1.2 不采用的方案

- 不维护两个代码仓库或两个 Python 后端。
- 不复制 SQLite 数据库、知识库、检索索引、附件库或模型配置。
- 不把 Streamlit 嵌入 Vue iframe。
- 不用 Streamlit Custom Component 承载整套新 UI；那会同时保留 Streamlit 重跑模型和前端桥接复杂度。
- 不让 Vue 直接访问 SQLite、文件系统路径或 keyring。
- 不把现有 Python `dict` 和 SQLite 行未经 DTO 校验直接暴露给前端。
- 不在迁移阶段顺便重写 Prompt、RAG、网络研究或后台任务状态机。
- 不把规划模式和对话模式做成一次浏览器会话内的临时开关。

## 2. 当前基线与迁移动因

### 2.1 当前 UI 规模

当前 `ui/` 约有 20,800 行 Python。体量较大的页面包括：

| 当前文件 | 当前职责 | 主要迁移问题 |
| --- | --- | --- |
| `ui/knowledge_management.py` | 知识、来源、审核和管理视图 | 页面、状态、表单和业务调用混合，超过 2,000 行 |
| `ui/long_reference_batch.py` | 长资料批次与任务操作 | 长页面、任务状态和控制操作高度耦合 |
| `ui/layout.py` | 全局 CSS 和展示原语 | 样式依赖 Streamlit DOM，不能可靠复用 |
| `ui/llm_settings.py` | 模型、能力、价格和连接测试 | 密钥交互和多种配置表单集中在单页 |
| `ui/long_reference_importer.py` | 多格式资料导入 | 上传、解析、预估、确认和任务创建耦合 |
| `ui/chapter_page.py` | 章节需求、正文和审阅 | 三阶段状态依赖 Streamlit rerun |
| `ui/free_writing/` | 会话、片段、附件、动作、知识和章节保存 | 已有合理模块切片，但交互仍被 widget 状态和 rerun 限制 |

Streamlit 官方执行模型会在每次交互时从头运行脚本，状态通过 Session State 在 rerun 之间保存：<https://docs.streamlit.io/develop/concepts/architecture/session-state>。这适合快速数据应用，但在以下需求上成本持续上升：

- 两个完全不同的应用壳层。
- 长时间保持的编辑草稿和复杂焦点状态。
- 流式正文、动作卡、附件进度和后台任务同时更新。
- 路由级深链接、浏览器前进/后退和可恢复页面定位。
- 大列表虚拟化、拖放、分栏、抽屉和细致响应式设计。
- 稳定视觉回归、组件测试和前端性能预算。

### 2.2 已存在且必须复用的能力

Vue 迁移不是功能重写。以下能力已经存在，应通过 API 暴露：

- 项目、多故事、故事复制与软删除。
- 创作方向、总纲、分卷、剧情段、章节细纲和正文资产。
- 自由创作会话、轮次、片段版本、接受、重写和分支。
- 对话消息和确定性动作协议。
- 对话附件、原文先检索、后台知识化和 OCR 状态。
- 正式知识、待审核知识、证据、修订、恢复和实体投影。
- FTS、词法、语义、RRF、反馈、冲突和检索评测。
- 长资料任务和网络研究任务的租约、心跳、恢复和控制。
- CapabilityRegistry、模型配置、凭据引用、自动配置和显式降级。
- LLM 预估、预算确认、Token/费用账本和操作归因。
- 统一上下文装配、上下文快照和一次性创作提醒。

### 2.3 现有文档关系

- `docs/ui_restructure_plan.md` 记录已经完成的 Streamlit 四入口精简，迁移开始后冻结为历史实施记录。
- `docs/conversational_creation_upgrade_plan.md` 记录已经实现的对话动作、附件、知识中心和自动配置底座，新对话 UI 必须复用这些能力。
- 本文件只负责 Vue/FastAPI 边界和双 UI 迁移，不重复定义底层知识或工作流。

## 3. 目标、不变量与非目标

### 3.1 产品目标

迁移完成后必须满足：

1. 新建故事时明确选择“规划创作”或“对话创作”。
2. 两种模式拥有不同的顶层 Layout、导航和默认交互。
3. 同一项目可以包含不同模式的故事，共享项目级资料和设置。
4. 切换故事时根据故事模式进入正确界面，不复用上一个故事的页面状态。
5. 切换模式不删除任何大纲、正文、会话、附件或知识。
6. 规划模式不显示“自由模式”标签；对话模式不显示大纲和章节规划入口。
7. 设置、资料和任务能力可以共享底层实现，但在两种 Layout 中以适合该模式的方式呈现。
8. 所有生成继续支持流式输出、费用预估、确认、错误恢复和用量归因。
9. 便携版仍由一个 Windows 启动器启动本地服务并自动打开浏览器。

### 3.2 工程不变量

整个迁移期间必须保持：

- SQLite 仍是结构化权威来源。
- Markdown/TXT 等文件资产及其 `asset_files` 登记语义不变。
- UI 和 API 不直接执行 SQL；SQL 只进入 `storage/repositories/`。
- API router 不承载业务流程，只校验 DTO、鉴权本地客户端、调用公开 workflow/service 并转换响应。
- domain 不依赖 FastAPI、Vue、HTTP 或前端 DTO。
- 已发布 migration 不修改；schema 变化只新增连续 migration。
- 后台任务的唯一持久权威仍是 `workflow_runs/workflow_steps`。
- LangGraph 不获得第二套持久状态。
- 任何用户输入参与路径解析前继续经过现有路径安全校验。
- API Key 不返回前端，不写入 SQLite 明文，不进入日志或 OpenAPI 示例。
- 生成预览与正式保存语义不合并。
- 普通模型正文不能直接执行持久知识或配置写入。
- 知识恢复继续追加新修订，不覆盖历史。
- 项目重命名、删除和任务维护锁语义不变。

### 3.3 本次非目标

- 不做云端部署和远程访问。
- 不做多人实时协作、账号、权限和同步。
- 不改用 PostgreSQL 或专用向量数据库。
- 不把后台 worker 独立成系统服务。
- 不在首次 Vue 发布中承诺完整手机端功能。
- 不在首次迁移中把 Markdown/TXT 权威正文转换为富文本数据库。
- 不默认启用远程字体、CDN 脚本或联网分析。
- 不追求 Streamlit DOM 与 Vue 页面逐像素相同。

## 4. 目标总体架构

```text
launcher.py
    |
    v
FastAPI / Uvicorn（仅 127.0.0.1）
    |
    +--------------------------+
    |                          |
    v                          v
Vue 静态资源               /api/v1/* + /api/v1/events/*
    |                          |
    v                          v
两个 Vue Layout          novelforge/api/*
    |                          |
    +--------------------------+
                               v
                    workflows / services
                               |
                    domain / core / storage
                               |
                    SQLite + Markdown/TXT
```

### 4.1 Python 目标目录

建议新增：

```text
novelforge/api/
├── __init__.py
├── app.py                     # FastAPI 应用工厂
├── lifespan.py                # 调度器启动、知识索引 prime 和关闭处理
├── dependencies.py            # 项目/故事解析、本地客户端校验、开发者模式
├── errors.py                  # 稳定错误码与异常映射
├── middleware.py              # request_id、安全头、日志与耗时
├── static.py                  # Vue dist 与 SPA fallback
├── schemas/
│   ├── common.py
│   ├── projects.py
│   ├── creation.py
│   ├── knowledge.py
│   ├── tasks.py
│   ├── settings.py
│   └── usage.py
├── routers/
│   ├── system.py
│   ├── projects.py
│   ├── stories.py
│   ├── planned_creation.py
│   ├── conversational_creation.py
│   ├── knowledge.py
│   ├── sources.py
│   ├── tasks.py
│   ├── settings.py
│   ├── usage.py
│   └── developer.py
└── streaming/
    ├── events.py
    ├── registry.py
    └── sse.py
```

约束：

- `schemas/` 是 HTTP DTO，不替代 `novelforge/core/schemas.py` 的 LLM 结构化输出模型。
- router 只调用稳定门面；若现有 UI 使用私有函数，先为 service/workflow 增加公开应用接口。
- 不让 router 导入 `storage.repositories`。
- 不在 router 中复制 Streamlit 页面里的计算、确认或状态转换。
- API 应用工厂必须允许测试注入临时 data root、假模型客户端和禁用后台线程。

### 4.2 Vue 目标目录

建议新增：

```text
frontend/
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── playwright.config.ts
├── index.html
├── public/
└── src/
    ├── main.ts
    ├── app/
    │   ├── App.vue
    │   ├── router.ts
    │   ├── bootstrap.ts
    │   └── error-boundary.ts
    ├── api/
    │   ├── client.ts
    │   ├── errors.ts
    │   ├── sse.ts
    │   └── generated/
    ├── layouts/
    │   ├── PlannedAppLayout.vue
    │   ├── ConversationalAppLayout.vue
    │   ├── PlannedLibraryLayout.vue
    │   └── ConversationalUtilityLayout.vue
    ├── routes/
    │   ├── start/
    │   ├── planned/
    │   ├── conversation/
    │   ├── library/
    │   └── settings/
    ├── features/
    │   ├── projects/
    │   ├── stories/
    │   ├── planned-creation/
    │   ├── conversation/
    │   ├── knowledge/
    │   ├── sources/
    │   ├── tasks/
    │   ├── settings/
    │   ├── usage/
    │   └── developer/
    ├── components/
    │   ├── primitives/
    │   ├── feedback/
    │   ├── forms/
    │   ├── editor/
    │   └── operation/
    ├── stores/
    │   ├── app.ts
    │   ├── project.ts
    │   ├── story.ts
    │   ├── operation.ts
    │   └── preferences.ts
    ├── composables/
    ├── styles/
    │   ├── tokens.css
    │   ├── reset.css
    │   ├── planned-theme.css
    │   ├── conversational-theme.css
    │   └── utilities.css
    ├── types/
    └── test/
```

目录约束：

- feature 页面不得直接使用裸 `fetch`，统一经过 `src/api/client.ts`。
- Pinia 保存客户端会话状态，不把整个数据库复制成长期全局 store。
- 服务器列表、详情和分页数据使用可失效的 server-state cache；具体库在 `VF-0.3` ADR 中锁定。
- Layout 只负责布局、导航和全局状态，不包含生成、保存或知识审核业务逻辑。
- 两个创作 Layout 不互相 import 页面组件；只允许依赖共享 primitives 和 feature-level 无布局组件。
- 单个 `.vue` 文件优先控制在 400 行以内；超过 600 行必须拆分或说明原因。

### 4.3 运行时依赖方向

```text
Vue route -> feature composable -> typed API client
FastAPI router -> application workflow/service facade
workflow -> domain/service/core
service -> domain/core/storage
storage repository -> sqlite3
```

禁止方向：

- Vue -> SQLite/本地路径/keyring。
- FastAPI router -> Streamlit UI。
- domain -> FastAPI/Pydantic HTTP DTO。
- repository -> API schema。
- Vue Layout -> Python 兼容镜像。

## 5. 两套 UI 的产品规格

### 5.1 模式作用域与进入规则

模式属于故事，不属于整个应用，也不属于浏览器会话：

```text
creation_mode = planned | conversational
```

进入规则：

1. 项目列表不决定创作模式。
2. 选择故事后，router 根据故事 `creation_mode` 进入对应 Layout。
3. URL 与故事模式不一致时，route guard 使用 `replace` 重定向，不渲染错误 Layout。
4. 新故事创建时必须选择模式。
5. 复制故事默认继承来源故事模式，并允许创建前修改。
6. 旧故事迁移后默认 `planned`，确保现有规划功能不消失。
7. 对“没有规划资产但已有 creative session”的旧故事，只显示一次“是否改为对话创作”的建议，不自动修改。
8. 模式切换入口放在故事设置中，使用明确动作“更换创作方式”，不放在顶栏做随手 Toggle。
9. 切换模式不删除、不移动、不重写任何业务资产。

### 5.2 规划创作界面

视觉方向：编辑部式、信息密度高但安静，强调作品结构、当前阶段和证据，不采用后台管理系统式大卡片堆叠。

建议布局：

```text
┌─────────────────────────────────────────────────────────────┐
│ 项目 / 故事 / 同步状态 / 任务 / 用量 / 设置                 │
├──────────────┬────────────────────────────┬─────────────────┤
│ 作品结构树   │ 主工作区                   │ 上下文检查器    │
│              │                            │                 │
│ 创作方向     │ 当前大纲、讨论或正文       │ 设定、证据      │
│ 全书         │ 编辑器 / 生成结果 / Diff   │ 创作提醒        │
│ 分卷         │                            │ 检索来源        │
│ 剧情段       │                            │ Agent 状态      │
│ 章节         │                            │                 │
├──────────────┴────────────────────────────┴─────────────────┤
│ 当前操作、费用预估、流式状态、保存状态                      │
└─────────────────────────────────────────────────────────────┘
```

核心规则：

- 左侧结构树是真正的作品导航，不是 Streamlit 四 Hub 的复制。
- 中间工作区一次只聚焦一个资产或一个阶段。
- 讨论、生成和人工编辑在同一资产上下文内完成，不跳到独立聊天页。
- 右侧检查器按需显示规则、优先设定、检索证据、上下文遗漏和用量。
- 主操作始终唯一；历史、Prompt 选项、上下文快照和技术细节进入次级抽屉。
- 长文本编辑区必须处理中文输入法组合、撤销、查找、草稿恢复和大文本性能。
- “自由模式”不再作为规划 Layout 中的标签存在。

规划路由建议：

```text
/projects/:projectId/stories/:storyId/planned/direction
/projects/:projectId/stories/:storyId/planned/outline
/projects/:projectId/stories/:storyId/planned/volumes/:volumeNo
/projects/:projectId/stories/:storyId/planned/arcs/:arcNo
/projects/:projectId/stories/:storyId/planned/chapters/:chapterNo/outline
/projects/:projectId/stories/:storyId/planned/chapters/:chapterNo/write
/projects/:projectId/stories/:storyId/planned/chapters/:chapterNo/review
```

### 5.3 对话创作界面

视觉方向：沉浸、低干扰、内容优先。默认只显示会话、正文和输入区；资料、记忆、动作和上下文是可收起的辅助层。

建议布局：

```text
┌─────────────────────────────────────────────────────────────┐
│ 故事名称 / 会话状态 / 模型能力 / 任务                        │
├──────────────┬────────────────────────────┬─────────────────┤
│ 会话列表     │ 对话与正文流               │ 记忆抽屉        │
│              │                            │                 │
│ 新对话       │ 用户命令                   │ 自动提取条目    │
│ 最近会话     │ 助手回复                   │ 当前附件        │
│ 已归档       │ 正文片段与版本             │ 相关资料        │
│              │ 动作卡与确认               │ 上下文摘要      │
├──────────────┴────────────────────────────┴─────────────────┤
│ 附件 / 命令 / 输入框 / 发送 / 当前预估                       │
└─────────────────────────────────────────────────────────────┘
```

核心规则：

- 进入故事后直接进入最近活动会话；没有会话时显示极简起始输入。
- 不显示总纲、分卷、剧情段、章节细纲或“下一步规划”。
- `write/revise/query/update/save` 等动作都通过同一输入区发起。
- 正文片段和普通助手消息保持不同视觉与数据语义。
- 自动提取默认写入会话记忆或待审核知识，不直接写正式知识。
- 自动提取只显示“本次记住了 N 条”的非阻塞反馈；用户可在右侧抽屉批量修正、忽略或提升。
- 附件托盘支持文件、粘贴文本、公开 URL 和已有资料，继续复用现有来源修订与资料任务。
- 模型生成时允许浏览历史和资料；切换会话不应丢失正在运行操作的状态。
- 发送快捷键必须正确处理中文输入法：组合输入期间 Enter 不能误提交。

对话路由建议：

```text
/projects/:projectId/stories/:storyId/chat
/projects/:projectId/stories/:storyId/chat/sessions/:sessionId
/projects/:projectId/stories/:storyId/chat/sessions/:sessionId/memory
/projects/:projectId/stories/:storyId/chat/sessions/:sessionId/attachments
```

`memory` 和 `attachments` 可以表现为抽屉状态，但仍应有可深链接 URL，支持刷新后恢复。

### 5.4 共享功能在两套 UI 中的呈现

“两套 UI”不等于复制所有功能代码：

| 功能 | 规划界面呈现 | 对话界面呈现 | 数据与 API |
| --- | --- | --- | --- |
| 项目/故事切换 | 顶栏 + 结构树 | 顶栏 + 会话侧栏 | 完全共享 |
| 资料搜索 | 独立资料工作区/右侧证据 | 记忆抽屉内轻搜索，可进入完整页 | 完全共享 |
| 模型设置 | 设置页 | 轻量状态入口进入设置页 | 完全共享 |
| 任务中心 | 全局抽屉 | 全局抽屉 | 完全共享 |
| 用量与费用 | 底部状态 + 明细页 | 输入区摘要 + 明细页 | 完全共享 |
| 知识编辑 | 完整编辑器 | 记忆卡进入相同编辑器 | 完全共享 |
| 开发工具 | 设置内完整页 | 设置内完整页 | 完全共享 |

共享功能可以由同一 feature 组件渲染，但必须允许两个 Layout 提供不同容器、密度和入口。禁止为了“代码复用”重新创造一个包含全部导航的超级 Layout。

## 6. 视觉系统与组件策略

Vue 只提供表达能力，不自动产生美观界面。迁移必须先建立视觉系统，再迁移功能。

### 6.1 设计 Token

`tokens.css` 至少定义：

- 语义颜色：canvas、surface、elevated、text、muted、border、accent、success、warning、danger、info。
- 两套主题覆盖：planned 和 conversational。
- 字体：UI、正文编辑、等宽诊断。
- 字号与行高：caption、body、body-lg、title、display。
- 间距：以 4px 为原子，常用 8/12/16/24/32。
- 圆角：输入、卡片、弹层分别定义，不允许页面随意硬编码。
- 阴影和边框。
- 动效时长与缓动，并支持 `prefers-reduced-motion`。
- z-index 层级：sticky、dropdown、drawer、modal、toast、command palette。
- 内容宽度：对话正文、规划编辑区、详情面板和全宽数据表。

首版不依赖在线字体。中文 UI 使用系统字体栈；正文编辑器提供无衬线/衬线本地字体偏好，但不改变资产内容。

### 6.2 组件层级

1. `primitives/`：Button、IconButton、Input、Select、Tabs、Dialog、Drawer、Tooltip、Popover、Menu、Badge、Progress、Skeleton。
2. `feedback/`：Toast、InlineError、EmptyState、CapabilityNotice、DegradedModeNotice。
3. `forms/`：Field、FieldError、DirtyGuard、ConfirmAction、ScopePicker。
4. `operation/`：PreflightCard、OperationProgress、StreamingStatus、UsageSummary、ActionReceipt。
5. `editor/`：PlainTextEditor、MarkdownPreview、DiffView、SourceQuote、AutosaveStatus。
6. feature 组件：只能依赖上述共享组件，不直接定义全局主题。

基础交互原语可采用可访问的 headless 组件库，但最终视觉必须由 NovelForge Token 控制。不得整体套用后台管理模板或未经调整的默认组件主题。

### 6.3 图标与视觉资产

- 使用同一 SVG 图标集，禁止混用 emoji、字体图标和多套线宽。
- 图标按钮必须有可访问名称和 Tooltip。
- 不使用远程 CDN 图标。
- 空状态插画不是首版必需；如果使用，作为本地可追踪资产并校验授权。

### 6.4 必须先验收的原型

在接入真实 API 前，必须用假数据完成并截图验收：

- 项目选择和新建故事模式选择。
- 规划 Layout 的方向、章节写作和右侧上下文检查器。
- 对话 Layout 的空会话、流式生成、动作确认、附件处理中和记忆抽屉。
- 资料搜索主从视图。
- 模型缺失、Embedding 降级、任务失败、无数据和长文本溢出。
- 1440×900、1280×800、1024×768 和 768×1024 四种视口。

原型验收后才允许大规模迁移页面；否则会把旧信息架构直接固化进新技术栈。

## 7. 路由、状态与草稿

### 7.1 URL 是页面定位事实源

以下状态必须进入 URL，而不是只存在 Pinia：

- projectId、storyId、creation mode route。
- 规划资产类型与 volume/arc/chapter 编号。
- conversation sessionId。
- 资料库当前主视图和详情 ID。
- 可分享/可恢复的筛选条件使用 query 参数；临时 hover、抽屉动画等不进入 URL。

浏览器刷新、前进、后退必须保持当前位置。旧 Streamlit `pending_navigation_intent` 不移植到 Vue；它只在兼容期用于旧 UI。

### 7.2 Pinia 状态边界

建议 store：

- `appStore`：版本、开发者模式、本地服务状态、全局通知。
- `projectStore`：当前项目摘要和可选项目列表。
- `storyStore`：当前故事摘要、模式和切换状态。
- `operationStore`：活动操作、SSE 订阅、进度和取消请求。
- `preferencesStore`：面板宽度、折叠状态、编辑器偏好、主题。

不要把知识库全部条目、全部来源、全部会话和全部任务放进一个永久 store。服务端数据应按 query key 缓存并在 mutation 后精确失效。

### 7.3 未保存草稿

- 正文和规划编辑器采用客户端 debounce 草稿恢复。
- 草稿 key 至少包含 app schema、projectId、storyId、asset type 和 logical ID。
- 草稿保存原始服务端 revision/hash，恢复时如果服务端已变化必须显示冲突，不能静默覆盖。
- 成功保存后清除对应草稿。
- API Key、凭据、模型完整响应和网页原文不得进入 localStorage。
- 对话输入可短期保存在 sessionStorage；用户主动发送或清空后移除。
- 离开含未保存变更的路由时显示 DirtyGuard。

### 7.4 多标签页

- 当前项目和故事主要由 URL 决定，不再依赖数据库中的全局 `is_active` 驱动每个请求。
- `is_active` 只作为启动默认或兼容偏好，不得让一个标签页切换故事后把另一个标签页强制跳走。
- 保存冲突使用 revision/hash/updated_at 比较；发生冲突返回 HTTP 409 并展示差异或重新加载选项。
- 后台任务状态由服务端权威返回，多标签页不各自创建重复任务。

## 8. API 契约

### 8.1 通用规则

- 基础路径：`/api/v1`。
- JSON 字段统一 `snake_case`，时间为 UTC ISO 8601。
- 业务对象在 URL 中使用稳定 ID；项目重命名后 route 不失效。
- 请求与响应均使用明确 Pydantic 模型。
- 列表默认分页，禁止无上限返回全部知识、来源、任务或用量事件。
- 写请求支持 `Idempotency-Key`；创建任务、提交动作、保存章节等不可因重试重复执行。
- 有并发覆盖风险的写请求携带 `expected_revision`、`content_hash` 或 `updated_at`。
- 危险操作的确认必须在 API 请求体中表达，不能只依赖前端已显示弹窗。
- GET 必须无副作用。
- 错误不返回 Python traceback、绝对路径、密钥或原始 SQL。

成功响应建议：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_..."
  }
}
```

失败响应建议：

```json
{
  "error": {
    "code": "story_mode_conflict",
    "message": "当前故事使用规划创作模式。",
    "details": {},
    "retryable": false,
    "request_id": "req_..."
  }
}
```

稳定错误码至少覆盖：

- `validation_error`
- `project_not_found`
- `story_not_found`
- `story_mode_conflict`
- `resource_conflict`
- `operation_in_progress`
- `confirmation_required`
- `capability_unavailable`
- `capability_degraded`
- `budget_confirmation_required`
- `lease_conflict`
- `maintenance_mode`
- `unsafe_path`
- `unsafe_url`
- `database_unavailable`
- `provider_error`
- `internal_error`

### 8.2 Bootstrap 与系统接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/health/live` | 进程存活，不触发重型检查 |
| GET | `/api/v1/health/ready` | schema、静态资源和核心初始化就绪 |
| GET | `/api/v1/bootstrap` | 版本、项目列表、上次选择、能力摘要、开发者模式 |
| GET | `/api/v1/system/version` | `VERSION`、schema、前端构建标识 |
| GET | `/api/v1/system/capabilities` | Chat/Embedding/Search/OCR 就绪与降级原因 |

`bootstrap` 不返回密钥，不加载全部项目详情，不触发向量重建或任务创建。

### 8.3 项目与故事接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET/POST | `/api/v1/projects` | 列表、新建 |
| GET/PATCH/DELETE | `/api/v1/projects/{project_id}` | 摘要、重命名、隔离删除 |
| GET/POST | `/api/v1/projects/{project_id}/stories` | 故事列表、新建并选择模式 |
| GET/PATCH/DELETE | `/api/v1/projects/{project_id}/stories/{story_id}` | 故事详情、重命名、删除 |
| POST | `/api/v1/projects/{project_id}/stories/{story_id}/copy` | 复制故事及模式 |
| PUT | `/api/v1/projects/{project_id}/stories/{story_id}/creation-mode` | 无损切换创作模式 |

项目和故事 API 必须调用现有路径安全、维护锁、复制、软删除和检索同步服务，不能自行操作目录。

### 8.4 规划创作接口组

接口按资产语义组织，而不是按旧 Streamlit 页面组织：

- `/planned/profile`
- `/planned/outline`
- `/planned/volumes`
- `/planned/arcs`
- `/planned/chapters/{chapter_no}/outline`
- `/planned/chapters/{chapter_no}/draft`
- `/planned/chapters/{chapter_no}/reviews`
- `/planned/discussions/*`
- `/planned/context-directives`

每类资产至少提供：读取、保存、讨论、生成、历史/上下文快照和必要删除。讨论批准与正式保存保持不同动作。生成默认返回 operation descriptor，再通过 SSE 订阅；不在一个长时间 HTTP JSON 请求中阻塞页面。

### 8.5 对话创作接口组

建议接口：

- `GET/POST /chat/sessions`
- `GET/PATCH/DELETE /chat/sessions/{session_id}`
- `GET /chat/sessions/{session_id}/bundle`
- `POST /chat/sessions/{session_id}/messages`
- `POST /chat/sessions/{session_id}/actions/plan`
- `POST /chat/actions/{action_id}/confirm`
- `POST /chat/actions/{action_id}/cancel`
- `POST /chat/actions/{action_id}/undo`
- `POST /chat/fragments/{fragment_id}/accept`
- `POST /chat/fragments/{fragment_id}/select`
- `POST /chat/fragments/{fragment_id}/rewrite`
- `GET/POST/DELETE /chat/sessions/{session_id}/attachments`
- `GET /chat/sessions/{session_id}/memory`
- `POST /chat/sessions/{session_id}/memory/review`
- `POST /chat/sessions/{session_id}/save-chapter`
- `GET /chat/sessions/{session_id}/last-context`

接口必须继续区分 `creative_messages`、`creative_turns`、`creative_fragments` 和 `creative_action_runs`，不能为了前端方便把它们合并为一张“聊天记录”。

### 8.6 资料、知识和任务接口组

知识：

- 分页搜索、筛选和游标。
- 正式知识详情、规范编辑、移动、归档、合并。
- 修订列表、diff 和恢复为新修订。
- 待审核知识确认、丢弃、批量审核和证据查看。
- 角色、世界观、时间轴和关系图投影。

来源：

- 来源列表、详情、修订、片段、精确原文区间。
- 上传、粘贴文本、公开 URL 和已有资料附加。
- 隔离、激活和删除必须继续遵守来源资产契约。

任务：

- 使用统一任务摘要 DTO 表示 `source_ingestion`、`web_research` 和知识索引状态。
- 控制命令仍调用各自 workflow，不绕过租约和 fencing。
- 任务列表分页；详情按需加载 steps 和证据。
- 暂停、取消不是强杀第三方 HTTP 请求，UI 必须显示真实语义。

### 8.7 设置、能力和用量接口组

- 模型档案列表、编辑、删除、默认方案。
- 凭据只接受写入/替换/删除，不提供明文读取。
- 连接测试返回分能力结果，不返回请求中的密钥。
- 规则和提示词选项继续支持 global/project/story 三层作用域。
- 自动配置返回当前值、锁定字段、原因和修订。
- 用量提供今日、月度、项目、故事、模型、操作和 Agent 聚合。
- 预估接口只返回估算，不写入虚假用量事件。
- 开发者检索接口受服务端开发者模式保护，不能只靠前端隐藏。

### 8.8 OpenAPI 与 TypeScript

- FastAPI OpenAPI 是前后端契约事实源。
- 构建过程导出确定性 `openapi.json`。
- TypeScript 类型和 API client 从 OpenAPI 生成或检查，不手工维护重复接口类型。
- CI/本地验证检查生成结果是否与 Python schema 一致。
- API 破坏性变更必须新增版本或提供兼容窗口，不能静默改变字段语义。

FastAPI 可直接使用 Pydantic 请求体进行验证并生成 OpenAPI：<https://fastapi.tiangolo.com/tutorial/body/>。

## 9. 流式输出与后台运行

### 9.1 操作模型

所有长操作统一返回：

```json
{
  "operation_id": "op_...",
  "operation_type": "chapter_write",
  "status": "queued",
  "stream_url": "/api/v1/operations/op_.../events",
  "resource_ref": {}
}
```

SSE 事件至少包括：

- `operation.started`
- `stage.changed`
- `token.delta`
- `progress.updated`
- `usage.updated`
- `artifact.saved`
- `operation.completed`
- `operation.failed`
- `operation.cancel_acknowledged`
- `heartbeat`

事件字段包括 `event_id`、`operation_id`、`sequence`、`occurred_at` 和类型化 payload。前端必须按 sequence 去重并容忍重连。

### 9.2 SSE 使用边界

- LLM Token 为单向流，使用 SSE。
- 浏览器断开只停止订阅，不默认取消服务端操作。
- 用户点击取消时调用独立 POST；第三方模型请求可能无法立即终止，UI 显示“取消已请求，将在安全检查点生效”。
- 对可恢复资料/研究任务，SQLite 状态仍是权威；SSE 只是降低轮询延迟。
- 页面刷新后先 GET 当前 operation/task 状态，再用 `Last-Event-ID` 或最新 sequence 继续订阅。
- `token.delta` 在前端以短时间批次合并渲染，避免每个 Token 触发完整组件树更新。

FastAPI/Starlette 支持流式响应；具体 SSE 实现和断线行为必须通过集成测试验证：<https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse>。

### 9.3 进程内 OperationRegistry

交互生成可使用进程内 registry 保存当前订阅者和短期事件缓冲，但它不是业务权威存储：

- 最终正文、片段、讨论或大纲仍由现有资产/运行记录保存。
- durable task 始终从 SQLite 恢复。
- registry 重启丢失时，前端通过业务资源和任务状态恢复，不把“没有内存事件”误判为数据丢失。
- 是否为非 durable 规划生成增加持久 operation 行，在 `VF-0.5` 形成 ADR 后决定；不能未经设计复用 `workflow_runs` 改变其现有语义。

### 9.4 调度器生命周期

FastAPI lifespan 取代 `app.py` 中的 Streamlit 启动位置：

1. 校验 schema 和静态资源。
2. 启动 ingestion、web research、knowledge index dispatcher。
3. prime 已有项目的知识索引任务。
4. 记录 runtime owner 和健康状态。
5. 关闭时发出停止信号并允许安全检查点；不强杀第三方请求。

兼容期 Streamlit 与 Vue 后端不得同时针对同一 data root 启动。现有 launcher lock 必须继续保证单实例启动。

## 10. 创作模式数据与业务规则

### 10.1 建议 schema 16

在 `stories` 增加稳定列：

```sql
creation_mode TEXT NOT NULL DEFAULT 'planned'
    CHECK (creation_mode IN ('planned', 'conversational'))
```

原因：

- 模式决定进入哪个应用 Layout，需要在加载完整 `story_profiles.profile_json` 前快速读取。
- 它是高频路由字段，不适合埋在低频 JSON payload。
- 旧故事默认 planned，保持当前行为。

迁移必须新增 `016_story_creation_mode.sql`，不得修改 `001_initial.sql`。repository、service、`StoryMeta`、复制、同步、软删除和兼容 index 都要显式处理该字段。

### 10.2 模式与上下文策略

模式不能只改变 UI：

- `planned`：保持当前大纲、卷、剧情段和章节细纲进入对应生成上下文的规则。
- `conversational`：默认不要求、也不主动推荐规划资产；上下文主要来自会话摘要、已接受片段、正式知识、附件和检索。
- 如果一个故事从 planned 切到 conversational，既有规划资产保留；可通过高级选项“在对话中参考既有规划”显式启用。
- 建议把低频策略 `planning_context_policy = mode_default | include | exclude` 保存到 `story_profiles.profile_json`，避免再新增高频列。
- mode 默认值解析必须是纯 domain 函数，并由 context assembly 调用，不能只在 Vue 中判断。

### 10.3 对话模式自动提取

- 新建 conversational 会话默认使用现有 `auto_extract_mode='on_accept'` 或其后续兼容扩展。
- 自动提取发生在片段接受或稳定事实满足阈值后，不对每个 Token 调用模型。
- 自动结果进入待审核知识或会话记忆层，不直接覆盖正式知识。
- 当前会话可以使用已提取的临时记忆；跨故事/项目提升仍需明确确认。
- 提取失败不阻塞正文继续创作，并显示可重试状态。
- 费用预估和实际用量必须归因到自动提取操作。

### 10.4 模式切换

模式切换事务只更新模式与必要 profile 策略，不删除资产：

- planned -> conversational：提示规划入口将隐藏，询问是否让对话继续参考已有规划。
- conversational -> planned：提示可把现有会话、片段和知识作为规划素材，不自动生成大纲。
- 正在运行的生成不被强制终止；UI 可等待完成后导航，或立即切换并在任务中心保留状态。
- API 返回新模式和目标 route；前端执行 replace 导航。
- 切换需要幂等，重复提交相同模式不得产生额外副作用。

## 11. 当前 Streamlit 能力到目标模块的映射

| 当前入口/模块 | 目标 Vue feature | 目标 API | 迁移说明 |
| --- | --- | --- | --- |
| `app.py` | App bootstrap/router | system/bootstrap | 最终只保留 ASGI 入口，不承载页面分发 |
| `ui/app_shell.py` | start、project/story switcher | projects/stories | Session State 改为 URL + client state |
| `ui/workbench_hub.py` | project dashboard | project summary | 不复制 Hub 标签结构 |
| `ui/resource_management.py` | content browser | assets/content | 使用分页与详情抽屉 |
| `ui/creative_profile_page.py` | planned direction | planned/profile | 讨论和表单在同一工作区 |
| `ui/outline_page.py` | book outline workspace | planned/outline | 保留讨论批准与正式保存差异 |
| `ui/volume_outline_page.py` | volume workspace | planned/volumes | 左侧树直接定位卷 |
| `ui/arc_outline_page.py` | arc workspace | planned/arcs | 保留章节分配和讨论资产 |
| `ui/chapter_outline_page.py` | chapter outline | planned/chapters | 以 chapter route 作为定位 |
| `ui/chapter_page.py` | chapter write/review | planned/chapters | 三步页面改成同一编辑工作区状态 |
| `ui/chapter_review_panel.py` | review panel | planned/reviews | 快速、综合、历史报告统一 |
| `ui/free_writing/*` | conversational shell | chat/* | 优先迁移，保留四类持久对象语义 |
| `ui/knowledge_center.py` | knowledge search | knowledge/search | 游标分页与虚拟列表 |
| `ui/knowledge_management.py` | knowledge editor/review | knowledge/* | 拆成搜索、详情、编辑、审核 feature |
| `ui/entity_experience.py` | entities/timeline/graph | knowledge/entities | 继续作为正式知识实时投影 |
| `ui/long_reference_importer.py` | source import wizard | sources/imports | 上传、预估、确认、创建任务分离 |
| `ui/long_reference_batch.py` | import batch detail | tasks/ingestion | 直接展示权威 task/batch 状态 |
| `ui/web_research*.py` | research task workspace | tasks/research | 保留隔离、证据和激活语义 |
| `ui/llm_settings.py` | model settings | settings/models | 凭据 write-only |
| `ui/llm_preflight.py` | PreflightCard | operations/preflight | 统一所有生成入口 |
| `ui/llm_usage.py` | UsageSummary/ledger | usage/* | 聚合分页，不加载 prompt/正文 |
| `ui/rules_page.py` | rules editor | settings/rules | 三层作用域不变 |
| `ui/prompt_options_page.py` | writing preference editor | settings/prompt-options | 兼容逻辑 ID |
| `ui/retrieval_center_page.py` | developer retrieval tools | developer/retrieval | 服务端校验开发者模式 |
| `ui/layout.py` | design tokens/primitives | 无 | 不迁移 DOM CSS，只提取设计语义 |

迁移页面前必须先列出其所有 service/workflow 调用。若页面包含业务规则，先把规则下沉到 domain/workflow，再建立 API；禁止在 Vue 中重新实现一份 Python 领域判断。

## 12. 分阶段实施任务

## 阶段 0：冻结基线与架构决策

目标：在写生产代码前固定现状、视觉方向、API 和运行边界。

### VF-0.1：建立迁移基线

状态：`已完成（2026-08-19）`

交付：

- 记录当前 git 基线、版本、schema、Python 验证矩阵和 UI 页面清单。
- 记录四类代表性项目夹具：空项目、规划型故事、对话型故事、大型资料库。
- 所有夹具必须位于隔离测试 data root，不能复制真实密钥。
- 保存当前关键 Streamlit 行为的截图或文字契约，用于功能对照，不追求视觉复刻。

验收：现有核心验证全部通过，失败项有明确基线说明；未触碰生产数据。

### VF-0.2：完成页面—调用—存储矩阵

状态：`已完成（2026-08-19）`

交付：为每个 Streamlit renderer 列出读取、写入、生成、确认、错误和跳转；标记公开门面缺口、私有函数调用和 UI 内业务逻辑。

验收：任何计划迁移页面都能追踪到 workflow/service/repository 和权威资产，不存在“先做页面再猜后端”的条目。

### VF-0.3：技术 ADR

状态：`已完成（2026-08-19）`

必须形成 ADR：

- Vue 3 + TypeScript + Vite。
- npm + `package-lock.json`，发布使用 `npm ci`。
- Router、Pinia、server-state cache、headless primitives、图标、编辑器和 OpenAPI client 生成方案。
- SSE 而非 WebSocket 的当前理由。
- Node 仅构建时存在。
- 浏览器式本地应用而非 Electron/Tauri。

验收：所有核心依赖版本有上限/锁文件策略；不存在同时引入两套同类状态库或组件库。

### VF-0.4：双 Layout 高保真原型

状态：`已完成（2026-08-19）`

按第 6.4 节完成假数据原型、交互说明、响应式截图、视觉 Token 初稿和组件清单。用户明确认可两种风格后方可进入生产迁移。

### VF-0.5：API、流式与本地安全 ADR

状态：`已完成（2026-08-19；协议、安全、mutation 幂等回放、取消命令与有界断线重放窗口已落地）`

锁定：错误 envelope、request ID、idempotency、并发冲突、SSE 事件、断线、取消、本地客户端请求头、CORS、Host 校验和非 durable operation 行为。

验收：使用时序图覆盖普通查询、流式生成、确认动作、文件上传、任务暂停和断线恢复。

## 阶段 1：故事模式领域与存储

目标：先让“两个 UI”成为后端可验证的故事属性，而不是前端临时状态。

### VF-1.1：定义 CreationMode 领域模型

状态：`已完成（2026-08-19）`

- 在 domain 定义枚举、兼容默认、切换规则和 planning context policy 解析。
- 明确新建、复制、重命名、归档、删除时的模式语义。
- 不导入 FastAPI 或 Vue 类型。

### VF-1.2：新增 schema 16

状态：`已完成（2026-08-19）`

- 新增 `016_story_creation_mode.sql`。
- 更新 `CURRENT_SCHEMA_VERSION`。
- 更新 `storage_architecture.md` 的当前版本和迁移历史。
- 验证旧数据库升级、新数据库初始化、版本过高拒绝和回滚备份说明。

### VF-1.3：repository/service 全链路

状态：`已完成（2026-08-19）`

- `list_story_rows`、同步、创建、复制、更新和兼容 index 处理模式。
- 对外提供 `get_story_creation_mode` 与 `set_story_creation_mode` 稳定门面。
- 复制故事默认继承，旧 JSON 不重新成为权威。

### VF-1.4：上下文与自动提取策略

状态：`已完成（2026-08-19）`

- context assembly 读取领域策略。
- conversational 默认不要求规划资产。
- 新会话自动提取默认与模式一致。
- 费用归因和降级不变。

### VF-1.5：模式回归验证

状态：`已完成（2026-08-19）`

新增验证覆盖：旧故事默认、混合模式项目、复制、切换无损、上下文 include/exclude、对话自动提取、故事删除清理和 DB-first。

阶段门：schema 16 和模式服务未稳定前，不允许 Vue router 自己保存 mode。

## 阶段 2：FastAPI 平台骨架

目标：建立不依赖 Streamlit 的本地应用服务，并保持所有业务从现有门面进入。

### VF-2.1：应用工厂与健康检查

状态：`已完成（2026-08-19）`

- 新建 `novelforge/api/`。
- 实现 application factory、配置注入、`live/ready/version`。
- 测试模式可使用临时 data root 和禁用外部网络。
- 尚不改变默认 launcher。

### VF-2.2：中间件、错误与本地安全

状态：`已完成（2026-08-19）`

- request ID、结构化访问日志、耗时和错误映射。
- production 同源、开发 Vite proxy；生产不开放通配 CORS。
- 仅允许 `127.0.0.1/localhost` Host。
- 所有 mutation 要求自定义本地客户端头，使跨站简单请求无法直接触发。
- CSP、`nosniff`、Referrer Policy 和禁止 frame 嵌入。

### VF-2.3：bootstrap、项目和故事垂直切片

状态：`已完成（2026-08-19）`

- 完成 bootstrap、项目列表/创建、故事列表/创建/模式切换。
- route 使用 project_id，服务层安全解析到当前项目目录。
- 删除与重命名复用维护锁和确认语义。

### VF-2.4：OpenAPI 导出与 TypeScript 生成

状态：`已完成（2026-08-19）`

- 新增确定性 OpenAPI 导出工具。
- 前端生成类型，不手工复制 DTO。
- 增加 `--check` 模式，CI 检查漂移。

### VF-2.5：OperationRegistry 与 SSE

状态：`已完成（2026-08-19；OperationRegistry、sequence、heartbeat、终态快照、假流、cancel command 与 events replay 已完成；持久工作流仍由既有 workflow rows 负责）`

- 实现类型化事件、sequence、心跳、重连和终态缓存。
- 使用假生成器验证 Token 流，不调用真实模型。
- 断开订阅不取消任务；取消走独立命令。

### VF-2.6：FastAPI lifespan 与调度器

状态：`已完成（2026-08-19）`

- 把三个 dispatcher 的启动和 prime 迁入 lifespan。
- 增加重复启动保护和健康摘要。
- 测试 shutdown、旧租约接管和不存在项目目录时不重建数据库。

### VF-2.7：API 基础验证

状态：`已完成（核心验证通过；凭据测试受 Windows Credential Manager 环境限制）`

验证：DTO、错误码、ID 解析、路径安全、同源策略、密钥脱敏、幂等、409 冲突、SSE 断线和测试 data root 隔离。

阶段门：必须能在不 import Streamlit 的测试进程中完成项目/故事读写和假 SSE 操作。

## 阶段 3：Vue 工程与设计系统

目标：建立可维护的前端底座和两个独立 Layout，不接入全部业务。

### VF-3.1：Vue 工程脚手架

状态：`已完成（2026-08-19）`

- `create-vue`：TypeScript、Router、Pinia、Vitest、ESLint、Prettier。
- 设置严格 TypeScript、路径别名、环境变量白名单和 production source map 策略。
- `dist` 不提交；发布脚本负责构建。

### VF-3.2：设计 Token 与基础组件

状态：`已完成（Token、双 Layout、组件预览 route、焦点/disabled/error/loading/reduced-motion 样式已验证）`

- 完成第 6 节 Token 和 primitives。
- 建立 Storybook 或等价组件预览方案；若不引入 Storybook，必须有组件展示 route。
- 验证键盘、焦点、disabled、loading、error 和 reduced motion。

### VF-3.3：Typed API client 与 server-state

状态：`已完成（2026-08-19；Pinia/client、生成类型、mutation headers、超时/AbortError、SSE 流解析与操作事件重放接口已完成）`

- 统一 base URL、request ID、错误解析、取消和超时。
- mutation 默认携带本地客户端头和 idempotency key。
- 禁止 feature 直接裸 fetch。

### VF-3.4：Router 与双 Layout guard

状态：`已完成（2026-08-19）`

- 实现 PlannedAppLayout 和 ConversationalAppLayout。
- route guard 根据 bootstrap/story mode 重定向。
- 直接粘贴深链接、刷新、前进后退和无效 ID 都有明确结果。

### VF-3.5：启动页与故事模式选择

状态：`已完成（2026-08-19）`

- 项目选择、新建项目、新建故事和模式卡片。
- 模型未配置时仍允许创建项目，但明确引导设置。
- 旧故事一次性模式建议不阻塞进入。

### VF-3.6：前端测试基础

状态：`已完成（2026-08-20；Vitest、API client、路由测试、Playwright Chromium + Edge E2E、移动截图、键盘焦点、组合输入保护和首屏性能检查已接入）`

- Vitest + Vue Test Utils。
- Playwright 浏览器矩阵已覆盖本机 Chromium 与 Microsoft Edge；发布 CI 仍需保留至少一个干净环境矩阵。
- API mock 与真实临时后端两级测试。
- 截图使用固定本地字体和时区。

阶段门：两个 Layout 以假数据呈现并通过用户视觉验收；还不能宣布业务可用。

## 阶段 4：对话创作界面优先迁移

目标：先交付边界清晰、最能体现 Vue 价值的对话模式垂直切片。

### VF-4.1：会话列表与 bundle API

状态：`已完成（2026-08-19；列表、创建、读取、重命名、归档、侧栏、会话重命名和归档确认已接通；分页保留为大数据量优化）`

- API 暴露分页会话、创建、重命名、归档、删除和 bundle。
- UI 完成会话侧栏、空状态、最近会话和 URL 恢复。

### VF-4.2：消息与流式正文

状态：`已完成（2026-08-19；SSE 发送/增量显示、继续/重写/分支动作选择、IME 组合输入保护已接通）`

- 发送消息、路由动作、创建 creative turn/action 和 SSE。
- 区分普通消息、正文片段、工具回执、错误和澄清。
- 中文 IME、Shift+Enter、Ctrl/⌘+Enter 正确。

### VF-4.3：片段接受、重写、分支与版本

状态：`已完成（2026-08-20；接受/候选切换、重写/分支、状态标识、版本时间线和通用 mutation 幂等回放已接通）`

- 迁移 fragment history/actions。
- 当前分支、候选版本和 accepted 状态清晰可见。
- 重复点击、网络重试和冲突不会产生重复 turn。

### VF-4.4：动作卡、确认与撤销

状态：`已完成（2026-08-19；动作规划/确认/取消/执行/撤销 API 与对话动作卡已接通）`

- `update_config/update_knowledge/extract_knowledge/save_chapter` 使用统一动作卡。
- Diff、作用域、费用和副作用明确。
- 取消、失败、确认、完成、undone 状态可恢复。

### VF-4.5：附件托盘

状态：`已完成（2026-08-20；粘贴资料、公开 URL、文件上传、会话附件列表、后台任务进度、失败重试和对话附件托盘已接通）`

- 文件、粘贴文本、公开 URL、已有资料。
- 仅下一轮/会话/故事/项目作用域。
- 上传进度、解析、词法可用、知识化、OCR、失败重试。
- 文件上限、压缩安全、SSRF 和重复附件继续由服务端保护。

### VF-4.6：自动记忆与知识抽屉

状态：`已完成（2026-08-19；待确认知识列表、确认/忽略 API 与共享工作区记忆抽屉已接通）`

- 展示会话记忆、自动提取、待审核条目和来源。
- 批量确认/忽略/修正不打断对话。
- 正式知识变更仍经过动作协议或知识 API。

### VF-4.7：章节保存、上下文与预估

状态：`已完成（2026-08-20；章节保存、context preview、预算指标、对话侧上下文预览和全局今日/月度用量面板已接通）`

- 保存章节使用确认动作和幂等键。
- 展示 last context、遗漏、检索降级、Token/费用和操作用量。
- 一次性附件/创作提醒只在业务成功后消费。

### VF-4.8：对话模式验收

状态：`已完成（2026-08-20；会话、流式、动作、附件、模式切换、错误和幂等 API smoke 已覆盖；SSE 客户端按 operation_id/sequence 做有界断线回放，Vitest fixture 已验证；真实模型/provider 长流仍需发布环境集成夹具）`

必须覆盖：首次输入、连续写作、普通问答、知识查询、配置修改、附件、断线恢复、刷新、失败重试、切故事、模式切换和无模型降级。通过后可作为 opt-in beta，但 Streamlit 仍保留。

## 阶段 5：规划创作界面迁移

目标：建立真正的长篇规划工作台，不复制四 Hub 标签页。

### VF-5.1：作品结构树与 Planned Layout

状态：`已完成（2026-08-19；独立 Layout、故事工作区、项目/故事切换、章节结构摘要和侧栏结构树已接通）`

- API 提供卷、剧情段、章节、完成状态和资源计数的轻量树摘要。
- 支持折叠、定位、当前资产、键盘导航和懒加载。
- 不在首屏加载每个资产正文。

### VF-5.2：创作方向工作区

状态：`已完成（2026-08-19；创作方向读写、规划页表单、保存反馈、讨论流和批准动作已接通）`

- 讨论、结构化建议、表单、自动配置和保存。
- 未配置不阻塞其它功能，但状态明确。
- profile 并发保存使用 revision/updated_at。

### VF-5.3：全书大纲工作区

状态：`已完成（2026-08-19；大纲读取/编辑/保存、讨论资产读取、讨论流、批准 API 与页面讨论面板已接通）`

- 讨论消息、批准结论、生成、人工编辑、保存和上下文证据。
- 预览不写正式大纲；保存后才消费 once directive。

### VF-5.4：分卷工作区

状态：`已完成（2026-08-20；分卷详情/大纲读写、结构摘要、独立工作区、讨论流、批准动作和服务层级联删除确认已接通）`

- 卷列表、当前卷、元数据、讨论、生成、保存、删除和下一阶段定位。
- 删除继续使用服务层资产级联，不根据标题拼路径。

### VF-5.5：剧情段工作区

状态：`已完成（2026-08-20；剧情段详情/大纲读写、结构摘要、讨论/批准、章节计划读写、重复/跨剧情段/预计数量/既有归属冲突校验与人工合并提示已接通）`

- 剧情段列表、卷归属、章节范围、讨论、章节计划和正文资产。
- 章节分配冲突返回显式错误。

### VF-5.6：章节细纲工作区

状态：`已完成（2026-08-20；章节细纲/正文读写、卷/剧情段结构上下文树、章节讨论流/批准和缺失上层规划提示已接通）`

- 章节层级、卷/剧情段上下文、讨论批准、细纲生成和编辑。
- 允许跳过缺失上层规划，但明确显示缺失上下文。

### VF-5.7：章节正文与审阅

状态：`已完成（2026-08-20；正文读写、章节选择、保存反馈、审阅投影、章节讨论和版本时间线/历史正文对比入口已接通）`

- 需求、生成、编辑、草稿恢复、保存、快速审阅、综合审阅和历史报告。
- 流式生成期间不阻塞右侧证据浏览。
- 保存和审阅分离，设定提炼仍是独立动作。

### VF-5.8：讨论资产、规则和上下文检查器

状态：`已完成（2026-08-20；讨论资产读取/批准、章节讨论、context preview、三层规则/提示词偏好、自动配置原因与证据 API/UI 已接通；普通用户隐藏原始 JSON，开发者投影由服务端环境变量控制并有 guard fixture）`

- 把 discussion asset candidates、规则、提示词、创作提醒、检索证据和 context snapshot 迁入右侧检查器。
- 普通用户不看到原始 JSON；开发者模式可查看技术细节。

### VF-5.9：规划模式验收

状态：`已完成（2026-08-20；规划方向→全书大纲→卷/剧情段→章节细纲→正文/审阅的 API smoke、结构校验、章节讨论、版本时间线和路由 E2E 已覆盖；真实模型长流由集成夹具补测）`

覆盖从空故事到方向、全书、分卷、剧情段、细纲、正文和审阅的完整链路；覆盖跳级、旧资产、讨论批准、预览、保存失败、流断开和故事切换。

## 阶段 6：共享工作区迁移

目标：补齐两种创作界面都依赖的项目、资料、知识、设置和任务功能。

### VF-6.1：项目概览与内容浏览

状态：`已完成（2026-08-20；项目摘要、章节/知识摘要、章节读写、知识详情、内容浏览分页和确认式安全删除已接通）`

- 项目摘要、推荐下一步、内容类型计数。
- 内容分页、筛选、定位、打开和安全删除。
- 推荐下一步根据 story mode 返回不同目标。

### VF-6.2：项目与故事生命周期

状态：`已完成（2026-08-19；项目与故事重命名/复制/归档/删除 API、确认交互和共享工作区复制入口已接通）`

- 重命名、复制、归档、删除、维护锁和运行任务冲突。
- 危险操作 API 二次确认并提供可恢复性说明。

### VF-6.3：统一资料与知识搜索

状态：`已完成（2026-08-20；知识搜索/详情 API、类型筛选、游标分页、URL 查询恢复、固定窗口虚拟列表和共享工作区主从视图已接通；10,000 条知识搜索夹具最近一次 p95=177.1ms，低于 300ms 预算）`

- FTS 分页、分类、故事、世界线、来源和归档筛选。
- 大列表虚拟化、URL 筛选恢复和主从视图。

### VF-6.4：知识详情、编辑与修订

状态：`已完成（2026-08-20；类型化 schema API、知识详情编辑、修订列表、当前-历史快照对比、证据摘录高亮、revision 冲突拒绝和历史快照载入后手动合并已接通；来源深链仍属后续增强）`

- 类型化表单、证据、来源高亮、diff、恢复、移动、合并和归档。
- 409 冲突提供重新加载或手动合并。

### VF-6.5：待审核、实体、时间轴和关系图

状态：`已完成（2026-08-20；关系图、角色/设定/时间线投影专用视图、待审核候选与共享记忆抽屉已接通）`

- 批量审核与策略。
- 角色/世界观卡片只投影正式知识。
- 图编辑回写正式关系知识，不直接改投影表。

### VF-6.6：资料导入与来源管理

状态：`已完成（2026-08-20；来源账本、公开 URL/文件附件入口、会话与项目多文件批量导入向导、研究任务工作区、批次健康/原文与知识化状态投影、逐页 OCR 置信度与进度回调已接通；真实 OCR/provider 评测仍属于发布环境门槛）`

- 简化导入、预估、确认、批次、来源修订和 OCR 预览。
- 原文词法可用与后台知识化状态分开显示。

### VF-6.7：网络研究

状态：`已完成（2026-08-20；网络研究创建、六阶段投影、控制、来源隔离/激活、已验证结论逐条送审和证据数量/权威度预览已接通；真实联网评测仍受 provider 配置约束）`

- 创建、估算、六阶段进度、证据、评测、控制和人工送审。
- 网页隔离与激活必须明确，不能因打开结果页自动进入 RAG。

### VF-6.8：模型、凭据与能力设置

状态：`已完成（2026-08-19；能力状态 API、脱敏模型列表、写入式密钥表单、活动模型切换和双 Layout 设置页已接通）`

- Chat/Embedding/Search/OCR 独立状态。
- 密钥 write-only、指纹/末四位展示、连接测试和降级。
- 不在浏览器持久化任何密钥。

### VF-6.9：规则、偏好、自动配置与用量

状态：`已完成（2026-08-20；全局/项目/故事规则编辑、提示词偏好、自动配置状态/原因/锁定字段、今日/月度用量和项目/故事/模型/操作/Agent 明细检查器已接通）`

- global/project/story 作用域编辑。
- 自动配置原因和锁定字段。
- 今日/月度/项目/操作明细和价格可信度。

### VF-6.10：任务中心与开发工具

状态：`已完成（2026-08-19；项目任务聚合、能力状态与共享工作区任务/能力投影已接通；开发者权限投影保留为部署加固）`

- 全局任务抽屉聚合 ingestion/research/index 状态。
- 开发者检索、评测和索引维护只在服务端允许时返回。
- 大型技术 payload 按需加载。

阶段门：普通用户功能达到 Streamlit 能力级对等；未迁移能力必须有明确回退入口，不能静默消失。

## 阶段 7：启动、构建与便携版

目标：让 Vue 版本在开发环境和 Windows 便携版中稳定启动，不要求用户安装 Node.js。

### VF-7.1：FastAPI 托管静态资源

状态：`已完成（2026-08-19）`

- `/api/*` 不进入 SPA fallback。
- hashed assets 使用长期缓存，`index.html` 禁止长期缓存。
- 未构建 dist 时 ready 检查失败并给出明确开发提示。
- 所有前端资源离线可用。

### VF-7.2：launcher 双模式兼容

状态：`已完成（2026-08-19）`

- 抽取通用端口、锁、日志、状态文件和浏览器打开逻辑。
- 增加 Vue/FastAPI 启动命令和 `/health/ready` 检查。
- 兼容期通过显式环境变量选择 `streamlit|vue`，同一 data root 禁止并行。
- 错误文案不再硬编码 Streamlit。

### VF-7.3：发布构建链

状态：`已完成（2026-08-20；构建脚本执行 npm ci、OpenAPI/类型检查、Vitest、Vue build、PyInstaller、运行时依赖检查并产出带 hashed dist 的便携包）`

`build_release.ps1` 增加：

1. 校验 Node/npm 仅存在于构建机。
2. `npm ci`。
3. typecheck、lint、unit test。
4. `npm run build`。
5. 校验 dist marker、资源 hash 和版本。
6. Python runtime 校验 fastapi/uvicorn 等依赖。
7. 便携包复制 dist，不复制 `node_modules`。
8. 包结构验证检查缺失/多余前端文件。

### VF-7.4：生产安全和日志

状态：`进行中（loopback、Host guard、mutation header、请求 ID、CSP、无 referrer、日志脱敏已验证；发布机安全审计清单和干净机权限证明待补）`

- 只绑定 loopback。
- 服务状态文件继续校验 root、pid、port。
- readiness 区分后端未就绪和静态资源缺失。
- launcher.log 不写请求正文、密钥、网页全文或模型响应。
- CSP 禁止远程脚本和不必要连接。

### VF-7.5：便携版冒烟

状态：`进行中（2026-08-20；自包含 Windows Python runtime、packaged FastAPI/Vue API 冒烟、布局和 Playwright 浏览器验证已完成；临时隔离 root 的真实 launcher 子进程已验证 ready、已有实例、端口冲突回退与停止后重启；干净机权限/浏览器打开/无 Node 矩阵仍待补）`

在干净 Windows 环境验证：解压、启动、端口冲突、已有实例、浏览器打开、创建项目、重启恢复、无 Node 环境、日志和退出行为。

## 阶段 8：切换、清理与正式发布

目标：以证据证明 Vue 达到功能、数据和发布对等后再删除 Streamlit。

### VF-8.1：端到端对等矩阵

状态：`进行中（已建立矩阵并覆盖 API/单元/Chromium+Edge Playwright 入口、刷新、组合输入和长草稿验收；旧 schema 15→16 升级与未来版本拒绝、临时 OpenAI-compatible HTTP 半截流/重试、匿名 10,000 条知识库夹具已通过；真实 provider 长流、真实用户大项目副本仍需 CI）`

逐项对比所有当前用户能力、错误、降级、预估、用量、任务恢复和数据结果。对等指业务语义一致，不要求页面布局一致。

### VF-8.2：视觉、性能与可访问性验收

状态：`进行中（双 Layout Token、响应式、焦点/禁用/错误/加载/reduced-motion、移动截图、键盘、组合输入、8,000 次长草稿和完整 WCAG 2A/2AA Axe 扫描已在 Chromium+Edge 自动化；SQLite/FTS 10,000 条搜索 p95 179.0ms；真实长会话/大资料交互压力仍需 CI）`

- 双 Layout 全状态截图。
- 键盘、焦点、对比度、屏幕阅读名称和 reduced motion。
- 大知识库、长会话、长正文、多个活动任务。
- 满足第 15 节性能预算。

### VF-8.3：默认切换到 Vue

状态：`已完成（2026-08-19；launcher 默认 Vue、缺 dist 自动回退 Streamlit、环境变量显式回退和 guard 验证已完成）`

- launcher 默认 Vue，Streamlit 仅显式回退。
- 至少经过一个正式兼容窗口。
- 收集本地启动、数据兼容和关键工作流失败样本。

### VF-8.4：文档与发布同步

状态：`已完成（2026-08-19；project/README/storage/ADR、迁移基线、调用矩阵和正式 release note 已同步）`

- 更新 README/README.en 安装、界面、模式和限制。
- 更新 `project.md` 当前架构和 UI 信息架构。
- 更新 `storage_architecture.md` schema 和模式字段。
- 新增 release note，不改写旧发布历史。
- 本规划更新实际完成状态。

### VF-8.5：删除 Streamlit UI 与依赖

状态：`待实施`

只有满足第 20 节最终完成定义后才能执行：

- 删除 `ui/` Streamlit renderer 和 Streamlit 专用验证。
- `app.py` 改为薄 ASGI 入口或导出 API app。
- requirements、launcher、release、spec、tools 清除 Streamlit。
- 保留仍有价值的纯 helper 前，必须迁入正确 domain/service/frontend 位置，不能建立 `legacy_ui` 永久墓地。

### VF-8.6：最终全量验证与发布

状态：`待实施`

运行 Python 全量回归、API 契约、前端 unit/e2e/visual、便携包冒烟、升级旧数据库和真实匿名大项目副本测试。成功后才宣布迁移完成。

## 13. 测试与验证矩阵

### 13.1 Python 既有回归

所有高风险阶段继续选择运行 `project.md` 中的相关 `tools/verify_*.py`。最终切换前至少包括：

```powershell
.\.venv\Scripts\python.exe tools\verify_package_structure.py
.\.venv\Scripts\python.exe tools\verify_db_storage.py
.\.venv\Scripts\python.exe tools\verify_context_assembly.py
.\.venv\Scripts\python.exe tools\verify_interactive_writing.py
.\.venv\Scripts\python.exe tools\verify_creative_actions.py
.\.venv\Scripts\python.exe tools\verify_creative_attachments.py
.\.venv\Scripts\python.exe tools\verify_ingestion_tasks.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_runtime.py
.\.venv\Scripts\python.exe tools\verify_ingestion_task_recovery.py
.\.venv\Scripts\python.exe tools\verify_web_research_tasks.py
.\.venv\Scripts\python.exe tools\verify_knowledge_center.py
.\.venv\Scripts\python.exe tools\verify_capability_orchestration.py
.\.venv\Scripts\python.exe tools\verify_llm_preflight.py
.\.venv\Scripts\python.exe tools\verify_llm_usage.py
```

### 13.2 API 测试

至少覆盖：

- OpenAPI schema snapshot。
- 所有错误码和 HTTP status 映射。
- 项目 ID 解析、重命名后稳定路由、路径穿越。
- 故事模式新建、复制、切换、旧库升级。
- DTO 过滤，确保不泄露 absolute path、secret 或内部 payload。
- 分页、游标、筛选和 409 并发冲突。
- idempotency 重放。
- 上传大小、压缩炸弹、SSRF 和不可信网页边界。
- SSE 顺序、重连、重复事件、取消和失败。
- dispatcher 单启动、lease、shutdown 和重启恢复。
- 临时 data root 之外无文件写入。

### 13.3 前端单元和组件测试

- route guard 与 mixed-mode project。
- API error 到用户文案映射。
- DirtyGuard、草稿冲突和恢复。
- PreflightCard、ActionCard、CapabilityNotice。
- 中文 IME 与快捷键。
- 虚拟列表和分页边界。
- SSE reducer 对乱序、重复、断线和终态的处理。
- 两个 Layout 不渲染对方的创作导航。

### 13.4 Playwright 端到端

关键旅程：

1. 首次启动 -> 配置模型引用 -> 新建项目 -> 新建 planned 故事。
2. planned：方向 -> 全书 -> 分卷 -> 剧情段 -> 细纲 -> 正文 -> 审阅。
3. 新建 conversational 故事 -> 输入 -> 流式正文 -> 接受 -> 自动记忆 -> 保存章节。
4. 对话附件 -> 原文可检索 -> 后台知识化 -> 待审核。
5. 网络研究 -> 暂停 -> 重启 -> 恢复 -> 送审 -> 激活来源。
6. 故事模式切换，所有旧资产仍存在。
7. 两标签页编辑冲突返回 409，不覆盖新版本。
8. 模型不可用、Embedding 关闭、OCR 缺失和搜索降级。
9. 端口冲突和服务重启后的前端恢复。

E2E 默认使用 stub 模型和离线搜索，不允许消耗真实 Token。

### 13.5 视觉回归

固定截图状态：

- 两个 Layout 的空、正常、loading、streaming、error、degraded。
- 长标题、长中文段落、英文、混合字符和无空格长串。
- 抽屉、Dialog、命令面板、Tooltip 和 Toast。
- 1440、1280、1024、768 四种视口。
- Light 首版；如果实现 dark，必须建立独立基线。

视觉 diff 不能取代人工设计验收；它只防止无意回退。

## 14. 本地安全要求

即使只绑定 localhost，也要防止浏览器中的恶意网页尝试调用本地 API：

- production 前后端同源，不开放 `*` CORS。
- dev 通过 Vite proxy 调用 API，不长期放宽 production。
- mutation 要求自定义请求头；预检只允许可信开发 origin。
- GET 无副作用，敏感读取不通过 URL query 传密钥。
- Host 只允许 localhost/127.0.0.1 和实际选定端口。
- API 不接受客户端传入任意服务器绝对路径。
- 文件上传写入受控临时目录，再走现有解析和路径围栏。
- URL 抓取继续使用现有公网 IP、重定向、大小和类型校验。
- 凭据端点只展示引用、指纹和末四位。
- 前端错误上报只保留非正文元数据，本项目不默认接入外部遥测。
- 开发者接口由服务端环境变量判断，不接受前端传 `developer=true` 解锁。
- 静态资源设置 CSP；不允许 CDN、任意 iframe 和远程脚本。

## 15. 性能与可访问性预算

### 15.1 前端性能预算

在参考开发机和本地服务中：

- 后端 ready 后，冷加载基础 Shell 到可交互目标 p95 不超过 2 秒。
- 初始 Shell JS + CSS gzip 目标不超过 350 KiB；编辑器、图谱和开发工具按 route lazy-load。
- 不在 bootstrap 加载全部故事资产、知识或任务 steps。
- 10,000 条知识仍使用服务端分页和前端虚拟列表。
- 对话只保留视口附近消息 DOM；历史按游标加载。
- Token delta 每 30–60ms 合并渲染，不逐 Token 重排整个页面。
- 长正文编辑器在 200,000 字符夹具上输入和滚动无明显阻塞；若达不到，必须虚拟化或更换编辑器方案。
- 关系图、diff 和 Markdown 预览按需加载。
- 所有列表请求可取消，快速切换筛选时旧响应不得覆盖新响应。

### 15.2 后端/API 性能预算

- health/live 不访问所有项目数据库。
- bootstrap 不执行向量构建或全文扫描。
- 已有知识中心 10,000 条搜索 p95 < 300ms 目标继续保持。
- 普通列表默认 20–50 条，上限由 API 固定。
- 单条知识保存事务反馈目标 < 500ms；后台索引状态异步更新。
- SSE 心跳频率避免无意义高 CPU 和日志洪泛。

### 15.3 可访问性

- 目标 WCAG 2.2 AA 的适用条款。
- 所有操作可通过键盘到达；焦点顺序与视觉顺序一致。
- Dialog/Drawer 有焦点圈定、Escape 和焦点返回。
- 状态不只靠颜色；错误、风险和进度有文字。
- 正文与 UI 对比度达标。
- 图标按钮有名称；表单错误关联字段。
- 支持 200% 缩放下的核心创作。
- 尊重 reduced motion。
- 中文输入法组合事件列入自动测试。

## 16. 构建、依赖与版本策略

### 16.1 Python

- `requirements.txt` 保存运行时依赖：FastAPI、Uvicorn、上传所需库等。
- 测试和构建依赖进入明确的开发依赖文件，不膨胀便携 runtime。
- Streamlit 在兼容窗口保留，VF-8.5 后移除。
- Python 命令继续使用 `.\.venv\Scripts\python.exe`。

### 16.2 Node

- 使用 npm 和提交的 `package-lock.json`。
- 开发安装 `npm --prefix frontend install`；CI/发布只使用 `npm ci`。
- 禁止提交 `node_modules` 和 `dist`。
- 依赖升级单独提交，附 typecheck、unit、e2e 或兼容说明。
- production 不从 CDN 拉取依赖。

### 16.3 建议前端命令

```powershell
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test:unit
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

### 16.4 开发启动

推荐两个进程：

```powershell
.\.venv\Scripts\python.exe -m uvicorn novelforge.api.app:create_app --factory --host 127.0.0.1 --port 8501
npm --prefix frontend run dev
```

Vite dev server只代理 `/api`，不直接访问 data。生产/便携版只有 FastAPI 一个服务进程。

## 17. 迁移兼容与回滚

### 17.1 兼容窗口

兼容期间：

- 默认启动方式在 VF-8.3 前仍可保持 Streamlit。
- Vue beta 通过显式启动选项进入。
- 两者读取相同 schema 和业务资产，不双写第二套数据。
- 同一 data root 同时只允许运行一个应用进程。
- migration 16 一旦应用，旧 v0.7.1 代码会因数据库版本过高拒绝打开；因此首次 beta 升级前必须明确备份和版本兼容说明。

### 17.2 回滚层级

1. **前端页面回滚**：route feature flag 切回 Streamlit，不回滚数据库。
2. **API feature 回滚**：保持 schema 和服务门面，关闭对应 Vue route。
3. **发布回滚**：只能回到理解当前 schema 的兼容版本；不能用旧二进制强开新 schema。
4. **数据回滚**：不提供自动降级 migration；使用升级前完整 data 备份恢复。

### 17.3 每阶段备份要求

- schema 16 上线前备份 global.db、所有 project.db 和文件资产。
- 项目副本测试必须使用受控复制，不在真实项目上跑 destructive E2E。
- 发布包测试使用新临时目录。

## 18. 风险清单

| 风险 | 典型表现 | 处理方式 |
| --- | --- | --- |
| 只换技术不改信息架构 | Vue 页面仍是四层标签和大表单 | VF-0.4 先验收两个独立 Layout |
| UI 内隐藏业务逻辑遗漏 | Vue 与 Streamlit 生成或保存结果不同 | VF-0.2 调用矩阵，先下沉后 API 化 |
| API 暴露原始 dict | 字段漂移、内部路径或密钥泄露 | Pydantic DTO、response filter、契约测试 |
| 双进程调度器 | 同一任务多次领取或重复 prime | launcher 单实例、lifespan owner、禁止并行 UI |
| SSE 断线误判失败 | 生成仍在运行但页面显示丢失 | operation 状态查询、sequence 和重连 |
| 浏览器刷新丢草稿 | 长篇编辑内容丢失 | namespaced draft、hash 冲突和 DirtyGuard |
| 多标签覆盖 | 旧页面保存覆盖新内容 | expected_revision/hash，HTTP 409 |
| 模式只存在前端 | API/上下文仍按另一模式工作 | schema 16 + domain policy |
| 模式切换丢资产 | 隐藏入口被误实现为删除 | 无损切换验证和资产计数前后对比 |
| 两套 UI 复制业务代码 | 修复只落在一套界面 | 共享 API/composable/primitives，不共享 Layout |
| 组件库默认风格仍丑 | 变成普通后台管理界面 | headless primitives + 自有 Token + 原型验收 |
| 长文本编辑器选型错误 | 中文 IME、撤销或大文档卡顿 | VF-0.3 spike + 200k 字符基准 |
| 任务状态高频轮询 | SQLite 和前端持续高负载 | SSE 通知 + 低频权威刷新 |
| Node 增加用户负担 | 便携版要求安装 npm | Node 仅构建时，发布只携 dist |
| 本地 API 被网页探测 | 恶意网页触发写操作 | 同源、无通配 CORS、自定义 mutation header |
| 测试污染真实数据 | E2E 创建/删除用户项目 | 可注入 data root、前缀和路径围栏 |
| 迁移无限延长 | 永久维护两套 UI | 阶段门、能力矩阵和 VF-8.5 下线条件 |
| 视觉回归不稳定 | 字体/时间/动画导致截图抖动 | 本地字体、固定时区、禁动画、稳定假数据 |

## 19. 每个任务的交付格式

```text
任务：VF-X.Y

结果：完成 / 部分完成 / 阻塞

修改：
- 文件：做了什么

契约：
- API/schema/route/状态语义是否变化
- 如何保持 SQLite、资产和工作流不变量

验证：
- 命令：通过 / 失败 / 未运行及原因
- 是否使用 stub，是否产生外部费用

兼容与回滚：
- Streamlit 回退是否仍可用
- 是否需要备份或升级说明

剩余风险：
- 只列当前任务未消除的风险

建议下一步：
- 只能指向本规划中的直接后继任务
```

禁止只报告“页面已经能打开”；涉及生成、保存或任务控制时必须验证数据结果、幂等、失败和刷新恢复。

## 20. 最终完成定义

只有同时满足以下条件，才能宣布 Vue 迁移完成并执行 VF-8.5：

### 产品

- 新故事明确选择 planned 或 conversational。
- 两种模式拥有独立 Layout、路由和导航。
- 规划界面不显示自由模式入口；对话界面不显示规划功能。
- 同一项目可以混合两种故事。
- 模式切换无损，已有资产数量和内容不变。
- 两种界面都能访问适合自身交互的资料、设置、任务和用量。

### 功能

- 规划全链路达到现有能力级。
- 对话消息、片段、动作、附件、记忆和章节保存达到现有能力级。
- 知识、来源、修订、审核、实体、导入和研究达到现有能力级。
- 模型能力、降级、预估、费用和凭据行为不退化。
- 后台任务跨页面、刷新和应用重启可恢复。

### 数据

- SQLite 和文件资产权威边界不变。
- schema 连续，旧数据库升级测试通过。
- 没有第二套知识、来源、附件、会话或任务存储。
- 所有危险写入、并发覆盖和模式切换有测试。
- 旧项目抽样升级后内容 hash、修订链和资产计数符合预期。

### 前端质量

- TypeScript strict、lint、unit、e2e 和 visual 通过。
- 满足性能预算和核心可访问性要求。
- 1440/1280/1024/768 视口关键流程可用。
- 中文输入法、长正文、长会话和大资料库通过专项验证。
- production 无远程 CDN 和 Node runtime 依赖。

### 发布

- launcher 单实例、端口冲突、ready、日志和浏览器打开通过。
- Windows 便携包在干净环境启动并完成核心旅程。
- build_release 和包结构验证包含 Vue dist。
- README、README.en、project.md、storage_architecture.md 和发布说明与实际一致。
- Streamlit 至少经过一个明确兼容窗口后才移除。

满足以上全部条件后，NovelForge 的正式架构才从“Streamlit 应用”转变为“Vue 双界面 + FastAPI 本地服务”。

## 21. 2026-08-20 执行审计

本轮已实际执行并通过：

- `npm run typecheck`、`npm run test:unit`（5 tests）、`npm run build`。
- `npm run test:e2e`（16 tests：8 个场景 × Chromium + Edge，包含双 Layout/模式入口 Axe、移动无溢出、1440/1280/1024/768 视口、键盘、刷新、reduced-motion、组合输入保护、8,000 次长草稿）。
- `tools.verify_api_smoke`、`tools.verify_structure_validation`、OpenAPI export/check、Vue build/package/layout 验证。
- Python 核心回归：creation modes、context assembly、interactive writing、creative actions/attachments、web research、capability orchestration、knowledge/entity、ingestion workbench/tasks/runtime/recovery、review regressions、DB-first/DB authority/delete/copy/no-mirror、retrieval hardening/quality、workflow guards、launcher guards 等；需要凭据的隔离验证使用 `NOVELFORGE_CREDENTIAL_BACKEND=memory` fixture，未调用真实模型或真实网络。
- `tools.verify_large_knowledge_search` 已用真实 SQLite/FTS 写入 10,000 条知识并测得本次搜索 p95 179.0ms（中位数 154.4ms），满足 300ms 后端预算。
- `tools.verify_legacy_db_upgrade` 已从 schema 15 旧库升级到 schema 16，确认故事默认 `planned`、资产相对路径与内容 hash 保持、重复启动幂等，并确认未来 schema 17 会被拒绝。
- `tools.verify_llm_http_provider` 已用本地 OpenAI-compatible HTTP 服务验证半截 SSE 会报告连接/解析错误、下一次请求可消费完整流；这是协议夹具，不替代真实模型 provider 评测。
- `tools.verify_launcher_runtime_matrix` 已在临时隔离 root 真实启动 launcher 子进程，覆盖 ready、持久化 pid/port、已有实例复用、非 NovelForge 端口回退、停止后陈旧状态清理与重新选择默认端口。
- `.github/workflows/vue-migration-windows.yml` 已建立 Windows CI 验收入口：干净 runner 安装 Python/Node、Chromium + Edge E2E、旧库/HTTP provider 协议/launcher/10k 压力/API smoke；真实 provider stream 仅在手动触发且显式配置 secrets 时运行，不会泄露凭据。
- `docs/releases/v0.7.1-clean-windows-checklist.md` 固化了无 Node 干净机、真实 provider/物理中文 IME、长会话和兼容窗口的人工签收项；在该清单取得记录前，不执行 VF-8.5。
- `tools.verify_ocr_progress_fixture` 已覆盖 3 页扫描 PDF 的逐页进度（0→100%）、低置信度告警、空页统计和页级置信度元数据；`tools.verify_ocr_api` 覆盖不落库 OCR 预览响应；fixture 不伪造真实 Tesseract/provider 可用性。
- 前端 `api.streamTurn`/`streamDiscussion` 已统一接入 operation replay：断线后按最后 SSE sequence 从 `/operations/{id}/events` 补齐，新增 Vitest fixture 通过（5 tests total）；该证据不替代真实模型长流/代理断线验收。
- `build_release.ps1 -RuntimeRoot ...` 已重建 `release/NovelForge-windows-portable-v0.7.1.zip`；包结构和包内首页、schema 16 health、bootstrap、usage breakdown、developer guard API 冒烟通过，旁车 `.sha256` 校验文件由构建脚本生成。

仍不能在本机诚实标记为最终完成的门：真实模型长流断线恢复、物理中文 IME（当前仅验证 composition 事件保护）与真实用户会话压力、超大资料交互压力、真实 OCR/provider 评测、干净 Windows 权限/浏览器打开/无 Node 矩阵，以及兼容窗口结束后的 VF-8.5 Streamlit 删除。临时 root 的 launcher 端口/已有实例/重启路径已有证据，但不能替代干净机矩阵。以上门必须在相应发布/CI 环境取得证据后再执行删除操作。
