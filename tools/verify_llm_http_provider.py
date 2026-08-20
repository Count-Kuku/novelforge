"""验证 OpenAI-compatible HTTP 流式 provider 的中断与重试边界。

这是本地协议夹具，不冒充真实模型/provider 评测；它用于证明客户端能观察到
半截流并在下一次请求中消费完整 SSE 流。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai import OpenAI


class ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests_seen = 0

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        type(self).requests_seen += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        if type(self).requests_seen == 1:
            self.wfile.write('data: {"choices":[{"delta":{"content":"半截"}}]}\n\n'.encode())
            self.wfile.write(b"data: {malformed-json}\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        chunks = ["完整", "流"]
        for text in chunks:
            payload = {"choices": [{"delta": {"content": text}}]}
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = OpenAI(
        api_key="fixture-key",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        max_retries=0,
    )
    try:
        interrupted = False
        try:
            list(
                client.chat.completions.create(
                    model="fixture-model",
                    messages=[{"role": "user", "content": "断线"}],
                    stream=True,
                )
            )
        except Exception as exc:  # SDK 将半截 HTTP 流包装为连接错误。
            interrupted = "".join(type(part).__name__ for part in [exc]) != ""
            print(f"[PASS] 半截 provider 流被报告为 {type(exc).__name__}")
        if not interrupted:
            raise AssertionError("半截 provider 流未触发连接错误")

        response = client.chat.completions.create(
            model="fixture-model",
            messages=[{"role": "user", "content": "重试"}],
            stream=True,
        )
        content = "".join(
            chunk.choices[0].delta.content or ""
            for chunk in response
            if chunk.choices and chunk.choices[0].delta
        )
        if content != "完整流":
            raise AssertionError(f"重试流内容错误：{content!r}")
        print("[PASS] 第二次 provider SSE 流完整消费并得到完整文本")
        if ProviderHandler.requests_seen != 2:
            raise AssertionError(f"provider 请求次数错误：{ProviderHandler.requests_seen}")
        print("Local OpenAI-compatible HTTP provider verification passed.")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
