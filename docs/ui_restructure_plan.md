# NovelForge UI 精简实施规划

> 文档用途：本文件是后续 UI 精简工作的唯一实施路线图，适合把单个任务编号直接交给 Luna 等代码模型执行。
>
> 当前基线：`9670d1f feat: 统一知识库并精简创作界面`
>
> 更新原则：每完成一个任务，只更新该任务的状态、实际改动和验证结果，不重新解释或改写未执行任务。

## 0. 如何使用这份规划

后续实现必须按任务编号逐项推进。一次只交给模型一个任务，例如 `UI-2.1`，不要用“一次完成所有 UI 重构”作为提示词。每个任务都应形成可独立验证、可独立回退的改动。

执行单个任务前，模型必须：

1. 完整阅读 `project.md` 和本文件。
2. 运行 `git status --short`，保留用户已有改动，不覆盖无关文件。
3. 阅读任务列出的关键文件及其直接依赖。
4. 确认前置任务已经完成；未完成时停止并报告，不跳步实现。
5. 只修改当前任务授权的范围；发现相邻问题时记录到交付说明，不顺手扩大改动。
6. 使用 `apply_patch` 修改源码，不使用脚本重写用户文件。
7. 运行任务要求的验证，并报告通过项、失败项和未执行项。
8. 未经用户明确要求，不自动提交、推送或删除兼容代码。

推荐给 Luna 的通用提示词：

```text
阅读 project.md 和 docs/ui_restructure_plan.md，执行其中任务 <任务编号>。
严格遵守任务的范围、前置条件、不变量、文件清单、验收标准和验证命令。
先检查 git 状态并保护已有改动；只实现这个任务，不提前实现后续任务。
完成后说明修改了什么、为什么、运行了哪些验证、还有什么风险。不要自行提交。
```

## 1. 当前状态

### 1.1 已完成：第一阶段“入口隐藏”

提交 `9670d1f` 已完成以下工作：

- 普通侧栏从 16 个页面缩减为 11 个页面。
- 普通侧栏隐藏“内容管理、资料检索、独立章节审阅、生成规则、提示词选项”。
- 内容管理可由项目指标按需打开。
- 快速审阅和综合审阅已经进入章节写作流程。
- 生成规则和写作偏好可由“模型与费用”的高级入口打开。
- `NOVELFORGE_DEVELOPER_MODE=1` 仍可在设置内部启用开发工具；旧完整侧栏不再作为普通导航恢复。
- 旧页面名、旧会话状态和按需打开页面仍由兼容路由处理。

### 1.2 当前技术事实

四入口合并已经落地，旧页面 renderer 仍作为兼容和 Hub 内部实现保留：

- `ui/navigation.py` 提供四个顶层入口、旧路由意图映射和普通/开发者模式回退规则。
- `ui/app_shell.py` 只渲染一个顶层侧栏导航；旧 `pending_nav_page` 只由兼容消费器读取。
- `app.py` 只分发工作台、创作、资料库、设置四个 Hub。
- 新跳转统一写入 `pending_navigation_intent`，Hub 和子视图状态继续按项目/故事作用域隔离。
- 项目资源、知识库、资料导入、规划、正文、设置页面由 Hub 按当前视图懒加载，不复制领域逻辑或数据。
- 资料检索、索引维护、质量评测只在开发者模式的设置/开发工具中出现；普通模式的旧检索中心意图回退到资料库搜索。

### 1.3 剩余阶段

| 阶段 | 目标 | 状态 |
| --- | --- | --- |
| 第一阶段 | 隐藏重复和高级入口 | 已完成 |
| 第二阶段 | 合并为工作台、创作、资料库、设置四个入口 | 已完成 |
| 第三阶段 | 清理内部重复流程、旧路由和误导文案 | 已完成 |
| 第四阶段 | 视觉、响应式和可访问性打磨 | 已完成（基础版） |

第二、第三阶段完成后，功能结构即达到正式可用状态。第四阶段只改善视觉品质，不是功能发布前置条件。

## 2. 最终目标与不变量

### 2.1 最终用户导航

项目存在时，侧栏只显示四个稳定入口：

| 顶层入口 | 默认视图 | 内部视图 | 主要职责 |
| --- | --- | --- | --- |
| 工作台 | 概览 | 概览、内容、项目与故事 | 判断进度、继续任务、查找已有产物 |
| 创作 | 章节写作或推荐下一步 | 创作方向、小说规划、章节写作、自由模式 | 从方向到规划再到正文创作 |
| 资料库 | 查找与编辑 | 查找与编辑、优先设定、待审核、导入与来源 | 管理原文资料与正式知识 |
| 设置 | 模型与费用 | 模型与费用、高级创作、开发工具 | 配置模型、规则、偏好和诊断工具 |

没有项目时只显示“设置”，同时保留侧栏的“新建项目”入口。

### 2.2 最终页面结构

