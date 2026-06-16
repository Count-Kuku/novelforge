# 故事空间（Story Spaces）—— 实施方案

## 概述

在现有项目结构下新增"故事"层，实现资料共享 + 故事隔离。一次导入原作设定和结构化知识，在此之上创建多个独立故事，各自拥有独立的大纲、章节、正文、审阅和创作配置。

---

## 存储结构变化

### 当前结构（每项目一个扁平故事）

```
projects/{project}/
├── memory.json
├── creative_profile.json
├── outline.md / outline.discussion.json
├── volumes/ / arcs/ / chapter_outlines/ / chapters/ / reviews/
├── analysis/ / evaluation/ / runs/
├── knowledge/ / retrieval/
```

### 新结构（项目下可含多个故事）

```
projects/{project}/
├── memory.json                 ← 共享基础设定（角色、世界、原作对齐等）
├── rules.json                  ← 共享项目规则
├── knowledge/                  ← 共享结构化知识库
├── retrieval/                  ← 共享检索索引（含向量和外部资料）
│
├── stories/
│   ├── index.json              ← 故事列表、当前激活故事 ID
│   │
│   ├── {story_id}/
│   │   ├── meta.json           ← 故事元信息（名称、描述、状态、创建时间）
│   │   ├── creative_profile.json
│   │   ├── memory_overrides.json ← 仅保存与本故事相关的设定差异
│   │   ├── outline.md
│   │   ├── outline.discussion.json
│   │   ├── volumes/
│   │   ├── arcs/
│   │   ├── chapter_outlines/
│   │   ├── chapters/
│   │   ├── reviews/
│   │   ├── analysis/
│   │   ├── evaluation/
│   │   ├── runs/
│   │   └── retrieval/          ← 故事级冲突裁决、调试记录
│   │
│   └── 故事B/
│       └── ...
```

### 存量项目迁移

首次访问时自动执行一次迁移：将当前项目根目录下的 `outline.md`、`volumes/`、`arcs/`、`chapter_outlines/`、`chapters/`、`reviews/`、`analysis/`、`evaluation/`、`runs/`、`creative_profile.json`、`outline.discussion.json` 等移至 `stories/default/` 下。

---

## 各层职责

| 层级 | 共享内容 | 说明 |
|------|----------|------|
| 项目层 | `memory.json`、`rules.json`、`knowledge/`、`retrieval/` | 所有故事共用；记忆字段中的 canon_mode、world、characters、relationships、timeline、foreshadowing、active_constraints 为基础设定 |
| 故事层 | `creative_profile.json`、`memory_overrides.json`、大纲、章节、审阅、评估、流水线 | 每个故事完全独立；memory_overrides 只存差异（例如"本故事中角色 A 是反派"），加载时与基础记忆合并 |

---

## 内存模型合并规则

`memory.json` 为共享基础。每个故事可持有 `memory_overrides.json`，结构与 `memory.json` 同构但只含差异字段。加载时执行深度合并：

1. 从项目 `memory.json` 加载基础设定
2. 如果故事存在 `memory_overrides.json`，读取并合并到基础之上
3. 字段级覆盖（list 字段：追加而非替换；str 字段：直接覆盖）

`chapter_summaries` 改为故事级存储（存于 `stories/{story_id}/chapter_summaries.json`），不再存在共享 `memory.json` 中。

---

## 修改范围

### 1. `memory.py` —— 存储层

新增函数：
- `stories_index_path(project_name)` → `projects/{project}/stories/index.json`
- `story_path(project_name, story_id)` → `projects/{project}/stories/{story_id}/`
- `story_meta_path(project_name, story_id)`
- `story_memory_overrides_path(project_name, story_id)`
- `story_chapter_summaries_path(project_name, story_id)`
- `load_stories_index(project_name)` → 返回 `{"stories": [...], "active_story_id": "..."}`
- `save_stories_index(project_name, index)`
- `create_story(project_name, story_id, name, description)`
- `delete_story(project_name, story_id)`
- `set_active_story(project_name, story_id)`
- `get_active_story_id(project_name)`
- `load_story_memory(project_name, story_id)` → 加载基础 memory + story overrides 合并后的结果
- `save_story_memory_overrides(project_name, story_id, overrides)`
- `load_story_chapter_summaries(project_name, story_id)` / `save_story_chapter_summaries(...)`
- `migrate_project_to_stories(project_name)` → 存量迁移

修改函数：
- 所有 per-chapter/per-volume/outline 路径从 `project_path(project_name) / ...` 改为 `story_path(project_name, story_id) / ...`，增加 `story_id` 参数
- `load_memory(project_name)` 增加 `story_id` 可选参数，默认 None（返回纯基础）
- `save_memory(project_name, ...)` 保持不变（只写入共享基础）

### 2. `schemas.py` —— 数据模型

新增：
- `StoryMeta(NovelForgeSchema)`：`story_id`, `name`, `description`, `status`, `created_at`, `updated_at`
- `StoriesIndex(NovelForgeSchema)`：`stories: list[StoryMeta]`, `active_story_id: str`

### 3. `skills.py` —— 业务层

