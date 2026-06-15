# 设定系统整体规划

## 1. 现状问题

| 问题 | 说明 |
|---|---|
| **作用域模糊** | 创作配置和核心设定在 UI 中没有清晰说明哪些是故事级、哪些是项目级 |
| **迁移缺失** | 创建新故事时没有复制已有设定的能力 |
| **设定间无法互通** | 故事设定不能推送到项目级作为默认，项目设定也不能快速应用到故事 |
| **注入路径分散** | rules、memory、retrieval 在技能函数中各自由不同的函数装配，无统一上下文层 |
| **设定只是摆设** | `reference_focus`、`reference_strength`、`conflict_policy` 只有文本描述，不实际影响检索行为和冲突处理 |
| **知识库与配置割裂** | creative_profile 选了"角色参考"但检索时不会自动优先匹配 `knowledge_characters` |
| **规则系统局限** | 规则只有 global/project 两级，缺少 story 层；UI 是纯文本行输入 |

## 2. 设定复制与冲突处理（核心新功能）

### 2.1 适用范围

| 来源 → 目标 | 可复制内容 |
|---|---|
| **故事 → 项目** | memory overrides 合并回 project memory.json（overrides 清空） |
| **项目 → 故事** | project memory.json 覆盖到 story memory_overrides（或选择性覆盖） |
| **故事 → 故事** | creative_profile + memory_overrides + rules_overrides |
| **故事规则 → 项目规则** | story rules_overrides 合并到 project rules.json |
| **项目规则 → 故事规则** | project rules 复制为 story rules_overrides |

### 2.2 冲突检测与合并 UI

```
合并预览窗口
├── 字段 1: canon_mode
│   ├── 来源值: "轻度架空"
│   └── 目标值: "完全架空"
│   └── 选择: ○ 保留来源  ○ 保留目标  ○ 合并（追加文本）
│
├── 字段 2: characters
│   ├── 来源: ["角色A", "角色B"]
│   └── 目标: ["角色B", "角色C"]
│   └── 选择: ○ 保留来源列表  ○ 保留目标列表  ○ 合并去重
│
├── 字段 3: creative_profile.workflow_depth
│   ├── 来源: "完整长篇流程"
│   └── 目标: "短篇结构+正文"
│   └── 选择: ○ 保留来源  ○ 保留目标
│
└── 确定合并  /  取消
```

实现方案：

- 后端：`merge_settings(source: dict, target: dict, schema: type) → MergePlan`
- `MergePlan` 包含每个字段的 `{ path, source_value, target_value, conflict: bool, resolution: None }`
- 对 list 字段默认做"合并去重"（列表级智能合并），标量字段默认"保留来源"
- 前端：渲染合并预览，只对 `conflict=True` 的字段显示选择器

### 2.3 入口位置

| 入口 | 位置 |
|---|---|
| 从项目导入到当前故事 | 设定 → 故事设定 标签页，按钮"从项目导入设定" |
| 从当前故事导出到项目（设为项目默认） | 设定 → 故事设定 标签页，按钮"设为项目默认设定" |
| 从其他故事导入 | 设定 → 故事设定 标签页，下拉选目标故事后点"导入" |
| 从故事导出到其他故事 | 设定 → 故事管理 标签页，故事列表的操作按钮 |

## 3. 目标架构

### 3.1 UI 结构

```
sidebar → 工作台 → 设定（统一入口）
│
└── st.tabs(["故事设定", "项目设定", "规则", "故事管理"])

故事设定标签页
├── 故事名称与作用域说明
├── 操作区
│   ├── [从项目导入设定]  → 弹出合并预览
│   ├── [设为项目默认]   → 合并到 project memory（带预览）
│   └── [从其他故事导入] → 选择源故事 → 合并预览
│
├── 创作配置表单（creative_profile）
└── 核心设定表单（memory_overrides）

项目设定标签页
├── 项目基础信息（名称、描述、创建时间）
├── 核心设定表单（memory.json base）
├── 知识库管理（现有知识库浏览/编辑/导入）
└── 外部资料列表

规则标签页
├── 全局规则编辑
├── 项目规则编辑
└── 故事规则编辑（新增，增量覆盖）

故事管理标签页
├── 故事列表表格（名称 / 状态 / 创建时间）
├── 操作：激活 / 复制 / 归档 / 删除
├── 复制弹出：选择复制目标范围（creative_profile + overrides / 含大纲章节）
└── 模型配置（移入底部）
```