```text
工作台
├─ 概览
├─ 内容
└─ 项目与故事

创作
├─ 创作方向
├─ 小说规划
│  ├─ 全书
│  ├─ 分卷
│  ├─ 剧情段
│  └─ 章节细纲
├─ 章节写作
│  ├─ 章节需求
│  ├─ 写作正文
│  └─ 保存与审阅
└─ 自由模式

资料库
├─ 查找与编辑
├─ 优先设定
├─ 待审核
│  └─ 高级：审核策略、处理记录
└─ 导入与来源
   ├─ 概览
   ├─ 导入
   ├─ 处理
   └─ 管理

设置
├─ 模型与费用
├─ 高级创作
│  ├─ 生成规则
│  └─ 写作偏好
└─ 开发工具（仅开发者模式）
   ├─ 资料检索诊断
   ├─ 质量评测
   └─ 索引维护
```

### 2.3 必须保持不变的能力

UI 重构不得改变以下行为：

- 项目、故事、章节、资料、知识、规则、提示词选项和运行记录的存储结构。
- 当前数据库 schema、migration 顺序和软删除语义。
- 大纲、正文、自由创作、审阅、资料导入和网络研究工作流。
- 统一上下文装配、知识检索、优先设定和待审核知识的语义。
- 一个模型 API Key 支撑生成，模型原生联网优先、免密通用搜索降级的能力策略。
- 后台资料任务、网络研究任务和知识索引任务的生命周期。
- Token/费用预估、用量记录和超阈值确认。
- 项目与故事切换后的状态隔离。
- 旧项目数据的可读性和旧会话状态的兼容跳转。

### 2.4 本次明确不做

- 不改成 Vue、React 或其它前端框架。
- 不新增数据库表或迁移。
- 不重写 LLM prompt、RAG、网络搜索或工作流实现。
- 不为了 UI 命名统一而批量重命名后端 `core_*`、`setting_role=core` 等兼容字段。
- 不删除历史数据、项目文件、来源修订或审阅报告。
- 不把所有旧页面源码一次性删除；先完成替代和验证，再逐步清理。
- 不同时进行大规模视觉换肤，避免结构问题和样式问题混在同一批改动中。

## 3. 导航与状态设计

### 3.1 顶层路由常量

最终只保留四个用户路由：

```python
TOP_LEVEL_PAGES = ["工作台", "创作", "资料库", "设置"]
DEFAULT_PAGE = "工作台"
```

页面标签、图标和说明继续集中在 `ui/navigation.py`。普通模式和开发者模式使用相同四个顶层页面；开发者模式只在“设置”内部多显示“开发工具”，不再恢复 16 个侧栏入口。

### 3.2 导航意图

不得继续让调用方直接同时修改 `active_page` 和多个页面 widget key。新增统一的“导航意图”，最小结构如下：

```python
{
    "version": 1,
    "page": "创作",
    "view": "小说规划",
    "subview": "章节细纲",
    "payload": {"chapter_no": 12},
}
```

推荐状态键：

- `pending_navigation_intent`：下一次 rerun 前消费一次。
- `active_page`：只保存四个顶层页面之一。
- `workbench_hub_view_<scope>`：概览、内容、项目与故事。
- `creation_hub_view_<scope>`：创作方向、小说规划、章节写作、自由模式。
- `creation_planning_view_<scope>`：全书、分卷、剧情段、章节细纲。
- `library_hub_view_<scope>`：查找与编辑、优先设定、待审核、导入与来源。
- `settings_hub_view`：模型与费用、高级创作、开发工具。
- `settings_advanced_view_<scope>`：生成规则、写作偏好。
- `settings_developer_view_<scope>`：资料检索、质量评测、索引维护。

除全局模型设置外，所有状态键必须使用 `scoped_widget_key` 绑定项目和故事。导航意图必须在对应 `segmented_control` 或 `radio` 创建之前消费，避免 Streamlit 抛出“widget 创建后不能修改 session_state”的异常。

### 3.3 兼容映射

所有旧页面名必须映射到新的顶层页面和内部视图：

| 旧页面或别名 | 新顶层页面 | 新内部视图 | 额外状态 |
| --- | --- | --- | --- |
| 项目总览 | 工作台 | 概览 | 无 |
| 项目资源、资源浏览器 | 工作台 | 内容 | 保留 `resource_browser_focus` |
| 创作配置 | 创作 | 创作方向 | 无 |
| 生成大纲 | 创作 | 小说规划 / 全书 | 保留原全书大纲内部状态 |
| 分卷大纲 | 创作 | 小说规划 / 分卷 | 保留卷号和原页面状态 |
| 剧情段大纲 | 创作 | 小说规划 / 剧情段 | 保留剧情段和章节分配状态 |
| 生成细纲 | 创作 | 小说规划 / 章节细纲 | 保留章节号 |
| 正文生成 | 创作 | 章节写作 | 保留 `chapter_page_view` |
| 章节审阅、章节评价 | 创作 | 章节写作 | 将 `chapter_page_view` 指向“3 · 保存与审阅” |
| 自由创作、快速生成 | 创作 | 自由模式 | 保留当前自由创作会话 |
| 知识库、设定、核心设定 | 资料库 | 查找与编辑 | 默认打开统一搜索 |
| 优先设定 | 资料库 | 优先设定 | 无 |
| 待审核设定、待审核知识 | 资料库 | 待审核 | 默认打开审核队列 |
| 资料导入、资料录入 | 资料库 | 导入与来源 | 保留资料工作区状态 |
| 模型配置 | 设置 | 模型与费用 | 保留 `llm_settings_view` |
| 生成规则 | 设置 | 高级创作 / 生成规则 | 无 |
| 提示词选项 | 设置 | 高级创作 / 写作偏好 | 无 |
| 检索中心 | 设置 | 开发工具 / 资料检索 | 普通模式回退到资料库并显示一次迁移说明 |

