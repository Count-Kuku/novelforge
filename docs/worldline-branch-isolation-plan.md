# 对话创作分支 → 知识世界线隔离：现状评估与演进规划

> 状态：**草案（roadmap）** · 作者：Yihao 与协作 AI · 日期：2026-09-06
> 性质：本文件记录"对话工作台自由创作出现分支时，提炼进知识库的设定可能互相矛盾"这一问题的**完整评估**与**未来演进路线**。当前已实施的是轻量缓解（提炼冲突提示 + 来源标记），本文件描述的**多世界线隔离**是后续大项，尚未实施，等分支管理产品面成型后再推进。

---

## 1. 背景与问题

对话工作台采用"写作 → 确认片段 → 自动提炼进知识库"流程。当同一会话内出现**创作分支**（从不同已确认片段继续生成不同走向，或明确试验两条故事线）时，不同分支的正文可能包含**互相矛盾的角色状态 / 世界规则 / 关系**（例如：分支A 中角色死亡，分支B 中角色仍在活跃）。

若两条分支都被确认并提炼，矛盾设定可能同时写入项目正式知识库，导致后续检索与生成引用到相悖设定。

## 2. 现状机制与能力边界（2026-09 核查）

### 2.1 提炼流程
确认片段 → `extract_fragment_knowledge`（`novelforge/workflows/interactive_writing/_fragment_ops.py`）抽取候选 → 入待审核队列（`pending_knowledge_items`）→ `auto_confirm_pending_items_without_risk`（`novelforge/workflows/source_workflows/consolidation.py`）自动审核。

### 2.2 已具备的矛盾防护
- 质量检查（`novelforge/domain/knowledge_quality.py:296`）会检测：pending 内部冲突、pending 与**正式库**的 `fact_conflict` / `confirmed_overlap` / `duplicate` / `alias_candidate`。
- 冲突检测按"知识键"分组：`(category, name, setting_scope, story_id, worldline_id, version_scope)`。
- 命中高严重度冲突的候选由自动审核**拦截（blocked）**并留在待审核区（`evaluate_pending_auto_review_decision`，`domain/knowledge_workflows.py:79`），由用户在知识工作区 `confirmPending` / `discardPending` 人工裁决，**不会静默写入正式库**。

### 2.3 能力边界（本次评估确认的不足）
1. **同名盲区**：只有"同分类 + 同名（含别名归并后）"才进入冲突比对。若分支把同一实体提炼成不同名称且未被别名识别，会走不同知识键 → 互不视为冲突 → 分别自动入库，矛盾静默共存。
2. **分支不隔离**：所有对话片段提炼时被固定注入 `worldline_id = profile/session 或 "main"`、`version_scope = "project_main"`（见 `_fragment_ops.py` 提炼候选组装）。创作分支的存在**不会**反映到知识隔离域上。
3. **worldline 仅存在于实体/知识层**：`worldline_id` 目前是知识（entities/知识条目）与故事配置层面的属性，**创作片段（creative_fragments）本身没有 worldline 字段**，检索侧有 worldline 过滤能力（`services/memory/knowledge_entities.py` 按 worldline 加载、`merge_worldline_baseline`），但对话提炼未使用分支粒度。
4. **无自动裁决**：即使冲突被拦截，仍需人工决策；没有"按分支决定采纳哪条"的机制。

### 2.4 已实施的轻量缓解（2026-09-06，本批）
- 确认即提炼后，若与正式库/同批存在冲突 → 前端显式提示（采纳 / 保留两条 / 跳过）三选。
- 提炼候选携带**分支来源标记**，冲突提示中展示"此设定来自哪条线"，辅助人工裁决。
- 详情见实施批次记录（会话收敛批 1）。

## 3. 演进路线：多世界线隔离（未来大项）

### 3.1 目标形态
让"分支"成为一等概念：从某确认片段派生一条创作分支时，该分支及其提炼的知识拥有独立**世界线身份**；正式知识与检索可按世界线过滤；用户可在世界线间切换视角。

### 3.2 关键设计点（初步）
1. **分支 → worldline 映射**：creative_fragment 增加 worldline_id / branch_root_id；branch 动作创建新片段时派生新 worldline（或在会话内用 `version_scope` 表达分支深度）。
2. **提炼注入域**：`_fragment_ops.py` 提炼候选的 `worldline_id`/`version_scope` 改为取自片段归属分支，而非固定 main。
3. **检索过滤**：`assemble_generation_context` / RAG 召回时按当前世界线过滤，避免主线写作引用旁支设定。
4. **正文/章节装配**：`finalize_creative_session`（章节汇编）与规划台章节正文需明确"当前启用哪条世界线"。

### 3.3 前置依赖（为什么现在不做）
- 当前产品**尚无"多世界线管理"用户面**：切换世界线查看正文/知识/继续写作的入口不存在。
- 会话收敛（continue/rewrite/branch → 单循环）本身仍在演进，分支形态未稳定。
- 先落地分支来源标注与冲突提示，可低成本收集"实际多线写作频率与诉求"，再决定隔离深度。

### 3.4 建议分期
- **P0（已完成）**：提炼冲突提示 + 分支来源标记（本批）。
- **P1（候选）**：创作片段链增加 worldline/branch 归属；提炼按片段归属注入域；提供只读的"分支设定预览"。
- **P2（远期）**：完整世界线视图与切换（正文/知识/生成跟随世界线），需要产品决策是否支持"多线并行正统"。

## 4. 涉及模块清单（未来改动参考）
- `novelforge/workflows/interactive_writing/_fragment_ops.py`（提炼候选域注入）
- `novelforge/workflows/interactive_writing/_context.py`（分支解析）
- `novelforge/services/memory/creative_sessions.py` + `storage/repositories/creative_sessions.py`（fragment 表结构、active/worldline）
- `novelforge/domain/knowledge_quality.py`（隔离域扩展）
- `novelforge/services/memory/knowledge_entities.py`（世界线查询/合并）
- `novelforge/services/memory/` 检索装配（`assemble_generation_context` 等）
- 前端会话页（起点选择、世界线指示）

## 5. 备注
- 待审核区人工处理入口当前位于共享工作区（`SharedWorkspaceView.vue`，`api.pendingKnowledge` / `confirmPending` / `discardPending`）。
- 本文件为 roadmap 草案，后续按实际产品节奏修订。