### 3.2 数据分层

```
项目层（共享）
├── memory.json (base)
├── rules.json (project, 6 scopes)
├── knowledge/ (12 categories)
├── retrieval/sources/
└── long_reference_batches/

故事层（独有，可覆盖项目层）
├── creative_profile.json
├── memory_overrides.json (增量覆盖 base)
├── rules_overrides.json (增量覆盖 project rules，新建)
├── 写作内容 (outline/volumes/arcs/chapters/reviews...)
├── 分析产物 (analysis/evaluation/runs)
└── retrieval/conflict_resolutions.json
```

**合并优先级（从低到高）**：
1. project memory.json (base)
2. story memory_overrides.json (增量 + 覆盖)
3. project rules.json
4. story rules_overrides.json

## 4. 阶段实施

### 阶段一：核心能力建设（约 7-10 天）

#### 1.1 合并引擎

**新增文件**：`merge.py`

```python
class MergeOpion:
    path: str          # 字段路径，如 "memory.characters"
    source_value: Any
    target_value: Any
    conflict: bool     # 两值不同且都非空
    field_type: str    # scalar / list / dict
    resolution: Any    # 用户选择后的值

def build_merge_plan(source: dict, target: dict, schema: type = None) -> list[MergeOption]:
    """递归对比两个设定字典，生成合并计划"""

def apply_merge_plan(base: dict, plan: list[MergeOption]) -> dict:
    """按用户的决议应用合并"""
```

- 对 list 字段：如果 source 和 target 有重叠，做智能合并去重；只在完全不相交或有元素冲突时标注 conflict
- 对 scalar 字段（str/bool）：不同则标 conflict
- `schema` 参数可选，传入 Pydantic model 可识别字段类型和别名

#### 1.2 设定复制函数

**在 `memory.py` 中新增**：

```python
def copy_creative_profile(
    project_name, source_story_id, target_story_id
) -> None:
    """复制 creative_profile.json（含 discussion artifact）"""

def copy_memory_overrides(
    project_name, source_story_id, target_story_id
) -> None:
    """复制 memory_overrides.json"""

def merge_story_to_project_memory(
    project_name, story_id, field_resolutions: dict
) -> dict:
    """
    将 story 的 memory_overrides 合并回 project memory.json
    field_resolutions: 用户对冲突字段的抉择
    操作后清空该 story 的 overrides（有冲突的字段除外）
    """

def merge_project_to_story_memory(
    project_name, story_id, field_resolutions: dict
) -> dict:
    """
    将 project memory 选择性覆盖到 story memory_overrides
    """

def merge_story_rules_to_project(
    project_name, story_id, field_resolutions: dict
) -> dict:
    """故事规则→项目规则合并"""

def copy_story(
    project_name, source_story_id, new_name: str,
    *,
    include_discussions: bool = True,
    include_summaries: bool = True,
    include_chapters: bool = True,
) -> dict:
    """复制整个故事目录到新 story_id"""

def archive_story(project_name, story_id) -> bool:
    """将故事标记为 archived"""
```

#### 1.3 统一设定上下文装配器

在 `context.py`（新建）中实现：

```python
@dataclass
class GenerationContext:
    rules_text: str
    memory: dict
    creative_profile: dict
    retrieval_context: str

def build_generation_context(
    project_name: str,
    story_id: str,
    capability: str,        # "outline" / "write" / "review" / ...
    *,
    query: str = "",
    retrieval_top_k: int | None = None,  # 默认由 reference_strength 决定
) -> GenerationContext:
    """
    一次性装配所有上下文：
    1. 注入顺序：global rules → project rules → story rules
    2. 记忆：project base + story overrides
    3. 创作配置字段（内联到规则文本中）
    4. 检索上下文（受 reference_focus + reference_strength 影响）
    """
```

#### 1.4 Creative Profile 驱动检索

在 `retrieval.py` 中实现 `REFERENCE_FOCUS_SOURCE_MAP`，并在 `_build_retrieval_context()` 中应用：