兼容逻辑至少保留一个正式版本周期。只有当代码搜索确认没有调用方再写入旧页面名，且兼容测试覆盖全部映射后，才允许进入删除任务。

### 3.4 导航 API

保留 `navigate_to(page)` 作为兼容门面，但新增明确 API：

```python
def navigate_to_target(
    page: str,
    *,
    view: str | None = None,
    subview: str | None = None,
    payload: dict | None = None,
) -> None:
    ...
```

规则：

- 新代码只调用 `navigate_to_target`。
- 旧代码调用 `navigate_to("项目资源")` 时，由兼容层生成新意图。
- `payload` 只携带短期定位信息，不保存正文、密钥或大对象。
- 意图消费后必须 `pop`，不能在后续 rerun 重复执行。
- 未知页面或未知视图必须记录 warning，并回退到安全默认页，不能静默丢弃。

## 4. 第二阶段：合并为四个入口

第二阶段分为六个独立任务。每个任务完成时应用都必须可启动，不能留下“导航已经切换、目标 Hub 尚不存在”的中间状态。

### UI-2.1：建立新导航契约，但暂不切换界面

状态：`已完成`

实际完成：新增四入口常量、旧路由到 Hub 意图映射、一次性意图消费和项目/故事作用域迁移；`verify_navigation_contract.py` 覆盖普通、开发者、无项目和旧路由场景。

目标：实现四入口常量、导航意图和完整旧路由映射，同时继续使用当前 11 页面普通导航，先把迁移逻辑验证稳定。

前置条件：第一阶段提交 `9670d1f` 已存在，工作区无未确认的导航改动。

关键文件：

- `ui/navigation.py`
- `ui/common.py`
- `ui/app_shell.py`
- `tools/verify_ui_restructure.py`
- 建议新增 `tools/verify_navigation_contract.py`

实施步骤：

1. 在 `ui/navigation.py` 增加四入口常量、允许的 Hub 视图和纯函数映射表。
2. 映射函数只接收普通 Python 数据，不导入 Streamlit，便于独立测试。
3. 在 `ui/common.py` 增加 `navigate_to_target`；旧 `navigate_to` 调用映射函数生成意图。
4. 在 `ui/app_shell.py` 增加意图消费器，但暂时仍可把意图翻译回旧页面，以保持现有界面不变。
5. 对未知版本、未知 page、未知 view 增加显式日志和安全回退。
6. 覆盖项目不存在、项目存在、故事切换、开发者模式四种上下文。
7. 为映射表中的每一行增加确定性测试。

验收标准：

- 旧 `navigate_to` 调用全部继续工作。
- 同一个意图只消费一次。
- 16 个旧页面和历史别名都有测试。
- 切换项目或故事后不会复用上一个作用域的 Hub 子视图。
- 未知意图不会导致空白页或 `IndexError`。
- 当前普通导航视觉不发生变化。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py ui tools
.\.venv\Scripts\python.exe tools\verify_navigation_contract.py
.\.venv\Scripts\python.exe tools\verify_ui_consistency.py
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
git diff --check
```

建议提交：`refactor(ui): 建立四入口导航契约`

### UI-2.2：创建四个 Hub 壳层并切换侧栏

状态：`已完成`

实际完成：新增工作台、创作、资料库、设置四个 Hub，`app.py` 收口为四个顶层分支，侧栏改为单层四入口。

目标：侧栏真正只显示工作台、创作、资料库、设置；Hub 内部先复用旧页面渲染函数，不在本任务重写页面内容。

前置条件：`UI-2.1` 完成。

建议新增文件：

- `ui/workbench_hub.py`
- `ui/creation_hub.py`
- `ui/library_hub.py`
- `ui/settings_hub.py`

需要修改：

- `app.py`
- `ui/app_shell.py`
- `ui/navigation.py`
- `tools/verify_ui_restructure.py`
- `tools/verify_ui_consistency.py`

实施步骤：

1. 每个 Hub 只负责内部视图选择和调用已有 renderer，不包含领域规则。
2. Hub 接收 `_reload_live_ui_modules()` 返回的当前模块映射，避免热重载后持有旧函数引用。
3. `_reload_live_ui_modules()` 增加四个 Hub 模块，并保持现有页面模块的重载顺序。
4. `app.py` 的主分发收敛为四个顶层分支。
5. `ui/app_shell.py` 将两层“工作区/页面”单选改成一个顶层导航控件。
6. 普通模式和开发者模式都只显示四个顶层入口。
7. 没有项目时只显示设置；新建项目成功后进入工作台概览。
8. Hub 内部使用 `segmented_control`，默认值必须只在 key 尚不存在时提供。
9. 旧 `active_page` 如果是旧页面名，首次运行时通过兼容映射落到正确 Hub。
10. 页面标题和页头必须显示用户看到的 Hub/内部视图名称，不显示旧内部路由名。

验收标准：

- 项目存在时侧栏正好四个页面，没有第二层页面单选。
- 没有项目时“设置 → 模型与费用”仍可使用。
- 16 个旧页面仍能通过兼容意图打开对应内容。
- `app.py` 不再有 16 个顶层 `elif page ==`。
- Streamlit 热重载测试通过。
- 不产生重复 widget key。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py ui tools
.\.venv\Scripts\python.exe tools\verify_navigation_contract.py
.\.venv\Scripts\python.exe tools\verify_ui_restructure.py
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
git diff --check
```

