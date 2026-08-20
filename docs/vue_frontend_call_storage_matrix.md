# Vue 迁移页面—调用—存储矩阵

这张矩阵是迁移期间的追踪表。Vue 不直接复制 Streamlit renderer 内的业务判断；每一行都先指向现有 Python 门面，再由 FastAPI 暴露稳定 DTO。

| Vue 工作区 | 主要读取 | 写入/生成 | 权威存储 | 当前迁移状态 |
| --- | --- | --- | --- | --- |
| 启动/模式选择 | bootstrap、项目、故事模式 | 创建项目、创建故事、切换模式 | `project_meta`、`stories` | 已接通 |
| 对话会话侧栏 | `list_creative_sessions`、bundle | `create_writing_session`、归档/重命名 | `creative_sessions`、`creative_turns`、`creative_fragments` | 已接通；大数据分页待优化 |
| 对话正文 | session bundle、片段链、context preview | `generate_writing_fragment`、accept/rewrite/branch、上下文检查 | creative tables、generation snapshot、usage ledger | SSE、片段操作、版本时间线、上下文预算和用量面板已接通 |
| 对话知识抽屉 | pending knowledge、references | confirm/ignore/edit knowledge | knowledge tables、asset payloads | 待确认列表、确认/忽略和知识 API 已接通 |
| 规划方向 | creative profile、rules、discussion artifact | discussion、profile 保存、自动配置 | story profile、rules、discussion assets | 方向表单、讨论流、批准和规则读取已接通 |
| 全书/分卷/剧情段 | outline/volume/arc facade、arc chapter plan | discussion、生成、保存、章节计划、删除、结构校验 | story assets + DB asset registry | 大纲、卷/段讨论流、批准、编辑器、分卷/剧情段删除、章节计划和重复/跨段/数量冲突校验已接通 |
| 章节细纲/正文 | chapter outline/content/review、workflow runs | edit/save/review、chapter discussion | Markdown + asset registry + workflow runs | 章节编辑、正文保存、审阅投影、结构上下文、章节讨论和版本时间线已接通 |
| 项目概览/内容浏览 | project summary、resource browser | 安全删除、复制、定位、分页 | `project_manager` + asset registry | 摘要、知识详情、故事复制、内容游标分页和确认式安全删除 API/UI 已接通 |
| 资料/知识/检索 | retrieval/search/knowledge facades、entity projections | import、confirm、修订、证据、评测、来源激活 | SQLite retrieval/knowledge tables | 游标/类型搜索、URL 查询恢复、固定窗口虚拟列表、类型 schema、修订/恢复/对比、revision 冲突、证据摘录高亮/手动合并、角色/设定/时间线、批次健康、关系图、研究工作区、批量导入 OCR 预览已接通；真实 OCR/provider 评测仍待发布环境 |
| 设置/任务 | credentials、capabilities、dispatchers、usage、automatic configuration | write-only secret、规则/提示词三层编辑、pause/resume/retry/cancel、研究结论送审、用量读取/分组 | `.env`/credential store、task tables、global usage ledger | 能力、脱敏模型配置、活动模型切换、规则/偏好、自动配置原因/锁定字段、任务控制、研究来源激活/结论审核和今日/月度/项目/故事/模型/操作/Agent 用量检查器已接通 |

## 路由与模式边界

- `/planned/*` 只渲染 `PlannedAppLayout`，由故事 `creation_mode=planned` guard 进入。
- `/conversational/*` 只渲染 `ConversationalAppLayout`，对话故事默认会话 `auto_extract_mode=on_accept`。
- 两种模式共用项目、故事、SQLite、文件资产和 API client；不在浏览器另建数据权威。
