# ADR-002：本地 API、SSE 与安全边界

状态：已接受（2026-08-19）

- API 前缀固定为 `/api/v1`，成功响应使用 `{data, meta}`，失败响应使用 `{error, meta}`；每个请求携带 `request_id` 和 `X-Request-Id`。
- 除 GET/HEAD/OPTIONS 外，写操作要求 `X-NovelForge-Client: vue`；Vue client 为 mutation 自动生成 `Idempotency-Key`。
- 默认只接受 `127.0.0.1`、`localhost` 和测试客户端 Host；需要远程部署时必须显式设置 `NOVELFORGE_ALLOW_REMOTE=1` 并由部署层提供认证与 TLS。
- CORS 仅开放 Vite 开发地址；生产静态资源同源，不开放通配来源。
- 响应统一添加 `nosniff`、`no-referrer`、`DENY` frame policy 和最小 CSP。
- SSE 事件至少包含 `event`、JSON `data` 和单调递增 `id`；订阅断开不等于取消工作流，取消应走独立 mutation。

## 已知后续项

当前临时流的终态缓存和可恢复 operation registry 尚未替代，真实长任务仍需在后续阶段接入 durable task dispatcher；这不改变 API envelope 或 SSE 事件命名。
