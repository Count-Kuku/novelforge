import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Iterator
from urllib.request import Request, urlopen


HOST = "127.0.0.1"
DEFAULT_PORT = 8501
PORT_CANDIDATES = [8501, 8502, 8503, 8504, 8505]
READY_TIMEOUT_SECONDS = 45
READY_POLL_INTERVAL_SECONDS = 0.5
APP_MARKER = "NovelForge"
LOG_FILE_NAME = "launcher.log"
SERVER_STATE_FILE_NAME = ".novelforge-server.json"
LAUNCH_LOCK_FILE_NAME = ".novelforge-launch.lock"
LAUNCH_LOCK_TIMEOUT_SECONDS = 15
LAUNCH_LOCK_POLL_INTERVAL_SECONDS = 0.1
STREAMLIT_MARKERS = ("streamlit", "stapp")
FRONTEND_ENV_NAME = "NOVELFORGE_FRONTEND"


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _app_entrypoint(root: Path) -> Path:
    return root / "app.py"


def _frontend_dist(root: Path) -> Path:
    return root / "frontend" / "dist"


def _frontend_mode(root: Path) -> str:
    requested = str(os.environ.get(FRONTEND_ENV_NAME, "vue") or "vue").strip().lower()
    if requested not in {"vue", "streamlit"}:
        requested = "vue"
    if requested == "vue" and not (_frontend_dist(root) / "index.html").exists():
        _write_log(root, "Vue bundle is missing; falling back to Streamlit compatibility mode", append=True)
        return "streamlit"
    return requested


def _log_path(root: Path) -> Path:
    return root / LOG_FILE_NAME


def _server_state_path(root: Path) -> Path:
    return root / SERVER_STATE_FILE_NAME


def _launch_lock_path(root: Path) -> Path:
    return root / LAUNCH_LOCK_FILE_NAME


