import os
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


HOST = "127.0.0.1"
DEFAULT_PORT = 8501
PORT_CANDIDATES = [8501, 8502, 8503, 8504, 8505]
READY_TIMEOUT_SECONDS = 45
READY_POLL_INTERVAL_SECONDS = 0.5
APP_MARKER = "NovelForge"
LOG_FILE_NAME = "launcher.log"


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _app_entrypoint(root: Path) -> Path:
    return root / "app.py"


def _log_path(root: Path) -> Path:
    return root / LOG_FILE_NAME


def _write_log(root: Path, message: str, append: bool = True):
    mode = "a" if append else "w"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log_path(root).open(mode, encoding="utf-8").write(f"[{timestamp}] {message}\n")


def _show_error(message: str):
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "NovelForge Launcher", 0x10)
            return
        except Exception:
            pass
    sys.stderr.write(f"NovelForge Launcher Error: {message}\n")


def _launch_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def _python_candidates(root: Path) -> list[Path]:
    return [
        root / ".venv" / "Scripts" / "pythonw.exe",
        root / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]


def _resolve_python(root: Path) -> Path:
    for candidate in _python_candidates(root):
        if candidate.exists():
            return candidate
    raise RuntimeError("No bundled Python runtime found. Expected .venv\\Scripts\\pythonw.exe or python.exe.")


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _fetch_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": "NovelForge-Launcher/1.0"})
    with urlopen(request, timeout=2) as response:
        return response.read().decode("utf-8", errors="ignore")


def _is_novelforge_instance(url: str) -> bool:
    try:
        return APP_MARKER in _fetch_page(url)
    except Exception:
        return False


def _find_available_port(root: Path) -> tuple[int | None, int | None]:
    first_conflicting_port = None
    for port in PORT_CANDIDATES:
        url = _launch_url(port)
        if not _is_port_open(HOST, port):
            return port, first_conflicting_port
        if _is_novelforge_instance(url):
            _write_log(root, f"Detected existing NovelForge instance on port {port}", append=True)
            webbrowser.open(url)
            return None, None
        if first_conflicting_port is None:
            first_conflicting_port = port
            _write_log(root, f"Port {port} is occupied by another application", append=True)
    return None, first_conflicting_port


def _wait_for_http_ready(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            request = Request(url, headers={"User-Agent": "NovelForge-Launcher/1.0"})
            with urlopen(request, timeout=2) as response:
                page = response.read().decode("utf-8", errors="ignore")
                if response.status < 500 and APP_MARKER in page:
                    return True
        except Exception:
            time.sleep(READY_POLL_INTERVAL_SECONDS)
    return False


def _launch_streamlit(root: Path, python_executable: Path, port: int):
    app_path = _app_entrypoint(root)
    if not app_path.exists():
        raise RuntimeError(f"Missing application entrypoint: {app_path}")

    streamlit_command = [
        str(python_executable),
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.port",
        str(port),
        "--server.address",
        HOST,
    ]

    creation_flags = 0
    startupinfo = None
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    _write_log(root, f"Launching Streamlit with Python: {python_executable}", append=True)
    _write_log(root, f"Working directory: {root}", append=True)
    _write_log(root, f"Target URL: {_launch_url(port)}", append=True)
    log_file = _log_path(root).open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            streamlit_command,
            cwd=root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            startupinfo=startupinfo,
        )
        _write_log(root, f"Spawned process with pid={process.pid}", append=True)
        return process
    except Exception:
        log_file.close()
        raise
    finally:
        log_file.close()


def _cleanup_process(root: Path, process: subprocess.Popen):
    if process.poll() is not None:
        return
    _write_log(root, f"Stopping process pid={process.pid} after launch failure", append=True)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _write_log(root, f"Force killing process pid={process.pid}", append=True)
        process.kill()


def _fail(root: Path, message: str) -> int:
    _write_log(root, f"ERROR: {message}", append=True)
    _show_error(f"{message}\n\nSee {LOG_FILE_NAME} for details.")
    return 1


def main() -> int:
    root = _project_root()
    _write_log(root, "=== Launcher started ===", append=False)
    _write_log(root, f"Port candidates: {', '.join(str(port) for port in PORT_CANDIDATES)}", append=True)

    selected_port, conflicting_port = _find_available_port(root)
    if selected_port is None:
        if conflicting_port is None:
            return 0
        return _fail(root, f"All candidate ports are unavailable. First conflicting port: {conflicting_port}.")

    app_url = _launch_url(selected_port)
    if selected_port != DEFAULT_PORT:
        _write_log(root, f"Falling back from default port {DEFAULT_PORT} to {selected_port}", append=True)

    try:
        python_executable = _resolve_python(root)
    except Exception as exc:
        return _fail(root, str(exc))

    try:
        process = _launch_streamlit(root, python_executable, selected_port)
    except Exception as exc:
        return _fail(root, f"Failed to launch Streamlit: {exc}")

    if _wait_for_http_ready(app_url, READY_TIMEOUT_SECONDS):
        _write_log(root, f"NovelForge became ready on port {selected_port}; opening browser", append=True)
        webbrowser.open(app_url)
        return 0

    if process.poll() is not None:
        return _fail(root, f"NovelForge exited early with code {process.returncode}.")

    _cleanup_process(root, process)
    return _fail(root, f"NovelForge did not become ready on port {selected_port} within {READY_TIMEOUT_SECONDS} seconds.")


if __name__ == "__main__":
    raise SystemExit(main())
