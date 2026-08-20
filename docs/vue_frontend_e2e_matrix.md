# Vue 双工作台验收矩阵

本矩阵把浏览器端验收路径固定下来，避免把“首页能打开”误当成迁移完成。当前仓库已执行 API smoke、Vitest、TypeScript、生产构建和 Playwright Chromium + Edge；真实模型长流、物理 IME、长会话与发布机矩阵仍需 CI 夹具。

| 旅程 | 规划工作台 | 对话工作台 | 当前自动化证据 |
| --- | --- | --- | --- |
| 新建项目/故事 | 选择 `planned` 后进入 `/planned` | 选择 `conversational` 后进入 `/conversational` | `verify_api_smoke.py`、路由单测 |
| 切换故事与模式 | 侧栏故事选择、切换到对话 | 侧栏故事选择、切换到规划 | `verify_creation_modes.py` |
| 大纲/方向 | profile、outline 读写与 context checker | 不展示规划导航 | API smoke、Vue build |
| 章节工作台 | 结构树、章节细纲/正文编辑 | 不展示规划导航 | API smoke、Vue build |
| 连续创作 | 共享工作区 | 会话创建、SSE 增量、接受/重写/分支、会话重命名 | `verify_interactive_writing.py`、API smoke |
| 附件 | 共享资料入口 | 粘贴资料托盘、URL/文件上传、会话附件列表、后台进度与失败重试 | API smoke、Vue build |
| 任务/能力 | 共享工作区与设置页 | 共享工作区与设置页、上下文预算预览 | API smoke、Vue build |
| 危险操作 | 重命名、归档、项目名称确认删除 | 故事归档、项目名称确认删除 | API mutation guard、idempotency smoke |
| 刷新/断线 | SSE heartbeat、operation replay | SSE heartbeat、operation replay | API smoke、Vitest operation replay fixture |
| 浏览器入口/路由刷新 | 模式入口、移动布局、键盘焦点、刷新 | 模式入口、移动布局、键盘焦点、刷新 | `npm run test:e2e`（5 passed，2026-08-20） |
| 截图/性能 | 移动视口与 1440/1280/1024/768 桌面截图、DOMContentLoaded < 1.5s、reduced-motion | 同左 | Playwright `test-results/` |

## 浏览器执行参数

- 视口：1440×900、1280×800、1024×768、768×1024。
- 重点：中文 IME 组合输入、Ctrl/⌘+Enter、Reduced Motion、键盘焦点、错误/加载/禁用状态。
- 禁止：真实付费模型、真实搜索服务、真实用户项目和真实密钥。
- 发布机应先执行 `npm ci`、`npm run typecheck`、`npm run test:unit`、`npm run build`，再启动 FastAPI 后运行 Playwright。
- 当前 Playwright 配置优先使用本机 Chromium for Testing；CI 若使用默认浏览器缓存，删除 `executablePath` 回退即可。

## 本轮浏览器探针（2026-08-19）

- 使用本地 FastAPI/Vue 构建在 `127.0.0.1:8766` 实际打开模式选择页、规划工作台和对话工作台，检查 DOM 可访问名称、双 Layout 导航隔离、关系图/研究/规则入口以及空状态。
- 额外用 `768×900` 临时视口检查对话工作台响应式 DOM，随后已恢复浏览器默认视口。
- 该探针不是 Playwright CI 替代；多视口截图、IME、断线恢复和长文本性能仍需在发布机完成。

## 便携包实机探针（2026-08-20）

- 使用 `build_release.ps1` 搭配自包含 Windows Python runtime 重建 `release/NovelForge-windows-portable-v0.7.1.zip`。
- `tools/verify_portable_layout.py` 通过；包内 `frontend/dist/index.html`、`novelforge/api/app.py` 和 `.runtime/python.exe` 均存在。
- 使用包内 runtime + 显式便携根路径启动 FastAPI，实际请求 `/`、`/api/v1/health/ready`（schema 16）、`/api/v1/bootstrap` 与 `/api/v1/usage/breakdown` 成功；完整 launcher、浏览器自动打开、端口冲突、重启恢复仍需干净 Windows CI。

## Playwright 自动化（2026-08-20）

- `frontend/tests/e2e/workspace.spec.ts` 覆盖双工作台入口、移动视口无横向溢出、键盘焦点、首屏性能、两套 Layout 路由隔离和刷新恢复。
- 本机 Chromium + Edge E2E：16 passed（8 个场景 × 2 浏览器）；截图写入 `frontend/test-results/`，报告写入 `frontend/playwright-report/`。覆盖双 Layout 的 WCAG 2A/2AA Axe 扫描、组合输入保护、8,000 次长草稿和移动无横向溢出。
- 服务端开发者投影守卫、`tools.verify_ocr_progress_fixture` 与 `tools.verify_ocr_api` 已通过；普通用户不返回/不展示原始 JSON，OCR fixture 覆盖 3 页逐页进度、预览响应与置信度告警；前端 SSE operation replay fixture 也已通过。
- `tools.verify_legacy_db_upgrade`、`tools.verify_llm_http_provider`、`tools.verify_launcher_runtime_matrix` 已通过；其中 launcher 夹具真实启动 FastAPI/Vue 子进程并覆盖端口/实例/重启状态。
- `.github/workflows/vue-migration-windows.yml` 提供 Windows clean-runner 入口；手动触发并配置 `NOVELFORGE_LLM_API_KEY/BASE_URL/MODEL` secrets 时，额外执行真实 provider 流式 smoke。
- 干净 Windows 的人工签收步骤见 `docs/releases/v0.7.1-clean-windows-checklist.md`，包含无 Node、端口/实例/重启、物理中文 IME 和兼容窗口记录。
- 尚未宣称全量浏览器完成：真实模型生成流断线恢复、物理中文 IME、真实临时后端长会话/大资料压力和干净 Windows launcher 权限/浏览器打开/无 Node 矩阵仍需 CI/发布机执行；Edge 浏览器本机矩阵已通过。