def _load_server_state(root: Path) -> dict:
    try:
        payload = json.loads(_server_state_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not process:
                return False
            ctypes.windll.kernel32.CloseHandle(process)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_server_state(root: Path, pid: int, port: int) -> None:
    state_path = _server_state_path(root)
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "pid": int(pid),
                "port": int(port),
                "root": str(root.resolve()),
                "started_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(state_path)


def _remove_server_state(root: Path, expected_pid: int | None = None) -> None:
    state_path = _server_state_path(root)
    if expected_pid is not None:
        state = _load_server_state(root)
        if int(state.get("pid") or 0) != expected_pid:
            return
    try:
        state_path.unlink(missing_ok=True)
    except OSError:
        pass


def _read_launch_lock_owner(handle: BinaryIO) -> dict:
    try:
        handle.seek(0)
        raw = handle.read().decode("utf-8", errors="ignore").strip()
        payload = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _try_lock_launch_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_launch_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _launcher_lock(root: Path) -> Iterator[None]:
    """Serialize port selection and process registration across launchers.

    The file is intentionally persistent: unlinking an advisory-lock file can
    create two independently locked inodes during a hand-off. Kernel locks are
    released automatically after a crash, so stale metadata never blocks the
    next launcher and is overwritten by the next lock owner.
    """

    lock_path = _launch_lock_path(root)
    handle = lock_path.open("a+b")
    acquired = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b" ")
            handle.flush()

        deadline = time.monotonic() + LAUNCH_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                _try_lock_launch_file(handle)
                acquired = True
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    owner = _read_launch_lock_owner(handle)
                    owner_pid = int(owner.get("pid") or 0)
                    owner_text = f" pid={owner_pid}" if owner_pid else ""
                    raise RuntimeError(
                        "Another NovelForge launcher is still preparing the server"
                        f"{owner_text}. Please try again shortly."
                    )
                time.sleep(LAUNCH_LOCK_POLL_INTERVAL_SECONDS)

        previous_owner = _read_launch_lock_owner(handle)
        previous_pid = int(previous_owner.get("pid") or 0)
        if previous_pid and previous_pid != os.getpid():
            _write_log(
                root,
                f"Recovered launcher lock metadata from pid={previous_pid}",
                append=True,
            )

        payload = {
            "pid": os.getpid(),
            "root": str(root.resolve()),
            "acquired_at": datetime.now().isoformat(timespec="seconds"),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
        yield
    finally:
        if acquired:
            try:
                handle.seek(0)
                handle.truncate()
                handle.write(b" ")
                handle.flush()
            except OSError:
                pass
            try:
                _unlock_launch_file(handle)
            except OSError:
                pass
        handle.close()


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
    portable_candidates: list[Path]
    if os.name == "nt":
        portable_candidates = [
            root / ".runtime" / "pythonw.exe",
            root / ".runtime" / "python.exe",
        ]
        development_candidates = [
            root / ".venv" / "Scripts" / "pythonw.exe",
            root / ".venv" / "Scripts" / "python.exe",
        ]
    else:
        portable_candidates = [
            root / ".runtime" / "bin" / "python3",
            root / ".runtime" / "bin" / "python",
        ]
        development_candidates = [
            root / ".venv" / "bin" / "python3",
            root / ".venv" / "bin" / "python",
        ]
    if getattr(sys, "frozen", False):
        # A copied venv contains an absolute pyvenv.cfg reference to its build
        # machine and is not a portable runtime. Release launchers accept only
        # the explicitly assembled self-contained distribution.
        return portable_candidates
    return [*development_candidates, *portable_candidates, Path(sys.executable)]


def _resolve_python(root: Path) -> Path:
    launcher_executable = Path(sys.executable).resolve()
    for candidate in _python_candidates(root):
        if candidate.exists() and not (
            getattr(sys, "frozen", False) and candidate.resolve() == launcher_executable
        ):
            return candidate
    raise RuntimeError(
        "No usable Python runtime found. Portable releases require "
        ".runtime/pythonw.exe or .runtime/python.exe; development runs require .venv."
    )


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


def _looks_like_streamlit_shell(page: str) -> bool:
    lowered = str(page or "").lower()
    return any(marker in lowered for marker in STREAMLIT_MARKERS)


def _clean_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = {}
    seen_keys: set[str] = set()
    for key, value in os.environ.items():
        normalized = key.upper() if os.name == "nt" else key
        if normalized == "PATH":
            env["Path" if os.name == "nt" else "PATH"] = value
            seen_keys.add(normalized)
        elif normalized not in seen_keys:
            env[key] = value
            seen_keys.add(normalized)
    return env


def _find_available_port(root: Path) -> tuple[int | None, int | None]:
    state = _load_server_state(root)
    state_pid = int(state.get("pid") or 0)
    state_port = int(state.get("port") or 0)
    state_root = str(state.get("root") or "")
    if state_root == str(root.resolve()) and state_port in PORT_CANDIDATES and _process_is_running(state_pid):
        url = _launch_url(state_port)
        if _is_port_open(HOST, state_port):
            try:
                trusted_page = _fetch_page(url)
            except Exception:
                trusted_page = ""
            if APP_MARKER in trusted_page or _looks_like_streamlit_shell(trusted_page):
                _write_log(root, f"Detected tracked NovelForge process pid={state_pid} on port {state_port}", append=True)
                webbrowser.open(url)
                return None, None
        # The tracked process may still be starting. Do not race it for the
        # same project directory or launch a duplicate server.
        _write_log(root, f"Tracked NovelForge process pid={state_pid} is still starting on port {state_port}", append=True)
        webbrowser.open(url)
        return None, None
    if state:
        _remove_server_state(root)

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
                if response.status < 500 and (APP_MARKER in page or _looks_like_streamlit_shell(page)):
                    return True
        except Exception:
            time.sleep(READY_POLL_INTERVAL_SECONDS)
    return False


def _spawn_server_process(
    root: Path,
    python_executable: Path,
    port: int,
    command: list[str],
    label: str,
):
    creation_flags = 0
    startupinfo = None
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    _write_log(root, f"Launching {label} with Python: {python_executable}", append=True)
    _write_log(root, f"Working directory: {root}", append=True)
    _write_log(root, f"Target URL: {_launch_url(port)}", append=True)
    log_file = _log_path(root).open("a", encoding="utf-8")
    try:
        child_env = _clean_subprocess_env()
        # The portable distribution uses Python's embeddable runtime, whose
        # ``python314._pth`` intentionally disables the implicit current
        # working-directory import path.  Explicitly prepend the extracted
        # application root so ``novelforge`` and sibling packages resolve in
        # both FastAPI/Vue and Streamlit compatibility launches.
        project_path = str(root.resolve())
        existing_python_path = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = (
            project_path
            if not existing_python_path
            else project_path + os.pathsep + existing_python_path
        )
        process = subprocess.Popen(
            command,
            cwd=root,
            env=child_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            startupinfo=startupinfo,
        )
        try:
            _write_server_state(root, process.pid, port)
        except OSError as exc:
            _write_log(root, f"Failed to persist server state: {exc}", append=True)
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise RuntimeError(
                "Failed to register the launched server; the child process was stopped."
            ) from exc
        _write_log(root, f"Spawned process with pid={process.pid}", append=True)
        return process
    finally:
        log_file.close()


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
        "--client.toolbarMode",
        "minimal",
        "--theme.base",
        "light",
        "--theme.primaryColor",
        "#0f766e",
        "--theme.backgroundColor",
        "#f7f8fb",
        "--theme.secondaryBackgroundColor",
        "#ffffff",
        "--theme.textColor",
        "#17202a",
        "--server.port",
        str(port),
        "--server.address",
        HOST,
    ]

    return _spawn_server_process(root, python_executable, port, streamlit_command, "Streamlit")