建议提交：`refactor(ui): 切换为四入口工作区`

### UI-2.3：合并工作台与内容管理

状态：`已完成`

实际完成：工作台包含概览、内容、项目与故事；首页指标、资源浏览器和快捷操作均改为工作台/内容意图。

目标：将项目总览和项目资源变成工作台内部视图，保证项目指标可以直接定位内容。

前置条件：`UI-2.2` 完成。

关键文件：

- `ui/workbench_hub.py`
- `ui/project_overview.py`
- `ui/resource_management.py`
- `ui/resource_browser_state.py`
- `ui/app_shell.py`

实施步骤：

1. 工作台提供“概览、内容、项目与故事”三个视图。
2. “概览”继续调用 `render_project_overview_page`。
3. “内容”继续调用 `render_resource_management_page`。
4. `navigate_to_resource_browser` 改为导航到“工作台 / 内容”，继续传递来源类型、搜索词和首项定位。
5. 确认 `resource_browser_focus` 在 Hub 控件渲染前已经设置，在内容页消费后清除。
6. 首页指标、报告数量和章节数量链接全部验证能打开正确筛选结果。
7. 将 `settings_page.py` 中故事管理逻辑提取为公开 renderer，放入独立小模块或工作台组件；不要从 Hub 调用私有下划线函数。
8. 侧栏继续保留故事快速切换和新故事入口；“项目与故事”只负责完整管理、复制、重命名和项目维护。
9. 删除首页“查找项目内容”等已被指标替代的重复按钮。
10. 危险操作仍要求项目名确认，并保留隔离删除语义。

验收标准：

- 侧栏没有“内容管理”。
- 任一非零项目指标点击后进入工作台内容视图并选中正确类型。
- 没有匹配资源时显示明确空状态，用户可以返回概览。
- 故事管理不再出现在知识库。
- 项目和故事切换不会串用筛选状态。

相关验证：

```powershell
.\.venv\Scripts\python.exe tools\verify_ui_restructure.py
.\.venv\Scripts\python.exe tools\verify_db_authority_and_copy.py
.\.venv\Scripts\python.exe tools\verify_story_copy_mirrors.py
.\.venv\Scripts\python.exe tools\verify_story_path_safety.py
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
```

建议提交：`refactor(ui): 合并工作台与内容管理`

### UI-2.4：合并资料导入与知识库

状态：`已完成`

实际完成：资料库覆盖查找编辑、优先设定、待审核和导入来源，导入任务状态保持原 scoped key；普通模式不展示检索诊断。

目标：形成单一“资料库”入口，先保证旧知识库和资料导入完整可用，再为第三阶段的内部扁平化做准备。

前置条件：`UI-2.2` 完成；可与 `UI-2.3` 独立开发，但合并时必须以最新导航契约为准。

关键文件：

- `ui/library_hub.py`
- `ui/settings_page.py`
- `ui/retrieval_ingestion_page.py`
- `ui/knowledge_management.py`
- `ui/knowledge_center.py`
- `ui/entity_experience.py`
- `ui/long_reference_importer.py`
- `ui/long_reference_batch.py`

实施步骤：

1. 资料库 Hub 初始提供“知识库、导入与来源”两个壳层视图。
2. “知识库”调用现有 `render_settings_page`；“导入与来源”调用现有资料导入 renderer。
3. 旧“知识库、优先设定、待审核知识”导航意图需要设置现有知识库 scoped state。
4. 旧“资料导入”导航意图需要保留 `概览/导入/处理/管理` 状态。
5. 所有资料导入页中的“前往知识库”改用新导航意图。
6. 长篇批次、后台任务完成后的跳转必须进入资料库正确视图。
7. 不复制知识审核或资料管理代码；Hub 只做分发。
8. 资料库默认进入知识库的“统一搜索”，不是内部“知识条目”列表。
9. 普通页面不得提供检索质量评测或索引重建入口。
10. 自动索引和生成时检索保持后台自动调用，不因页面合并改变。

验收标准：

- 资料库单一入口覆盖导入、处理、来源、知识、角色视图、优先设定和待审核知识。
- 原有长篇资料批次状态可以继续恢复。
- 知识确认、丢弃、修订恢复和索引同步行为不变。
- 普通用户看不到“检索中心”。
- 不产生第二套原文或知识存储。