为所有故事级操作函数增加可选 `story_id` 参数，默认 `"default"`：
- `generate_outline(project_name, user_idea, story_id="default")`
- `generate_chapter_outline(project_name, chapter_no, ..., story_id="default")`
- `write_chapter(project_name, chapter_no, ..., story_id="default")`
- `review_chapter(...)`、`evaluate_chapter(...)`、各类 `discuss_*`、`approve_*`、`clear_*`
- `run_dynamic_generation_task(...)`、`pipeline_plan_write_review_update(...)`

`_build_rules_text()` 修改：从加载纯 `load_memory(project_name)` 改为 `load_story_memory(project_name, story_id)`，合并基础 + 故事覆盖。

`_build_retrieval_context()` 增加 `story_id` 参数，检索时按 story 过滤章节类 source types。

### 4. `app.py` —— 界面层

侧边栏：
- 在项目选择器下方增加"故事"选择器，仅在有项目时显示
- 列出所有故事，允许切换
- 切换故事时更新 `active_story_id` 并 rerun

故事管理：
- 在项目总览或侧边栏增加"新建故事"入口
- 新建时弹出对话框输入名称和描述
- 自动生成 `story_id`（基于名称的 slug）

页面函数：
- 所有页面级函数增加 `story_id` 参数（从 session_state 或 sidebar 取）
- 更新 `render_sidebar(project_name, projects)` → `render_sidebar(project_name, projects, stories, active_story_id)`

存量迁移：
- 在 `init_project_state()` 中检测是否需要迁移：如果项目目录下有 `outline.md` 但无 `stories/`，则触发一次性迁移
- 迁移后设置 `active_story_id = "default"`

### 5. `retrieval.py` —— 检索层

- `_documents_from_project_files()` 增加 `story_id` 参数
- 检索文档构建时，按 story 分别构建章节/大纲类文档
- 共享类文档（memory、knowledge、external sources）仍属于项目级，不按 story 隔离
- 检索查询时，允许指定 `story_id` 以限定召回范围

### 6. `pipeline.py` —— 流水线

- 流水线状态存储路径从 `runs/` 改为 `stories/{story_id}/runs/`
- `ChapterPipelineState` schema 增加 `story_id` 字段

---

## 实施步骤（分两期）

### 第一期：故事空间 MVP

目标：能创建故事、切换故事、在选定故事下完成全套创作流程

1. `memory.py`：新增 stories 路径函数、CRUD、合并加载、迁移函数
2. `schemas.py`：新增 StoryMeta、StoriesIndex
3. `app.py` 侧边栏：故事选择器、新建故事入口
4. `app.py` 所有页面：串联 `story_id` 参数
5. `skills.py`：所有函数增加 `story_id` 参数（默认 `"default"`）
6. 存量迁移逻辑：`init_project_state()` 中检测并执行一次迁移

#### 第一期不改的部分

- 检索层仍然共享（story 隔离放第二期）
- `memory.json` 故事覆盖走简单 merge，不做深层 diff
- 不涉及大范围 UI 重构

### 第二期：故事隔离与增强

1. 检索按故事隔离
2. 记忆覆盖的 UI 编辑界面
3. 故事间拷贝/迁移功能（例如把故事 A 的章节复制到故事 B）
4. 故事级角色关系差异的冲突提示

---

## 涉及文件清单

| 文件 | 改动规模 | 主要变更 |
|------|---------|---------|
| `memory.py` | 大 | 新增 stories 路径/CURD/合并/迁移；所有路径函数加 story_id |
| `schemas.py` | 小 | 新增 StoryMeta、StoriesIndex |
| `skills.py` | 大 | 所有函数加 story_id 参数；`_build_rules_text` 改用合并内存 |
| `app.py` | 中 | 侧边栏加故事选择器；所有页面串联 story_id |
| `retrieval.py` | 小 | 文档构建/检索可选 story_id |
| `prompts.py` | 无 | 不直接改动（通过 skills.py 间接传入 story 上下文） |

---

## 存量项目迁移细节

迁移函数 `migrate_project_to_stories(project_name)`：

```
1. 检查迁移标记: projects/{project}/.migrated
2. 如已迁移 → 跳过
3. 创建 stories/default/
4. 移动: outline.md, outline.discussion.json, creative_profile.json, creative_profile.discussion.json
5. 移动: volumes/ / arcs/ / chapter_outlines/ / chapters/ / reviews/
6. 移动: analysis/ / evaluation/ / runs/
7. 移动: retrieval/ (冲突裁决等故事级索引)
8. 创建 stories/index.json, 设 active_story_id = "default"
9. 写入 .migrated 标记
```

---

## 风险与注意事项

1. `memory.json` 中的 `chapter_summaries` 需要拆分出到故事层——迁移时提取到 `stories/default/chapter_summaries.json` 并清空共享字段
2. 现有的 `_build_rules_text()` 和 `_format_discussion_context()` 直接或间接加载 memory，需要确保它们正确使用 story 合并后的内存
3. 大纲/分卷/剧情段的编号（volume_no, arc_no, chapter_no）是 per-story 的，不同故事的同序号文件不会冲突
4. 首次迁移是一次的，建议加 `.migrated` 标记文件防止意外重复执行
