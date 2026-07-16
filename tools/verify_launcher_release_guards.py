from __future__ import annotations

import json
import multiprocessing
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import launcher


def _lock_worker(
    root_text: str,
    worker_id: int,
    start_event: multiprocessing.synchronize.Event,
    events: multiprocessing.queues.Queue,
) -> None:
    root = Path(root_text)
    start_event.wait(timeout=10)
    with launcher._launcher_lock(root):
        events.put(("acquired", worker_id, time.monotonic()))
        time.sleep(0.35)
        events.put(("released", worker_id, time.monotonic()))


class _ExitedProcess:
    pid = 43210
    returncode = 7

    def poll(self) -> int:
        return self.returncode


def _check_early_exit_state_cleanup(root: Path) -> None:
    process = _ExitedProcess()
    launcher._write_server_state(root, process.pid, launcher.DEFAULT_PORT)
    with (
        patch.object(launcher, "_project_root", return_value=root),
        patch.object(
            launcher,
            "_find_available_port",
            return_value=(launcher.DEFAULT_PORT, None),
        ),
        patch.object(launcher, "_resolve_python", return_value=Path(sys.executable)),
        patch.object(launcher, "_launch_streamlit", return_value=process),
        patch.object(launcher, "_wait_for_http_ready", return_value=False),
        patch.object(launcher, "_show_error", return_value=None),
    ):
        result = launcher.main()
    assert result == 1
    assert not launcher._server_state_path(root).exists(), (
        "early child exit left .novelforge-server.json behind"
    )


def _check_expected_pid_guard(root: Path) -> None:
    launcher._write_server_state(root, 9002, launcher.DEFAULT_PORT)
    launcher._remove_server_state(root, expected_pid=9001)
    state = json.loads(launcher._server_state_path(root).read_text(encoding="utf-8"))
    assert state["pid"] == 9002, "cleanup removed a newer process state"
    launcher._remove_server_state(root, expected_pid=9002)


def _check_cross_process_lock(root: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    events = context.Queue()
    workers = [
        context.Process(
            target=_lock_worker,
            args=(str(root), worker_id, start_event, events),
        )
        for worker_id in (1, 2)
    ]
    for worker in workers:
        worker.start()
    start_event.set()
    observed = [events.get(timeout=15) for _ in range(4)]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0, f"lock worker failed: exit={worker.exitcode}"

    by_worker: dict[int, dict[str, float]] = {}
    for event_name, worker_id, timestamp in observed:
        by_worker.setdefault(worker_id, {})[event_name] = timestamp
    assert set(by_worker) == {1, 2}
    first_id = min(by_worker, key=lambda item: by_worker[item]["acquired"])
    second_id = 1 if first_id == 2 else 2
    assert by_worker[second_id]["acquired"] >= by_worker[first_id]["released"] - 0.02, (
        "two launcher processes held the launch lock at the same time"
    )


def _check_stale_and_exception_lock_cleanup(root: Path) -> None:
    launcher._launch_lock_path(root).write_text(
        json.dumps({"pid": 999_999_999, "root": str(root)}),
        encoding="utf-8",
    )
    with launcher._launcher_lock(root):
        pass

    try:
        with launcher._launcher_lock(root):
            raise RuntimeError("intentional verification failure")
    except RuntimeError as exc:
        assert "intentional verification failure" in str(exc)

    started = time.monotonic()
    with launcher._launcher_lock(root):
        pass
    assert time.monotonic() - started < 2, "exception left the launch lock held"


def _run_rejected_build(runtime_root: Path) -> str:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PROJECT_ROOT / "build_release.ps1"),
        "-RuntimeRoot",
        str(runtime_root),
        "-Version",
        "guard-check",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode != 0, f"unsafe RuntimeRoot was accepted: {runtime_root}"
    return f"{completed.stdout}\n{completed.stderr}"


def _check_build_path_guards() -> None:
    equal_output = _run_rejected_build(PROJECT_ROOT)
    assert "must not equal ProjectRoot" in equal_output

    ancestor_output = _run_rejected_build(PROJECT_ROOT.parent)
    assert "ancestor of ProjectRoot" in ancestor_output

    portable_child = PROJECT_ROOT / "release" / "NovelForge-Portable" / ".runtime"
    portable_output = _run_rejected_build(portable_child)
    assert "inside PortableRoot" in portable_output

    release_ancestor_output = _run_rejected_build(PROJECT_ROOT / "release")
    assert "must not contain PortableRoot" in release_ancestor_output


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="novelforge-launcher-check-") as temp_dir:
        root = Path(temp_dir)
        _check_early_exit_state_cleanup(root)
        checks += 1
        _check_expected_pid_guard(root)
        checks += 1
        _check_cross_process_lock(root)
        checks += 1
        _check_stale_and_exception_lock_cleanup(root)
        checks += 1
    _check_build_path_guards()
    checks += 1
    print(f"Launcher/release guard verification passed: {checks} checks")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
