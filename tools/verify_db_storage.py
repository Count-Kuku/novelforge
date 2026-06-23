from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script_name: str) -> dict:
    command = [sys.executable, str(ROOT / "tools" / script_name)]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        payload = {
            "ok": False,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    return {
        "script": script_name,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0 and bool(payload.get("ok")),
        "result": payload,
        "stderr": completed.stderr,
    }


def main() -> int:
    checks = [
        _run("verify_global_db_first_reads.py"),
        _run("verify_db_first_reads.py"),
        _run("verify_db_delete_semantics.py"),
        _run("verify_db_no_json_mirrors.py"),
    ]
    result = {
        "ok": all(item.get("ok") for item in checks),
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