相关验证：

```powershell
.\.venv\Scripts\python.exe tools\verify_ingestion_knowledge_upgrade.py
.\.venv\Scripts\python.exe tools\verify_confirmed_knowledge_atomicity.py
.\.venv\Scripts\python.exe tools\verify_ingestion_workbench.py
.\.venv\Scripts\python.exe tools\verify_ingestion_ui_guards.py
.\.venv\Scripts\python.exe tools\verify_knowledge_center.py
.\.venv\Scripts\python.exe tools\verify_entity_experience.py
.\.venv\Scripts\python.exe tools\verify_ui_restructure.py
```

建议提交：`refactor(ui): 合并资料导入与知识库`

### UI-2.5：合并规划、章节写作与自由模式

状态：`已完成`

实际完成：创作 Hub 提供创作方向、小说规划、章节写作、自由模式；规划四阶段使用内部导航，章节审阅继续收口在章节写作第三步。

目标：将七个创作相关侧栏页面合并为“创作”Hub，同时保持各页面已有的生成、保存、审阅和状态恢复能力。

前置条件：`UI-2.2` 完成。

关键文件：

- `ui/creation_hub.py`
- `ui/creative_profile_page.py`
- `ui/outline_page.py`
- `ui/volume_outline_page.py`
- `ui/arc_outline_page.py`
- `ui/chapter_outline_page.py`
- `ui/chapter_page.py`
- `ui/chapter_review_panel.py`
- `ui/evaluation.py`
- `ui/free_writing/`

实施步骤：

1. 创作 Hub 提供“创作方向、小说规划、章节写作、自由模式”四个一级内部视图。
2. 小说规划提供“全书、分卷、剧情段、章节细纲”二级视图。
3. 一级和二级视图只渲染当前选中的页面，不能先执行所有 renderer 再隐藏。
4. 保留各规划页现有的“输入定位、讨论、生成编辑”内部节奏。
5. 从创作方向的推荐流程跳转时，使用导航意图定位正确内部视图。
6. 章节写作继续使用当前三步结构，并把快速/综合审阅保留在第三步。
7. 旧独立章节审阅路由映射到章节写作第三步；不再渲染独立评价页面作为普通流程。
8. 如果独立评价页仍有“历史报告浏览”能力，将该部分提取为可嵌入组件，由章节写作第三步调用。
9. 自由创作改称“自由模式”，但存储中的 `creative_session`、工作流动作名和后端函数不改名。
10. 自由模式的“整理章节、提炼知识、附件资料”继续导航到新 Hub 目标。
11. 对未完成创作配置的故事，只显示非阻塞提示，不禁止用户直接写作。
12. Hub 视图选择按项目和故事隔离；章节号、卷号和剧情段选择继续沿用原页面 scoped state。

验收标准：

- 侧栏只显示一个“创作”。
- 从创作方向到各级规划、正文和自由模式均可在两次点击内到达。
- 旧 7 个创作页面名都能正确迁移。
- 保存正文后可立即执行快速或综合审阅。
- 审阅不会自动提炼知识；知识提炼仍是独立明确动作。
- 自由创作会话、候选分支和附件状态不丢失。

相关验证：

```powershell
.\.venv\Scripts\python.exe tools\verify_context_assembly.py
.\.venv\Scripts\python.exe tools\verify_review_regressions.py
.\.venv\Scripts\python.exe tools\verify_creative_actions.py
.\.venv\Scripts\python.exe tools\verify_creative_attachments.py
.\.venv\Scripts\python.exe tools\verify_interactive_writing.py
.\.venv\Scripts\python.exe tools\verify_free_writing_ui.py
.\.venv\Scripts\python.exe tools\verify_ui_restructure.py
```

说明：`verify_free_writing_ui.py` 不应要求真实 API Key。若当前脚本仍依赖外部模型，应先把 UI 路由验证与真实生成验证分开，并使用 stub，不得在验收中调用真实服务。

建议提交：`refactor(ui): 合并小说规划与写作流程`

### UI-2.6：合并设置与开发工具

状态：`已完成`

实际完成：设置 Hub 集中模型与费用、高级创作和开发工具；删除旧 `render_model_settings_page` 临时跳转，开发工具受环境变量控制。

目标：将模型、费用、规则和偏好收进单一设置 Hub；检索诊断只在开发者模式出现。

前置条件：`UI-2.2` 完成；建议在 `UI-2.4` 后执行，以便开发工具能正确回到资料库。

关键文件：

- `ui/settings_hub.py`
- `ui/llm_settings.py`
- `ui/rules_page.py`
- `ui/prompt_options_page.py`
- `ui/retrieval_center_page.py`
- `ui/retrieval_eval_panel.py`
- `ui/common.py`
- `app.py`

实施步骤：

