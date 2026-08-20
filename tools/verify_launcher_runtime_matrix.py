"""在临时 data root 上运行真实 launcher 子进程并验证启动矩阵。"""
from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import launcher  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind((launcher.HOST, 0))
        return int(sock.getsockname()[1])


class MarkerHandler(http.server.BaseHTTPRequestHandler):
    marker = "other application"

    def do_GET(self) -> None:  # noqa: N802
        payload = f"<html><body>{self.marker}</body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args) -> None:
        return


def occupy(port: int, marker: str):
    handler = type("ProbeMarkerHandler", (MarkerHandler,), {"marker": marker})
    server = http.server.ThreadingHTTPServer((launcher.HOST, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.kill(pid, 15)


def main() -> int:
    port_a, port_b = free_port(), free_port()
    while port_b == port_a:
        port_b = free_port()
    old_candidates = launcher.PORT_CANDIDATES
    old_default = launcher.DEFAULT_PORT
    old_timeout = launcher.READY_TIMEOUT_SECONDS
    old_python_path = os.environ.get("PYTHONPATH")
    browser_calls: list[str] = []
    child_pid = 0
    try:
        launcher.PORT_CANDIDATES = [port_a, port_b]
        launcher.DEFAULT_PORT = port_a
        launcher.READY_TIMEOUT_SECONDS = 15
        os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
        os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + str(os.environ.get("PYTHONPATH") or "")
        with tempfile.TemporaryDirectory(prefix="novelforge-launcher-runtime-") as temp_dir:
            root = Path(temp_dir)
            shutil.copytree(ROOT / "frontend" / "dist", root / "frontend" / "dist")
            with (
                patch.object(launcher, "_project_root", return_value=root),
                patch.object(launcher, "_resolve_python", return_value=Path(sys.executable)),
                patch.object(launcher.webbrowser, "open", side_effect=lambda url: browser_calls.append(url) or True),
            ):
                result = launcher.main()
                check(result == 0, "真实 launcher 子进程启动 FastAPI/Vue 并通过 ready")
                state = launcher._load_server_state(root)
                child_pid = int(state.get("pid") or 0)
                check(child_pid > 0 and launcher._process_is_running(child_pid), "launcher 持久化运行中的 pid/port 状态")
                selected, conflict = launcher._find_available_port(root)
                check(selected is None and conflict is None, "已有本项目实例不会重复启动")

                stop_pid(child_pid)
                for _ in range(30):
                    if not launcher._process_is_running(child_pid):
                        break
                    time.sleep(0.2)
                check(not launcher._process_is_running(child_pid), "停止后子进程确实退出")
                selected, conflict = launcher._find_available_port(root)
                check(selected == port_a and conflict is None, "陈旧状态清理后可重新选择默认端口")

                other = occupy(port_a, "unrelated application")
                try:
                    selected, conflict = launcher._find_available_port(root)
                    check(selected == port_b and conflict == port_a, "非 NovelForge 端口冲突会回退候选端口")
                finally:
                    other.shutdown()
                    other.server_close()

                existing = occupy(port_a, "NovelForge")
                try:
                    selected, conflict = launcher._find_available_port(root)
                    check(selected is None and conflict is None, "已存在 NovelForge 页面时只复用实例")
                finally:
                    existing.shutdown()
                    existing.server_close()
    finally:
        if child_pid and launcher._process_is_running(child_pid):
            stop_pid(child_pid)
        launcher.PORT_CANDIDATES = old_candidates
        launcher.DEFAULT_PORT = old_default
        launcher.READY_TIMEOUT_SECONDS = old_timeout
        if old_python_path is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = old_python_path
        os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
    print("Launcher runtime matrix verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