def _launch_fastapi(root: Path, python_executable: Path, port: int):
    command = [
        str(python_executable),
        "-m",
        "uvicorn",
        "novelforge.api.app:app",
        "--host",
        HOST,
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    return _spawn_server_process(root, python_executable, port, command, "FastAPI/Vue")


def _cleanup_process(root: Path, process: subprocess.Popen):
    if process.poll() is not None:
        _remove_server_state(root, expected_pid=process.pid)
        return
    _write_log(root, f"Stopping process pid={process.pid} after launch failure", append=True)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _write_log(root, f"Force killing process pid={process.pid}", append=True)
        process.kill()
    finally:
        _remove_server_state(root, expected_pid=process.pid)


def _fail(root: Path, message: str) -> int:
    _write_log(root, f"ERROR: {message}", append=True)
    _show_error(f"{message}\n\nSee {LOG_FILE_NAME} for details.")
    return 1


def main() -> int:
    root = _project_root()
    try:
        with _launcher_lock(root):
            _write_log(root, "=== Launcher started ===", append=True)
            _write_log(
                root,
                f"Port candidates: {', '.join(str(port) for port in PORT_CANDIDATES)}",
                append=True,
            )

            selected_port, conflicting_port = _find_available_port(root)
            if selected_port is None:
                if conflicting_port is None:
                    return 0
                return _fail(
                    root,
                    "All candidate ports are unavailable. "
                    f"First conflicting port: {conflicting_port}.",
                )

            app_url = _launch_url(selected_port)
            if selected_port != DEFAULT_PORT:
                _write_log(
                    root,
                    f"Falling back from default port {DEFAULT_PORT} to {selected_port}",
                    append=True,
                )

            python_executable = _resolve_python(root)
            frontend_mode = _frontend_mode(root)
            _write_log(root, f"Selected frontend mode: {frontend_mode}", append=True)
            process = (
                _launch_fastapi(root, python_executable, selected_port)
                if frontend_mode == "vue"
                else _launch_streamlit(root, python_executable, selected_port)
            )
    except Exception as exc:
        return _fail(root, f"Failed to prepare or launch NovelForge: {exc}")

    if _wait_for_http_ready(app_url, READY_TIMEOUT_SECONDS):
        _write_log(root, f"NovelForge became ready on port {selected_port}; opening browser", append=True)
        webbrowser.open(app_url)
        return 0

    if process.poll() is not None:
        _remove_server_state(root, expected_pid=process.pid)
        return _fail(root, f"NovelForge exited early with code {process.returncode}.")

    _cleanup_process(root, process)
    return _fail(root, f"NovelForge did not become ready on port {selected_port} within {READY_TIMEOUT_SECONDS} seconds.")


if __name__ == "__main__":
    raise SystemExit(main())