1. 设置 Hub 普通模式提供“模型与费用、高级创作”。
2. 高级创作提供“生成规则、写作偏好”，继续调用现有 renderer。
3. 开发者模式额外提供“开发工具”，其中嵌入检索查询、质量评测和索引维护。
4. 删除 `render_model_settings_page` 底部通过按钮跳往隐藏页面的临时实现，改为 Hub 内切换。
5. 没有项目时只允许模型与费用；需要项目的高级页面显示说明而不是异常。
6. `NOVELFORGE_DEVELOPER_MODE` 只改变设置内部选项，不改变顶层导航数量。
7. 模型能力中心仍说明原生联网优先和免密通用搜索降级，不展示单独搜索 API Key。
8. 规则和偏好页面返回时保持设置 Hub，不跳到旧路由。
9. 开发工具执行重建等维护操作时继续使用确认和健康检查。
10. 普通模式收到旧“检索中心”状态时，回退到资料库并显示一次迁移说明。

验收标准：

- 普通侧栏和设置普通视图均不出现检索诊断。
- 开发者模式仍只有四个顶层入口。
- 模型配置、连接测试、费用配置、规则和偏好完整可用。
- 没有项目时不会渲染依赖项目的规则或检索工具。
- 不重新引入 Brave 或其它额外搜索 API Key。

相关验证：

```powershell
.\.venv\Scripts\python.exe tools\verify_capability_orchestration.py
.\.venv\Scripts\python.exe tools\verify_llm_currency_ui.py
.\.venv\Scripts\python.exe tools\verify_llm_preflight_ui.py
.\.venv\Scripts\python.exe tools\verify_llm_usage_ui.py
.\.venv\Scripts\python.exe tools\verify_retrieval_quality.py
.\.venv\Scripts\python.exe tools\verify_retrieval_hardening.py
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
```

建议提交：`refactor(ui): 合并设置与开发工具`

## 5. 第三阶段：流程清理与旧代码收口

第三阶段只在第二阶段六个任务全部通过后开始。目标不是继续添加功能，而是减少 Hub 内部嵌套、重复入口和兼容债务。

### UI-3.1：扁平化资料库内部结构

状态：`已完成`

实际完成：资料库改为四视图，统一搜索详情提供查看、轻量编辑、修订历史和恢复；角色视图仍是正式知识投影。

目标：把第二阶段“知识库/导入与来源”两层壳进一步整理为最终四视图结构。

关键文件：

- `ui/library_hub.py`
- `ui/settings_page.py`
- `ui/knowledge_center.py`
- `ui/knowledge_management.py`
- `ui/entity_experience.py`
- `ui/retrieval_ingestion_page.py`

实施步骤：

1. 资料库顶层改为“查找与编辑、优先设定、待审核、导入与来源”。
2. 默认打开“查找与编辑”的统一搜索，而不是知识条目清单。
3. 搜索结果提供明确的“查看、编辑、查看修订”操作。
4. 角色中心和其它创作实体改为搜索结果的视图模式或筛选，不再占独立顶层标签。
5. 待审核默认只显示审核队列；审核策略和处理记录放在同一页的高级区域。
6. 将故事管理从知识库完全移除。
7. 导入与来源继续保留概览、导入、处理、管理四个任务型视图。
8. 旧 `knowledge_library_view` 和子视图状态增加一次性迁移。

验收标准：

- 用户进入资料库后可以直接搜索、查看并进入编辑。
- “角色卡”仍是正式知识的投影视图，不产生第二套数据。
- 待审核流程最多两层，不出现“资料库 → 知识库 → 待审核 → 审核队列”四层嵌套。
- 所有知识修订和索引同步测试通过。

建议提交：`refactor(ui): 扁平化资料库工作流`

### UI-3.2：统一创作流程中的下一步动作

状态：`已完成`

实际完成：新增统一下一步动作组件，创作方向和全书/分卷/剧情段/细纲阶段按顺序导航到下一阶段。

目标：让每个创作视图只突出一个主要下一步，减少重复按钮和说明。

实施步骤：

1. 创作方向保存后，根据配置推荐一个下一步，并允许用户手动选择其它阶段。
2. 全书大纲保存后推荐分卷；分卷保存后推荐剧情段；剧情段保存后推荐章节细纲；细纲保存后推荐章节写作。
3. 推荐动作统一调用导航意图，不直接写 widget state。
4. 页面首屏只保留当前目标、当前状态和主操作。
5. 历史结果、上下文依据、提示词选项和低频参数统一放入一次展开的高级区。
6. 删除同一页面重复出现的“返回、继续、前往”按钮，只保留流程末尾的主要下一步。
7. 所有生成调用旁继续显示 Token/费用摘要。

验收标准：

- 每个创作阶段最多一个主按钮。
- 任意阶段完成后都有明确的下一步。
- 用户仍可跳过规划直接进入自由模式或章节写作。
- 不改变生成 prompt 和持久化结果。

建议提交：`refactor(ui): 统一创作流程下一步动作`

### UI-3.3：移除独立审阅与重复报告入口

状态：`已完成`

实际完成：普通应用不再加载或分发独立评价 renderer，快速/综合审阅和设定提炼均保留在章节写作审阅区；旧审阅路由仍映射到该视图。

目标：章节写作成为审阅的唯一普通用户入口，同时保留历史报告查看能力。

实施步骤：

