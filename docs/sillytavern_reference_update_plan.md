# NovelForge × SillyTavern 功能借鉴与更新规划

> 规划日期：2026-07-28
> NovelForge 基线：`v0.5.1`、SQLite Schema `v6`
> SillyTavern 参考基线：官方仓库提交 `8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8`

## 1. 结论

NovelForge 不应转型为“聊天式酒馆”，也不需要用聊天记录替代章节。更合适的方向是：

**继续以项目、故事线、大纲和章节为主干，吸收 SillyTavern 在角色卡、世界书、作者注释、提示词编排、候选回复和分支聊天上的上下文组织能力。**

优先级最高的并不是导入角色卡，而是先建立一个统一、可预览、可解释、受预算约束的“上下文装配器”。它会成为后续人物档案、世界设定激活、章节导演注、候选稿和故事分支的共同底座。

推荐的演进顺序：

1. `v0.5.2`：修复现有注入策略和检索源漂移。
2. `v0.6.0`：统一上下文装配器、导演注、真实注入预览。
3. `v0.6.1`：把自动角色实体升级为可维护的人物档案。
4. `v0.6.2`：增加世界设定激活规则和 Character Card JSON 导入/导出。
5. `v0.7.0`：增加章节候选稿、选稿发布和故事分支谱系。
6. `v0.7.1+`：增加场景演员表、安全工作流配方等增强能力。

## 2. 产品定位

### 2.1 保留 NovelForge 的核心

- 项目资源是共享资料源。
- 故事线是同人分支、世界线或独立作品的隔离边界。
- 大纲、章节、摘要和事实状态是长篇写作的正式资产。
- 知识库、证据、冲突检测和 RAG 是事实约束层。
- 章节生成完成后，才把正式结果同步到摘要、状态和检索库。

### 2.2 从 SillyTavern 借鉴的核心

- 角色卡：结构化的人格、口吻、示例对话和场景预设。
- 世界书：按关键词、语义、范围和优先级激活设定。
- 作者注释：临时或持续地影响当前生成。
- Prompt Manager：明确上下文块的顺序、来源和占用。
- Swipes：同一输入保留多个候选结果。
- Branching/Checkpoint：从某一节点复制并继续另一条叙事线。

### 2.3 不应照搬的部分

- 不把聊天消息作为项目的唯一真实来源。
- 不把随机概率、递归触发作为第一版世界设定激活机制。
- 不允许导入的角色卡脚本、扩展字段直接执行。
- 不允许用户提示词覆盖结构化输出契约、安全规则和系统约束。
- 不让未选中的候选稿进入章节摘要、事实抽取或向量索引。
- 暂不复制群聊角色发言概率、图片生成、TTS、酒馆扩展生态。

## 3. 参考实现与 NovelForge 映射

