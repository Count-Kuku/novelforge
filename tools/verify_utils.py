from __future__ import annotations

import gc
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4


def make_workspace(prefix: str) -> Path:
    base = Path(tempfile.gettempdir())
    for _ in range(100):
        candidate = base / f"{prefix}{uuid4().hex}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Unable to create verification workspace with prefix: {prefix}")


@contextmanager
def isolated_workspace(prefix: str) -> Iterator[Path]:
    workspace = make_workspace(prefix)
    previous_cwd = Path.cwd()
    try:
        os.chdir(workspace)
        yield workspace
    finally:
        os.chdir(previous_cwd)
        retry_rmtree(workspace)


def retry_unlink(root: Path, file: Path, *, attempts: int = 5, delay_seconds: float = 0.1) -> bool:
    resolved_root = root.resolve()
    resolved_file = file.resolve()
    if resolved_root != resolved_file and resolved_root not in resolved_file.parents:
        raise RuntimeError(f"Refusing to delete outside verification workspace: {resolved_file}")
    if not resolved_file.exists() or not resolved_file.is_file():
        return False

    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            resolved_file.unlink()
            return True
        except OSError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay_seconds)
    if last_error:
        raise last_error
    return False


def retry_rmtree(path: Path, *, attempts: int = 10, delay_seconds: float = 0.25) -> None:
    if not path.exists():
        return
    for attempt in range(attempts):
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