1. 从 `ui/evaluation.py` 提取仍有价值的报告列表和报告详情组件。
2. 在章节写作第三步中统一展示快速审阅、综合审阅和历史报告。
3. 保留两种审阅模式的领域函数和数据类型。
4. 删除普通 UI 对独立评价 renderer 的调用。
5. 旧“章节审阅/章节评价”路由继续映射到章节写作第三步。
6. 确认设定提炼仍位于审阅之后的独立知识更新区域。

验收标准：

- 用户不会看到两个章节审阅入口。
- 旧审阅报告仍可按章节查看。
- 快速和综合审阅结果数量、保存和复用行为不变。

建议提交：`refactor(ui): 收口章节审阅入口`

### UI-3.4：删除过期路由与临时兼容 UI

状态：`已完成`

实际完成：产品调用方全部迁移到 `navigate_to_target`；旧 `pending_nav_page`、旧页面分组和旧 renderer 仅保留兼容映射或仍被 Hub 调用的实现。

目标：在兼容测试稳定后清理第一阶段留下的双导航结构和隐藏页返回逻辑。

允许删除或收口的内容：

- `ADVANCED_PAGE_GROUPS` 和 `PRIMARY_PAGE_GROUPS` 双结构。
- `_render_hidden_page_navigation`。
- 第一阶段设置页底部的隐藏页面跳转按钮。
- `app.py` 中旧页面顶层分发。
- 只为旧侧栏使用的页面标签、图标和分组常量。
- 已无调用方的 `pending_nav_page` 直接写入。

仍需保留：

- 旧页面名到导航意图的纯兼容映射。
- `navigate_to(page)` 兼容门面，直到代码搜索确认所有调用方已迁移。
- 原页面 renderer；只要 Hub 仍调用它们，就不能删除。
- 开发工具 renderer。

实施步骤：

1. 使用 `rg` 列出所有旧页面名和 `pending_nav_page` 写入点。
2. 将产品代码调用方迁移到 `navigate_to_target`。
3. 测试代码可继续直接构造旧意图，用于验证兼容。
4. 删除不再可达的临时 UI，不删除后端数据或工作流。
5. 更新 README、`project.md` 和本规划的状态。

验收标准：

- `app.py` 只分发四个 Hub。
- 产品代码不再直接写 `pending_nav_page`。
- 旧页面名只存在于兼容映射、迁移测试和历史文档说明中。
- 普通与开发者模式顶层入口都固定为四个。

建议提交：`refactor(ui): 清理旧页面路由兼容层`

### UI-3.5：最终回归与文档同步

状态：`已完成`

实际完成：同步 README、README.en、project.md 和本规划，补充导航契约的状态隔离及无项目测试，并更新 UI 重构验证脚本。

目标：证明 UI 合并没有改变数据和工作流语义，并把文档更新为最终状态。

必须完成：

1. 更新 `README.md`、`README.en.md`、`project.md` 和本文件。
2. 更新 `tools/verify_ui_restructure.py`，验证四 Hub 的所有内部视图。
3. 保留单独的导航兼容测试，覆盖全部旧路由。
4. 增加项目/故事切换状态隔离测试。
5. 增加无项目、普通模式、开发者模式三套导航测试。
6. 对工作台资源定位、创作下一步、知识库跳转和高级设置入口做端到端 UI 测试。
7. 运行最终验证矩阵。