| SillyTavern 能力 | 官方代码参考 | NovelForge 当前基础 | 建议动作 |
|---|---|---|---|
| Character Card V2 | [`src/endpoints/characters.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/src/endpoints/characters.js) 中的 `getCharaCardV2`、`convertToV2`、`charaFormatData` | `knowledge_entities.py` 已能从已确认知识生成角色实体卡 | 建立“自动事实层 + 人工覆盖层”的人物档案；后续支持 Card V2/V3 JSON |
| Character Book / World Info | [`public/scripts/world-info.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/public/scripts/world-info.js) 中的扫描、激活、预算和递归逻辑 | `knowledge_items`、别名组、混合检索、世界线和作用域过滤已经存在 | 增加确定性的激活规则和原因解释；复用 RAG，不复制整套随机递归机制 |
| Author's Note | [`public/scripts/authors-note.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/public/scripts/authors-note.js) 中的 prompt、interval、depth、position、role | 临时写作要求和 Prompt Options 已可影响生成 | 增加项目/故事/章节/单次范围的“导演注”，并提供有效期和剩余次数 |
| Prompt Manager | [`public/scripts/PromptManager.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/public/scripts/PromptManager.js) 中的 `Prompt`、`PromptCollection`、`PromptManager` | `prompt_options.py` 有插槽、优先级和结构化契约保护 | 引入统一 Context Block、真实顺序预览、预算和省略原因 |
| Swipe 候选 | SillyTavern 消息的 swipe 数据模型和分支快照逻辑 | 当前一次生成只有一个正式章节结果 | 增加同一章节的多个候选稿，只允许选中稿发布 |
| Branch / Checkpoint | [`public/scripts/bookmarks.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/public/scripts/bookmarks.js) 中的 `getBranchChatSnapshot`、`createBranch`、`createNewBookmark` | `memory.copy_story()` 已能完整复制故事资产 | 在现有复制功能上补充父故事、分叉章节和来源指纹 |
| Data Bank / Vector | [`public/scripts/extensions/vectors/index.js`](https://github.com/SillyTavern/SillyTavern/blob/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8/public/scripts/extensions/vectors/index.js) | NovelForge 已有更贴合长篇写作的分段、向量、反馈、评测和冲突检测 | 不重做向量库，只改进注入策略、来源配置和可解释性 |

## 4. 当前代码中应先解决的问题

这些问题会直接影响后续功能的正确性，应放入第一阶段，而不是等到界面优化时再处理。

### 4.1 注入策略没有被严格执行

涉及文件：

- `setting_knowledge.py`
- `retrieval.py`
- `ui/settings_page.py`

当前 `list_setting_items(core_only=True)` 会让所有 `setting_role == "core"` 的设定通过，即使其 `injection_policy` 是 `retrieval` 或 `manual_only`。这会导致界面中的“检索命中时注入”和“仅手动管理”与实际生成行为不一致。

建议统一语义：

| 策略 | 直接注入 | 进入检索索引 | 自动检索注入 | 手动选择注入 |
|---|---:|---:|---:|---:|
| `always` | 是 | 是 | 可重复去重 | 是 |
| `retrieval` | 否 | 是 | 是 | 是 |
| `manual_only` | 否 | 可索引但默认禁止自动命中 | 否 | 是 |

`manual_only` 即使保留向量，也必须在运行时检索过滤中排除，除非调用方传入明确选中的知识 ID。

### 4.2 检索 Profile 与调用点白名单发生漂移

涉及文件：

- `retrieval.py`
- `skills.py`

`RETRIEVAL_TASK_PROFILES` 已经为章节写作配置了 `entity_character_card` 等来源，但多个生成入口又传入显式 `allowed_source_types`。当前显式列表会覆盖 Profile，导致人物实体卡虽然已经建立和索引，却可能不参与正文生成。

建议：

- 以 `retrieval_profile` 为默认唯一来源配置。
- 只有特殊任务才传额外来源，并明确组合模式：
  - `union`：在 Profile 上追加。
  - `intersect`：进一步收窄。
  - `replace`：完全替换，必须显式声明。
- 删除 `skills.py` 中重复、易漂移的长列表。
- 在测试中断言 `drafting` Profile 能实际召回人物实体和别名信息。

### 4.3 当前注入预览不等于真实生成上下文

涉及文件：

- `ui/prompt_option_tools.py`
- `skills.py`
- `prompts.py`

现有预览能展示核心设定、规则、创作档案、Prompt Options 和临时要求，但不包含：

- 实际 RAG 命中；
- 最终装配顺序；
- 各块预算占用；
- 被裁剪内容及原因；
- 生效范围和世界线；
- 最终上下文指纹。

预览和生成分别拼装，长期会产生行为漂移。后续必须由同一个装配函数生成“预览”和“提交给模型的内容”。

### 4.4 人物实体卡目前更像自动缓存，不是人物档案

涉及文件：

- `knowledge_entities.py`
- `memory.py`
- `ui/knowledge_management.py`

现有角色实体卡的优点是可由已确认知识自动聚合，并带来源知识 ID、世界线和证据。但当前界面主要通过整段 JSON 编辑，重新生成时人工内容也容易被覆盖。

需要拆成两层：

1. `AutoCharacterFacts`：由知识库生成，不手工修改。
2. `CharacterProfileOverride`：由作者维护，只保存人工补充和覆盖字段。

运行时得到：

```text
EffectiveCharacterProfile
  = AutoCharacterFacts
  + CharacterProfileOverride
  + 当前故事线/世界线过滤
```

## 5. 目标架构

### 5.1 统一上下文装配器

新增模块：

- `context_assembly.py`

建议数据模型加入 `schemas.py`：

```python
class ContextBlock(BaseModel):
    block_id: str
    category: str
    content: str
    source_type: str
    source_ref: str | None = None
    scope: str
    story_id: str | None = None
    worldline: str | None = None
    placement: str
    priority: int = 0
    hard_constraint: bool = False
    activation_reason: str = ""
    estimated_tokens: int = 0
    included: bool = True
    omission_reason: str = ""
    metadata: dict = Field(default_factory=dict)


class ContextAssembly(BaseModel):
    capability: str
    query: str
    chapter_no: int | None = None
    blocks: list[ContextBlock]
    total_estimated_tokens: int
    context_budget: int
    omitted_blocks: list[ContextBlock]
    warnings: list[str]
    fingerprint: str
```

装配器对外提供两个主要入口：

```python
assemble_generation_context(...)
render_context_preview(...)
```

`render_context_preview()` 必须只格式化 `assemble_generation_context()` 的结果，不能重新收集一遍资源。

推荐的受限插槽顺序：

1. 系统硬约束和输出 Schema；
2. 创作档案；
3. 项目/故事规则和已确认冲突决策；
4. `always` 核心设定；
5. 当前生效的导演注；
6. POV、场景人物档案；
7. 最近章节摘要和故事状态；
8. 规则激活或 RAG 命中的知识；
9. Prompt Options 和本次写作要求；
10. 用户任务与不可覆盖的输出契约。

这里不照搬 SillyTavern 的任意 `role + depth` 注入。NovelForge 应只开放有限插槽，避免作者注或外部角色卡越过结构化输出要求。

### 5.2 预算与优先级

第一版不增加 tokenizer 依赖，可使用稳定的近似估算，并在模型提供方支持时切换为精确 token 计数。

裁剪顺序：

1. 永不裁剪输出 Schema、安全约束和硬规则。
2. 为当前章节写作目标、POV 人物和最近状态预留预算。
3. 对检索知识按综合得分和激活优先级排序。
4. 合并重复实体卡与知识项。
5. 记录所有被省略块及原因，不静默丢弃。

建议预算告警：

- `< 70%`：正常；
- `70%–90%`：黄色提醒；
- `> 90%`：红色提醒并显示主要占用来源；
- 硬约束本身超过预算：阻止生成并给出可操作提示。

### 5.3 指纹与可复现性

每次生成保存：

- Context Assembly fingerprint；
- 使用的资源 ID 与版本/更新时间；
- 检索命中 ID、分数和激活原因；
- Prompt Option ID；
- 模型 Profile；
- 写作指导；
- 生成时间。

指纹用于：

- 对比候选稿是否使用相同上下文；
- 判断重试是否可复现；
- 标记“资料修改后旧候选已过期”；
- 记录故事分支的来源状态。

## 6. 分阶段实施规划

### 阶段 0：`v0.5.2` 上下文正确性修复

#### 目标

先让现有“设定注入、人物实体检索、作用域隔离”与界面承诺一致。

#### 代码工作

1. 在 `setting_knowledge.py` 中严格实现三种 `injection_policy`。
2. 在 `retrieval.py` 的候选过滤阶段加入 `manual_only` 排除。
3. 支持通过 `explicit_knowledge_ids` 让用户手选知识越过自动过滤。
4. 调整 `resolve_retrieval_params()`，加入明确的来源组合模式。
5. 清理 `skills.py` 中重复的 `allowed_source_types`。
6. 确认 `drafting`、`outline`、`review` Profile 的人物实体卡策略。
7. 在现有预览中临时增加策略标签，直到阶段 1 的统一预览落地。

#### 验收标准

- `always` 设定无需检索即可出现在生成上下文。
- `retrieval` 设定只有命中后才出现。
- `manual_only` 设定不会被自动检索注入。
- 明确手选的 `manual_only` 设定可以注入。
- 正文写作可召回 `entity_character_card`。
- 项目、故事和世界线隔离测试全部通过。
- 旧数据无需手工迁移。

#### 验证脚本

建议新增：

- `tools/verify_context_policy.py`
- `tools/verify_retrieval_profile_sources.py`

并把关键用例纳入现有回归验证入口。

### 阶段 1：`v0.6.0` 上下文装配器与导演注

#### 目标

把散落在 `skills.py`、`prompts.py` 和 UI 预览里的上下文拼装统一起来，并提供类似 Author's Note 的可控临时指令。

#### 新增数据模型

```python
class ContextDirective(BaseModel):
    directive_id: str
    name: str
    content: str
    scope: Literal["project", "story", "chapter", "run"]
    story_id: str | None = None
    chapter_start: int | None = None
    chapter_end: int | None = None
    capabilities: list[str] = Field(default_factory=list)
    placement: Literal[
        "hard_constraints",
        "story_state",
        "chapter_direction",
        "character_voice",
        "style",
        "reference",
    ]
    priority: int = 0
    enabled: bool = True
    remaining_uses: int | None = None
    expires_at: str | None = None
```

导演注示例：

- “未来三章保持林黛玉视角，不进入宝玉内心。”
- “本章只写潜入，不揭示幕后主使。”
- “这次重写减少网络流行语。”
- “人物对白更克制，但不要改变既定事实。”

#### 持久化方案

利用现有通用资产能力，不增加数据库迁移：

- `asset_type = "context_directive"`
- 内容放入 `asset_payloads`
- `logical_key` 由 scope、story、chapter 和 directive ID 组成
- 通过 `memory.py` 暴露读写函数
- 故事复制时沿用 `story_copy.py` 的通用资产复制能力

导演注不进入 RAG 索引，避免它被当成世界事实。

#### 生命周期规则

- 预览和 dry-run 不消耗 `remaining_uses`。
- 模型调用失败不消耗。
- 只有章节或正式资产成功保存后才消耗。
- “单次”导演注消费后保留历史记录，但变为 inactive。
- 所有消费操作写入生成运行元数据，便于追踪。

#### UI 方案

新增共享组件：

- `ui/context_directives.py`
- `ui/context_preview.py`

接入位置：

- `ui/chapter_page.py`
- `ui/dynamic_generation.py`
- 大纲生成和评价页的高级选项

预览至少显示：

- 最终顺序；
- 来源、作用域、世界线；
- 激活原因；
- 估算 token；
- 是否被裁剪；
- 警告；
- Context fingerprint。

不建议为导演注新增独立导航页。项目级和故事级管理可放在“核心设定/项目资源”，本章和单次指令直接放在生成页。

#### 代码改造

- `skills.py`：所有主要生成入口先调用 `assemble_generation_context()`。
- `prompts.py`：只负责模板和最终格式化，不再自行扫描资源。
- `ui/prompt_option_tools.py`：改为展示装配结果。
- `memory.py`：增加导演注和生成上下文快照的 facade。
- `schemas.py`：增加 Context 相关模型。

#### 验收标准

- UI 预览内容与实际送模内容来自同一个装配结果。
- 修改资源后，Context fingerprint 会变化。
- 被省略的上下文均有可见原因。
- 单次导演注只在成功保存后消费。
- 用户内容无法越过或覆盖输出 Schema。
- 旧的生成流程在没有导演注时保持兼容。

### 阶段 2：`v0.6.1` 人物档案

#### 目标

把当前自动生成的角色实体卡升级为可审阅、可补充、可按场景使用的写作资产。

#### 数据分层

保留：

- `character_entities`：自动事实层，继续由已确认知识构建。

新增：

- `character_profile_override`：人工维护层。
- `EffectiveCharacterProfile`：运行时合并结果，不单独作为真相源。

建议人工字段：

- 展示名、别名；
- 外貌和识别特征；
- 性格与行为倾向；
- 当前目标、长期目标；
- 恐惧、底线、禁忌；
- 能力、物品；
- 关系；
- 对话风格；
- 示例对话；
- OOC 约束；
- POV/叙事注意事项；
- 场景预设和开场灵感；
- 适用故事、世界线；
- 备注与来源。

#### 合并规则

- 事实字段默认以已确认知识为底。
- 人工覆盖只覆盖明确填写的字段。
- 事实变化时不删除人工补充。
- 自动事实与人工覆盖冲突时显示警告，不静默覆盖。
- Effective Profile 合并后再进入人物实体检索文档。

#### UI 方案

新增页面：

- `ui/character_profiles_page.py`

导航放在“资料”组，名称为“人物档案”。

页面能力：

- 人物列表与搜索；
- 自动事实/人工补充/有效档案三栏或标签页；
- 表单编辑，不以整段 JSON 作为主交互；
- 冲突和缺失字段提示；
- 当前故事线/世界线预览；
- 选择“本章出场人物”和 POV；
- 展示其来源知识和关系。

#### 章节写作接入

扩展 `ChapterWritingGuidance`：

```python
pov_character_id: str | None
scene_character_ids: list[str]
character_profile_mode: Literal["auto", "selected_only"]
```

上下文装配器应：

1. 强制加入 POV 人物的有效档案；
2. 优先加入场景人物；
3. 其他角色交给 RAG；
4. 对同一人物的实体卡和知识命中去重。

#### 验收标准

- 重新构建自动实体卡不会丢失人工档案。
- 故事线和世界线覆盖正确隔离。
- 人物档案保存后会刷新对应检索文档。
- 本章选中的 POV 和场景人物稳定进入上下文。
- 人工档案与事实冲突时可见且可追溯。

### 阶段 3：`v0.6.2` 世界设定激活与 Character Card 互操作

#### 目标

把世界书中最有价值的“按场景激活”能力引入现有知识库，同时支持安全的角色卡 JSON 交换。

#### 知识激活规则

建议增加：

```python
class KnowledgeActivationRule(BaseModel):
    mode: Literal["always", "keyword", "semantic", "hybrid", "manual"]
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    negative_keys: list[str] = Field(default_factory=list)
    key_logic: Literal["any", "all"] = "any"
    priority: int = 0
    capabilities: list[str] = Field(default_factory=list)
    chapter_start: int | None = None
    chapter_end: int | None = None
    placement: str = "reference"
    max_context_tokens: int | None = None
```

第一版激活流程：

```text
作用域/故事/世界线过滤
  → capability 与章节范围过滤
  → always / 手动选择
  → 关键词与别名命中
  → 语义检索
  → hybrid 合并与去重
  → 预算裁剪
  → 输出激活原因
```

暂不实现：

- 随机概率触发；
- 无限递归世界书；
- 复杂分组竞争；
- 导入脚本执行；
- 任意 prompt depth。

这些功能对长篇写作的可复现性不利，收益低于调试成本。

#### Character Card JSON 导入

新增模块：

- `character_card_io.py`

MVP 只支持 JSON：

- Character Card V2；
- 在字段稳定后补充 V3；
- PNG 内嵌元数据推迟到后续版本，避免仅为导入引入图像依赖。

字段映射建议：

| Character Card 字段 | NovelForge 目标 |
|---|---|
| `name` | 人物档案名称 |
| `description` | 人工档案简介/外貌候选 |
| `personality` | 性格和行为倾向 |
| `scenario` | 场景预设 |
| `first_mes` | 开场灵感，不作为既定事实 |
| `alternate_greetings` | 备选开场灵感 |
| `mes_example` | 示例对话 |
| `creator_notes` | 导入备注，不参与自动提示 |
| `system_prompt` | 默认禁用的 Prompt Option 候选 |
| `post_history_instructions` | 默认禁用的导演注/Prompt Option 候选 |
| `character_book.entries` | 待审核知识 + 激活规则候选 |
| `extensions` | 隔离保存或忽略，绝不执行 |

导入流程：

1. 解析并验证格式；
2. 展示字段映射预览；
3. 检测同名人物、别名和知识冲突；
4. 生成待审核条目；
5. 用户选择合并、新建或跳过；
6. 外部 prompt 默认关闭；
7. 用户确认后才写入人物档案或知识库；
8. 保存原始来源和导入报告。

#### Character Card JSON 导出

导出内容来自：

- Effective Character Profile；
- 用户明确选择的关联知识；
- 用户选择的场景预设和示例对话。

不自动导出：

- 项目密钥、模型配置；
- 未确认知识；
- 私有作者注；
- 未选择的故事线资料；
- 内部工作流和运行记录。

#### 验收标准

- 相同输入和配置得到相同的激活结果。
- 每个激活条目都显示“为什么出现”。
- 世界线和章节范围始终先于关键词/语义匹配。
- 外部 prompt、扩展和脚本不会自动生效。
- 导入不会跳过待审核与冲突检查。
- 导入后删除原始文件不影响已确认资产。

### 阶段 4：`v0.7.0` 章节候选稿与故事分支

#### 目标

吸收 SillyTavern 的 Swipe 和 Branch 思路，但以章节为单位设计。

#### 章节候选稿

新增模块：

- `generation_variants.py`
- `ui/generation_variants.py`

候选稿元数据：

```python
class ChapterVariant(BaseModel):
    variant_id: str
    story_id: str
    chapter_no: int
    title: str
    status: Literal["candidate", "selected", "rejected", "stale"]
    source_outline_id: str | None = None
    source_outline_hash: str
    context_fingerprint: str
    model_profile: str
    workflow_run_id: str | None = None
    created_at: str
```

长文本仍使用文件存储：

```text
stories/{story_id}/drafts/chapter_{chapter_no:03d}/{variant_id}.md
```

并在 `asset_files` 注册元数据，保持 SQLite-first 的资产索引方式。

工作流：

1. 同一章节生成 2–4 个候选稿；
2. 使用相同 Context fingerprint 时标记为公平对比；
3. 展示并排差异、质量评价和事实风险；
4. 用户选择一个候选；
5. 选中稿通过现有 `save_chapter()` 发布为正式章节；
6. 仅选中稿触发摘要、事实抽取、状态更新和检索同步。

当大纲、设定或人物档案修改后，旧候选与新指纹不一致，应显示 `stale` 提示，但不自动删除。

#### 故事分支谱系

现有 `memory.copy_story()` 和 `storage/repositories/story_copy.py` 已经具备主要复制能力。无需重写复制逻辑，只补充谱系。

建议新增迁移：

- `storage/migrations/007_story_lineage.sql`

建议表：

```sql
CREATE TABLE story_lineage (
    child_story_id TEXT PRIMARY KEY,
    parent_story_id TEXT NOT NULL,
    fork_chapter_no INTEGER,
    source_asset_id TEXT,
    source_context_fingerprint TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(child_story_id) REFERENCES stories(story_id),
    FOREIGN KEY(parent_story_id) REFERENCES stories(story_id)
);
```

新增仓储：

- `storage/repositories/story_lineage.py`

分支方式：

- 从当前完整故事复制；
- 从第 N 章建立分支，并把后续章节标为未继承或不复制；
- 从某个候选稿建立新故事分支；
- 创建只读检查点。

#### UI 方案

- “项目总览”显示故事树和父子关系。
- “项目资源”显示章节候选和分支来源。
- “正文生成”支持“生成候选”“比较”“选中并发布”。
- 复制/分支前明确显示将复制哪些资产。

#### 验收标准

- 未选中候选不进入正式章节与 RAG。
- 选中稿发布复用现有章节保存链路。
- 每个故事分支可以追溯到父故事、章节和上下文指纹。
- 删除/归档子故事不影响父故事。
- 旧故事在没有 lineage 记录时仍能正常使用。

### 阶段 5：`v0.7.1+` 增强项

#### 场景演员表

利用已有 `graph_nodes` 和 `graph_edges`：

- 选择 POV、主要人物、旁观人物；
- 显示人物关系；
- 检查“本场人物未知但文本让其知晓”的知识泄漏；
- 自动建议应注入的关系和最近事件。

#### 安全工作流配方

只提供白名单动作，不引入任意脚本：

```text
检索资料
  → 生成候选
  → 评价候选
  → 事实一致性检查
  → 用户选稿
  → 发布章节
  → 更新摘要/状态
```

配方只允许配置：

- 步骤开关；
- 模型 Profile；
- 候选数；
- 评分阈值；
- 是否需要人工确认；
- 失败重试次数。

不允许执行文件、Shell、JavaScript 或角色卡扩展代码。

## 7. 建议文件变更清单

| 文件 | 动作 | 主要职责 |
|---|---|---|
| `context_assembly.py` | 新增 | 统一收集、排序、预算、裁剪、解释和指纹 |
| `character_profiles.py` | 新增 | 自动事实与人工覆盖的合并 |
| `character_card_io.py` | 新增 | Character Card JSON 安全导入/导出 |
| `generation_variants.py` | 新增 | 候选稿生命周期和发布 |
| `schemas.py` | 修改 | Context、Directive、人物档案、激活规则、候选稿模型 |
| `memory.py` | 修改 | 继续作为持久化 facade，禁止 UI 直连仓储 |
| `retrieval.py` | 修改 | 策略过滤、来源组合、激活原因、人物档案去重 |
| `setting_knowledge.py` | 修改 | 严格执行注入策略 |
| `skills.py` | 修改 | 所有能力统一使用 Context Assembly |
| `prompts.py` | 修改 | 接收已装配上下文，不重复读取业务资源 |
| `prompt_options.py` | 修改 | 映射到受限插槽和上下文块 |
| `ui/context_preview.py` | 新增 | 真实上下文预览 |
| `ui/context_directives.py` | 新增 | 导演注编辑器 |
| `ui/character_profiles_page.py` | 新增 | 人物档案管理 |
| `ui/generation_variants.py` | 新增 | 候选稿比较和选稿 |
| `ui/navigation.py` | 修改 | 仅增加“人物档案”，避免导航膨胀 |
| `ui/chapter_page.py` | 修改 | 导演注、演员表、候选稿接入 |
| `ui/dynamic_generation.py` | 修改 | 使用相同的上下文装配与预览 |
| `resource_browser.py` | 修改 | 展示导演注、人物覆盖、候选和分支来源 |
| `storage/repositories/story_lineage.py` | 阶段 4 新增 | 故事父子关系 |
| `storage/migrations/007_story_lineage.sql` | 阶段 4 新增 | 故事谱系持久化 |

## 8. 数据迁移策略

### 无迁移阶段

阶段 0–3 优先复用：

- `asset_files`
- `asset_payloads`
- `logical_key`
- 现有知识表和检索表

新 JSON 资产类型应先通过 `memory.py` 封装，保持未来迁移到专用表的可能性。

### 需要迁移的阶段

阶段 4 的故事谱系需要可查询的父子关系，建议使用 Schema v7 专表，而不是把关系埋入 `story_profiles` JSON。

迁移要求：

- 只新增，不改写旧故事；
- 旧故事没有 lineage 行时视为根节点；
- 新迁移纳入顺序执行；
- 复制失败时 lineage 和资产复制必须在同一事务语义下回滚或补偿；
- 继续保持旧项目可打开。

## 9. 测试矩阵

### 上下文与检索

- 三种 injection policy。
- `union/intersect/replace` 来源组合。
- 项目/故事/世界线隔离。
- 人物实体卡召回。
- 同一事实去重。
- 超预算裁剪与硬约束保护。
- 预览和实际上下文指纹一致。

### 导演注

- 项目、故事、章节、单次作用域。
- capability 和章节范围过滤。
- 成功后消费、失败不消费、预览不消费。
- 过期和禁用。

### 人物档案

- 自动事实更新不破坏人工覆盖。
- 空字段不覆盖事实。
- 冲突可见。
- POV 和场景人物强制注入。
- 世界线隔离。

### Character Card

- V2 标准 JSON。
- 缺失可选字段。
- 未知字段保留在导入报告。
- 恶意 system prompt 默认禁用。
- extensions 和脚本不执行。
- 重复人物合并和取消导入。
- character_book 进入待审核。

### 候选稿和分支

- 多候选只发布一个。
- 未发布候选不进入摘要/RAG。
- 资料变化触发 stale。
- 从章节和候选创建故事分支。
- 父子故事相互隔离。
- 归档、复制和恢复兼容。

## 10. 风险与控制

| 风险 | 控制措施 |
|---|---|
| 上下文装配重构影响所有生成能力 | 先增加兼容适配层，按 capability 逐个迁移，并保留旧快照测试 |
| “更强注入”导致 token 膨胀 | 统一预算、来源聚合、去重和省略报告 |
| 人工人物档案与知识事实冲突 | 分层存储，合并时显示冲突，不覆盖原始事实 |
| 外部角色卡提示注入 | 外部 prompt 默认禁用，脚本永不执行，必须人工确认 |
| 候选稿污染正式知识 | 候选存放在 drafts，只有选中发布后进入正式管线 |
| 分支复制体积变大 | 分支前显示资产范围；后续再考虑内容寻址或引用复用 |
| UI 变复杂 | 只新增“人物档案”主页面，其他能力嵌入现有工作流 |
| 可复现性下降 | 第一版采用确定性规则，保存上下文指纹和来源快照 |

## 11. 首个开发批次建议

第一批建议只做 `v0.5.2 + v0.6.0`，不要同时上角色卡导入。

开发顺序：

1. 为现有注入策略和 Profile 漂移补失败测试。
2. 修复 `setting_knowledge.py` 和 `retrieval.py`。
3. 建立 `ContextBlock` 和 `ContextAssembly`。
4. 先迁移 `write_chapter()`，让预览和实际生成一致。
5. 再迁移快速生成、大纲和评价能力。
6. 增加导演注及生命周期。
7. 完成回归后再开始人物档案。

这个批次完成后，项目将先获得最重要的基础能力：

- 用户能知道模型到底看到了什么；
- 设定的注入策略真实有效；
- 人物实体卡能稳定参与写作；
- 临时写作意图不必混入永久世界事实；
- 后续角色卡、世界书和候选稿都能复用同一个上下文管线。

## 12. 完成定义

整个规划完成时，应满足：

- 章节仍是正式写作资产，聊天不会成为新的主数据模型。
- 每次生成都有可解释、可复现的 Context Assembly。
- 项目资料、故事资料、世界线和临时指令边界清楚。
- 人物档案同时利用自动事实和人工塑造。
- 世界设定能确定性地按场景激活。
- 可以安全导入/导出主流 Character Card JSON。
- 同一章节可以保留多个候选，并明确发布其中一个。
- 故事分支有可追溯谱系。
- 未确认外部资料、未选候选和可执行扩展不会污染正式知识与生成流程。

## 13. 参考资料

- [SillyTavern World Info 官方文档](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)
- [SillyTavern Character Design 官方文档](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)
- [SillyTavern Author's Note 官方文档](https://docs.sillytavern.app/usage/core-concepts/authors-note/)
- [SillyTavern Prompt Manager 官方文档](https://docs.sillytavern.app/usage/prompts/prompt-manager/)
- [SillyTavern Chat Branching 官方文档](https://docs.sillytavern.app/usage/core-concepts/chatfilemanagement/)
- [SillyTavern Data Bank 官方文档](https://docs.sillytavern.app/usage/core-concepts/data-bank/)
- [Character Card V2 Specification](https://github.com/malfoyslastname/character-card-spec-v2)
- [SillyTavern 固定参考提交](https://github.com/SillyTavern/SillyTavern/tree/8172dcd0ee672d3cd9a5e5f7af134f91a45cd2b8)
