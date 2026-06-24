# app.py 可持续拆解规划

目标：在不改变现有用户流程的前提下，把 `app.py` 从单体 Streamlit 页面逐步拆成清晰、可验证、可继续扩展的模块。

## 当前执行状态

截至本轮拆解，`app.py` 已经收缩为入口、路由和少量兼容函数。页面渲染、共享 UI 组件、流式预览、资料导入、检索中心、项目设置和写作/评价工作台已经迁移到 `ui/` 包。

后续继续拆解时应把重点放在页面内部的重复组合逻辑，而不是继续扩大 `app.py` 的职责。

## 执行原则

- 每一批只拆一个稳定边界，优先选择低耦合、高复用、行为可直接验证的代码。
- 每一批完成后必须运行语法检查和关键模块导入检查；发现问题当批修复。
- 审查或验证单项任务运行接近 10 分钟时，先停下检查是否卡住，再决定继续、缩小范围或换验证方式。
- 不在拆分过程中重写业务逻辑；除非发现明确 bug，否则只做等价迁移。
- 页面级大函数拆分时，先抽出纯渲染/状态 helper，再拆事件处理，最后拆整页入口。

## 阶段 1：基础 UI 层

目标：先移走低耦合 UI 基础设施，让后续页面模块可以复用。

计划模块：

- `ui/layout.py`：全局 CSS、页面头部和布局样式。
- `ui/labels.py`：状态、来源、检索、知识分类等中文标签映射。
- `ui/common.py`：通用按钮、session key、整数指标、批次进度回调等。
- `ui/step_views.py`：步骤状态、JSON 展开、检索使用报告和检索结果展示。
- `ui/retrieval_views.py`：检索证据和召回结果展示。

验收：

- `app.py` 只从这些模块导入基础 UI 函数。
- 样式、标签、步骤展示行为不变。
- 源码内存编译或 `py_compile` 覆盖拆出的模块和 `app.py`。
- 导入 `app` 不报错。

## 阶段 2：讨论与生成共用组件

目标：把全书、分卷、剧情段、章节、创作配置中重复的讨论 UI 和 artifact 审批逻辑抽成共用模块。

计划模块：

- `ui/discussion.py`：讨论消息 key、聊天渲染、总结渲染、审批 artifact 展示。
- `ui/discussion_assets_panel.py`：素材和设定 guardrail 问题展示、替换目标选择、候选格式化。
- `ui/streaming.py`：生成过程的实时预览、停止按钮和取消异常。

验收：

- 各讨论页面只保留页面特有的参数装配和保存逻辑。
- 继续讨论、首次讨论、审批写入的 session 行为不变。
- 主要生成动作仍通过 `stream_callback` 在页面内逐步显示输出。

## 阶段 3：资料导入工作台

目标：拆出目前最重的资料导入、长篇批次、来源台账和质量面板。

计划模块：

- `ui/retrieval_ingestion_page.py`：资料导入入口、粘贴资料整理和结构化知识提取。
- `ui/long_reference_importer.py`：长篇导入向导。
- `ui/long_reference_batch.py`：长篇批次管理、继续处理、重提取和整理。
- `ui/knowledge_management.py`：pending 队列、质量面板、自动审查策略、审查记录、来源台账和来源包报告。
- `ui/retrieval_eval_panel.py`：检索评估面板。

验收：

- 长篇文本导入、批次继续处理、失败重试、批次整理入口仍可工作。
- 流式预览回调仍能传递到 `source_workflows.py`。

## 阶段 4：规划页面

目标：拆出全书、分卷、剧情段、章节细纲相关页面。

计划模块：

- `ui/outline_page.py`：全书大纲。
- `ui/volume_outline_page.py`：分卷大纲。
- `ui/arc_outline_page.py`：剧情段大纲。
- `ui/chapter_outline_page.py`：章节细纲。
- `ui/creative_profile_page.py`：创作配置页和相关表单状态。

验收：

- 讨论、继续讨论、生成正式大纲、保存 artifact 的行为不变。
- 章节细纲仍能正确读写故事空间、卷、剧情段和检索上下文。

## 阶段 5：写作与评价页面

目标：拆出正文生成、快速生成和章节评价，进一步隔离流式生成流程。

计划模块：

- `ui/chapter_page.py`：正文生成和流水线页面。
- `ui/dynamic_generation.py`：快速生成 playground。
- `ui/evaluation.py`：章节评价页面和综合评价入口。

验收：

- “仅生成细纲”“完整流水线”“写正文”“审阅正文”“提炼设定”等按钮仍能流式输出。
- 停止生成仍按当前合作式取消逻辑生效。

## 阶段 6：项目、设置、资源与检索中心

目标：拆出剩余较稳定页面，并让 `app.py` 退化成入口和路由。

计划模块：

- `ui/project_overview.py`
- `ui/settings_page.py`
- `ui/llm_settings.py`
- `ui/resource_management.py`
- `ui/retrieval_center_page.py`
- `ui/app_shell.py`
- `ui/navigation.py`
- `ui/rules_page.py`
- `ui/prompt_options_page.py`
- `ui/prompt_option_tools.py`
- `ui/resource_browser_state.py`

验收：

- `app.py` 只保留导入、初始化、页面路由和少量兼容代码。
- 每个页面模块可以独立导入。

## 持续审查清单

- 是否存在从新模块反向导入 `app.py` 的循环依赖。
- 是否把业务存储逻辑误放进 UI 模块。
- 是否改变了 Streamlit widget key，导致用户已有 session 状态丢失。
- 是否吞掉 `GenerationCancelled` 这类需要继续传播的取消异常。
- 是否让流式生成回退成一次性输出。
- 是否引入未使用或重复导入，导致后续维护成本上升。
