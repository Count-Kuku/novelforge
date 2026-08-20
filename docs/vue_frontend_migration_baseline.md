# Vue 前端迁移基线

本文档记录 `VF-0.1` 的只读基线，避免后续 Vue/API 迁移把当前事实误当成目标状态。

## 基线版本

- 仓库版本：`v0.7.1`
- 当前分支：`main`
- 当前 schema：`16`（已完成创作模式 migration；迁移前为 `15`）
- 当前旧前端：Streamlit，入口为根目录 `app.py`
- 当前启动器：根目录 `launcher.py`
- 当前数据权威：SQLite + Markdown/TXT 文件资产
- 当前新前端规划：[vue_frontend_migration_plan.md](vue_frontend_migration_plan.md)

## 已确认的当前入口

| 场景 | 当前入口 |
| --- | --- |
| 应用初始化与顶层路由 | `app.py` |
| 启动/端口/单实例锁 | `launcher.py` |
| 规划与章节写作 | `ui/creation_hub.py`、`ui/outline_page.py`、`ui/volume_outline_page.py`、`ui/arc_outline_page.py`、`ui/chapter_outline_page.py`、`ui/chapter_page.py` |
| 对话创作 | `ui/free_writing/` |
| 资料和知识 | `ui/library_hub.py`、`ui/knowledge_management.py`、`ui/knowledge_center.py` |
| 持久任务 | `ui/ingestion_tasks.py`、`ui/web_research_tasks.py` 与对应 workflow dispatcher |
| 结构化权威 | `storage/db.py`、`storage/schema.py`、`storage/repositories/` |

## 基线验证

已执行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q novelforge storage
git diff --check
```

另外使用临时项目目录验证了：

- 连续 migration 可初始化到 schema `16`。
- 新故事行支持 `planned/conversational`。
- 缺少或非法模式值会归一化为 `planned`。
- 本次验证未访问或修改真实 `data/` 项目。

## 当前依赖状态

- Node.js `v25.9.0`
- npm `11.12.1`
- 当前 `.venv` 已安装 FastAPI `0.141.1`、Uvicorn `0.49.0` 和 `python-multipart`；运行时依赖已加入 `requirements.txt`。
- `frontend/` 已建立 Vue 3 + TypeScript + Vite + Router + Pinia 工程，`package-lock.json` 已生成；类型检查、Vitest 和生产构建均通过。
- FastAPI 已提供 `/api/v1` bootstrap、项目/故事/模式、会话 bundle、SSE 流和生产静态资源托管；`docs/openapi.json` 可由 `tools/export_openapi.py --check` 校验。
- API 冒烟验证覆盖本地 Host、mutation client header、CSP/cache headers、项目/故事/大纲/章节/方向/规则读写、故事复制、知识待审核、来源账本、模型配置脱敏读取、模式切换、会话 bundle、动作/附件/URL 附件校验、SSE 快照/假流和健康检查。

## 保护边界

- launcher 默认选择 Vue；缺少 `frontend/dist/index.html` 时自动回退 Streamlit，也可用 `NOVELFORGE_FRONTEND=streamlit` 显式回退。
- `tools/verify_portable_layout.py` 已提供发布包目录检查；2026-08-20 已使用自包含 Windows Python runtime 重建便携包，并完成包内 FastAPI/Vue API 冒烟（首页、health/schema 16、bootstrap、usage breakdown）。完整干净机 launcher/浏览器/重启矩阵仍需发布机 CI。
- 不删除旧 `ui/`、不重写 workflow、不创建第二套知识/附件/任务存储。
- schema 16 上线前仍需备份真实 `data/`；旧代码不能打开高于其支持版本的数据库。

## 环境限制记录

`tools/verify_db_storage.py` 在本机执行时，既有全局凭据子验证可能因 Windows Credential Manager 返回 `WinError 1312` 而失败；这不是本次 Vue/API 改动引入的 schema 或业务失败。隔离项目、DB-first、故事模式、上下文、FastAPI 和 Vue 验证均独立通过。
