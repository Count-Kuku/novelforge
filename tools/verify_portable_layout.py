"""Validate the portable release layout when a release has been built.

The self-contained Windows Python runtime is intentionally supplied by the
release machine. This checker therefore validates the deterministic project
payload locally and reports a clear, non-success result when no package is
available instead of pretending to have run a clean-machine smoke test.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    portable = root / "release" / "NovelForge-Portable"
    if not portable.exists():
        print("portable layout verification: skipped (no release/NovelForge-Portable; provide self-contained runtime to build)")
        return 2
    required_files = ["NovelForge.exe", "launcher.py", "frontend/dist/index.html", "novelforge/api/app.py", "storage/schema.py", "USAGE.txt"]
    missing = [item for item in required_files if not (portable / item).exists()]
    if missing:
        print(f"portable layout verification: failed; missing {missing}")
        return 1
    dist_assets = list((portable / "frontend" / "dist" / "assets").glob("*"))
    if not dist_assets:
        print("portable layout verification: failed; no hashed frontend assets")
        return 1
    print(f"portable layout verification: ok ({len(dist_assets)} frontend assets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
