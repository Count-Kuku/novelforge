# ADR-001：Vue 双工作台迁移架构

状态：已接受（2026-08-19）

## 决策

- 前端使用 Vue 3 + TypeScript + Vite；路由使用 `vue-router`，跨页面客户端状态使用 `pinia`。
- 前端依赖由 `frontend/package.json` 和 `frontend/package-lock.json` 固定，发布阶段只执行 `npm ci` 和 `npm run build`；Node.js 不进入运行时便携包。
- FastAPI 作为唯一 Vue HTTP 边界，静态构建产物由同一进程托管；开发环境使用 Vite proxy。
- 规划创作和对话创作使用两个独立 Layout，而不是在同一页面内堆叠按钮。故事的 `creation_mode` 由 SQLite 权威存储。
- 生成流使用 SSE。当前工作流是服务端同步函数，使用后台线程和队列桥接为 SSE；后续 durable operation 仍通过独立 operation registry 演进，不把临时流伪装成 workflow run。
- 采用浏览器式本地应用，不引入 Electron/Tauri；launcher 负责启动 FastAPI，缺少 Vue 构建产物时可回退 Streamlit。

## 放弃的方案

- 不再扩展 Streamlit 作为新 UI 技术；其只承担兼容窗口和回退入口。
- 不使用 WebSocket：当前事件是单向服务端流，SSE 更适合断线重连、HTTP 代理和本地部署。
- 不在 Vue 中复制领域判断；故事模式、上下文策略、资产级联和维护锁继续由 Python domain/service/workflow 负责。

## 迁移边界

`novelforge/api/` 只依赖公开 memory/project/workflow 门面。`frontend/src/api/client.ts` 是浏览器唯一请求入口；DTO 与 OpenAPI 文档由 `tools/export_openapi.py` 导出并可用 `--check` 检查漂移。