```python
REFERENCE_FOCUS_SOURCE_MAP = {
    "角色":     ["knowledge_characters", "memory_character"],
    "世界观":   ["knowledge_world_rules", "knowledge_locations", "memory_world"],
    "剧情事件":  ["knowledge_timeline_events", "memory_timeline"],
    "道具能力":  ["knowledge_items", "knowledge_abilities"],
    "时间线":   ["knowledge_timeline_events", "memory_timeline"],
    "写作风格":  ["knowledge_writing_style", "knowledge_dialogue_style",
                   "knowledge_narrative_techniques"],
    "硬性约束":  ["knowledge_constraints"],
}

REFERENCE_STRENGTH_PARAMS = {
    "轻参考":      {"top_k": 3,  "mode": "lexical"},
    "中参考":      {"top_k": 6,  "mode": "hybrid"},
    "强参考":      {"top_k": 10, "mode": "hybrid"},
    "严格原作":    {"top_k": 15, "mode": "hybrid",
                     "scopes": ["canon", "reference"]},
    "主要参考文风": {"top_k": 8,  "mode": "hybrid",
                     "source_types": ["knowledge_writing_style",
                       "knowledge_dialogue_style", "knowledge_narrative_techniques"]},
}
```

#### 1.5 记忆字段扩展

```python
DEFAULT_MEMORY = {
    # 已有
    "title": "", "genre": "", "canon_mode": "", "au_rules": [],
    "world": [], "characters": [], "relationships": [],
    "timeline": [], "foreshadowing": [], "active_constraints": [],
    "chapter_summaries": [],
    # 新增
    "locations": [],
    "organizations": [],
    "power_systems": [],
    "relationship_graph": [],
}
```

### 阶段二：设定页面 UI（约 4-5 天）

#### 2.1 页面结构

- `render_settings_page(project_name)` — 统一入口，用 `st.tabs` 分四个标签页
- `_render_story_settings_tab()` — 故事设定表单 + 导入/导出操作区
- `_render_project_settings_tab()` — 项目设定表单 + 知识库/资料
- `_render_rules_tab()` — 三级规则编辑
- `_render_story_management_tab()` — 故事列表管理

#### 2.2 合并预览 UI 组件

- `_render_merge_preview(source_label, target_label, merge_plan)` — 通用合并预览组件
- 逐行显示字段名、来源值、目标值
- conflict 字段用 `st.radio` 让用户选择
- 底部确认/取消按钮

#### 2.3 副作用

- sidebar "工作台" 组的页面入口变更：
  - 删除 "核心设定"、"创作配置"，改为 "设定"
  - "交互规则" 不再单独出现（合并进设定→规则标签页）
  - "模型配置" 移入设定→故事管理→底部

### 阶段三：设定驱动生成（约 3-5 天）

#### 3.1 Conflict Policy 驱动冲突处理

- 复制/合并操作中的 `conflict_policy` 字段也可影响默认决议
- 生成步骤中，检索冲突自动按 `conflict_policy` 裁决

#### 3.2 Workflow Depth 下沉到技能层

- `generate_by_profile()` 根据 `workflow_depth` 自动选择执行路径

## 5. 文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `merge.py` | **新建** | 合并引擎：`build_merge_plan()` + `apply_merge_plan()` |
| `context.py` | **新建** | `build_generation_context()` 统一上下文装配 |
| `app.py` | **修改** | 删除 `render_memory_page()`、`render_creative_profile_page()`；新增 `render_settings_page()` + 4 个标签页 + 合并预览组件；sidebar 导航更新 |
| `memory.py` | **修改** | 扩展 `DEFAULT_MEMORY`；新增 `copy_creative_profile()`、`copy_memory_overrides()`、`merge_story_to_project_memory()`、`merge_project_to_story_memory()`、`load/save_story_rules()`、`copy_story()`、`archive_story()` |
| `retrieval.py` | **修改** | 新增 `REFERENCE_FOCUS_SOURCE_MAP` + `REFERENCE_STRENGTH_PARAMS`；`retrieve_context()` 支持 profile 驱动参数 |
| `skills.py` | **修改** | 约 20 个生成函数改调 `build_generation_context()` |
| `prompts.py` | **修改** | `format_rules_for_prompt()` 新增 story_rules 参数 |
| `project_manager.py` | **修改** | 新增故事复制/归档管理函数 |

## 6. 兼容性

- 现有单故事项目无影响，`story_id="default"` 表现不变
- `DEFAULT_MEMORY` 扩展通过 `normalize_memory()` 自动补齐
- 合并引擎仅在用户主动执行复制操作时触发
- 故事级 rules 仅在用户编辑故事规则时才创建文件
- 旧页面函数保留一个版本作为 fallback，确认无误后删除