最终验证矩阵：

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py novelforge storage ui tools
.\.venv\Scripts\python.exe tools\verify_package_structure.py
.\.venv\Scripts\python.exe tools\verify_navigation_contract.py
.\.venv\Scripts\python.exe tools\verify_ui_consistency.py
.\.venv\Scripts\python.exe tools\verify_ui_restructure.py
.\.venv\Scripts\python.exe tools\verify_app_smoke.py
.\.venv\Scripts\python.exe tools\verify_context_assembly.py
.\.venv\Scripts\python.exe tools\verify_review_regressions.py
.\.venv\Scripts\python.exe tools\verify_interactive_writing.py
.\.venv\Scripts\python.exe tools\verify_ingestion_knowledge_upgrade.py
.\.venv\Scripts\python.exe tools\verify_confirmed_knowledge_atomicity.py
.\.venv\Scripts\python.exe tools\verify_ingestion_workbench.py
.\.venv\Scripts\python.exe tools\verify_knowledge_center.py
.\.venv\Scripts\python.exe tools\verify_entity_experience.py
.\.venv\Scripts\python.exe tools\verify_capability_orchestration.py
.\.venv\Scripts\python.exe tools\verify_llm_preflight.py
.\.venv\Scripts\python.exe tools\verify_llm_usage.py
git diff --check
```

Windows 测试退出时偶发的临时目录 `PermissionError` 只有在脚本已经输出 `ok: true` 且进程退出码为 0 时才能视为非功能性清理警告；其它情况必须按测试失败处理。

建议提交：`test(ui): 完成四入口界面回归`

## 6. 第四阶段：可选视觉打磨

第四阶段不得与第二、第三阶段混合提交。

### UI-4.1：统一 Hub 视觉层级

状态：`已完成（基础版）`

实际完成：四个 Hub 通过共享 `render_hub_navigation` 使用统一边框容器、分段导航和状态初始化；保留现有卡片、空状态和主按钮样式。

- 四个 Hub 使用统一页头、内部导航、状态条和内容宽度。
- 同一页面最多一个高强调主按钮。
- 统一 8px 间距基准、按钮高度、卡片边框和空状态。
- 删除仅用于旧 16 页面布局的 CSS。
- 不改变功能和状态结构。

建议提交：`style(ui): 统一四入口视觉层级`

### UI-4.2：窄屏与可访问性

状态：`已完成（基础版）`

实际完成：沿用现有 900px/560px 响应式堆叠规则，并为 Hub 分段导航增加窄屏横向滚动；控件继续使用明确 label/help 和选中态。

- 在约 1280px、760px、390px 三种宽度验收。
- 多列布局在窄屏自然堆叠，不依赖固定像素宽度。
- 分段导航可横向滚动且选中态明确。
- 状态不只依赖颜色表达。
- 按钮、输入框和弹出层具有清晰 label/help。
- 键盘焦点顺序与视觉顺序一致。

建议提交：`style(ui): 改善窄屏与可访问性`

### UI-4.3：渲染性能与长页面控制

状态：`已完成（基础版）`

实际完成：四个 Hub 只调用当前视图 renderer，后台 dispatcher 仍由 `app.py` 单次启动；统一搜索继续分页，未引入跨项目缓存。

- Hub 只调用当前活动 renderer。
- 不在首屏加载隐藏视图的数据和大型列表。
- 大列表使用分页、范围或主从布局。
- 后台 dispatcher 只由应用入口启动一次，Hub 不重复启动。
- 使用 Streamlit 缓存时不得缓存项目密钥、可变 session state 或跨故事数据。

建议提交：`perf(ui): 优化 Hub 渲染开销`

## 7. 风险清单与处理方式

| 风险 | 典型表现 | 必须采用的处理方式 |
| --- | --- | --- |
| Streamlit widget 状态写入时机错误 | 页面切换时报 widget state 异常 | pending intent 在控件创建前消费，点击后 rerun |
| 项目/故事状态串线 | 切故事后仍显示上一个故事的页面或筛选 | 所有 Hub 和子视图使用 scoped key |
| 热重载持有旧 renderer | 修改代码后仍执行旧函数 | Hub 纳入 `_reload_live_ui_modules`，不缓存函数对象 |
| 资源定位丢失 | 点击指标只打开内容页但没有正确筛选 | 保留并测试 `resource_browser_focus` payload |
| 旧会话落到错误页面 | 更新后用户回到首页而非原任务 | 完整旧路由映射和一次性状态迁移 |
| Hub 嵌套层级过深 | 四入口表面精简，页面内部仍有四层标签 | 第三阶段扁平化资料库和创作流程 |
| 重构误改业务逻辑 | 生成、审核或索引结果变化 | Hub 只复用 renderer；运行领域回归测试 |
| 普通用户重新看到内部工具 | 出现检索评测、索引或 Worker 术语 | 开发工具只由环境变量开启且位于设置内部 |
| 无 API Key 导致 UI 验收失败 | 页面测试误触发真实生成 | UI 测试使用 stub，不调用外部模型或搜索 |
| 模块继续膨胀 | 新 Hub 超过约 600～800 行 | Hub 只编排；组件、状态转换分别拆分 |
| 兼容代码过早删除 | 首页快捷入口或旧状态失效 | 先完成 UI-3.4 的调用点审计再删除 |

## 8. 每个任务的交付格式

Luna 完成任务后必须按以下结构交付：

```text
任务：UI-X.Y

结果：完成 / 部分完成 / 阻塞

修改：
- 文件：做了什么

兼容性：
- 哪些旧入口或状态已验证
- 是否涉及数据、schema、工作流（正常情况下应为否）

验证：
- 命令：通过 / 失败 / 未运行及原因

剩余风险：
- 仅列当前任务尚未消除的风险

建议下一步：
- 只能指向规划中的直接后继任务
```

禁止只回复“已完成”而不列出验证；禁止用修改大量无关文件来满足行数或格式检查。

## 9. 最终完成定义

第二、第三阶段全部完成时，必须同时满足：

- 项目存在时侧栏恰好四个顶层入口。
- 没有项目时仍能配置模型和创建项目。
- `app.py` 只负责四个 Hub 的顶层分发。
- 旧页面名全部能迁移到正确 Hub 和内部视图。
- 工作台可以定位全部已有创作产物。
- 创作入口覆盖方向、规划、章节写作、审阅和自由模式。
- 资料库覆盖导入、来源、搜索、编辑、角色视图、优先设定和待审核知识。
- 设置覆盖模型、费用、规则、偏好；检索诊断只在开发者模式出现。
- 章节审阅和知识提炼没有重新混为同一操作。
- 没有新增第二套知识、资料或角色卡存储。
- 项目/故事切换后所有 UI 状态正确隔离。
- 关键 UI、知识、创作、审阅、检索和应用冒烟测试全部通过。
- README、`project.md` 与实际界面一致。

只有达到以上条件，才可以宣布 UI 精简完成。第四阶段可以在此之后独立进行。
