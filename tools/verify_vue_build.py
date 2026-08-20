"""Check the Vue build contract without opening a browser."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "frontend"
    package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    assert (frontend / "package-lock.json").exists(), "缺少 package-lock.json"
    assert package["scripts"]["build"], "缺少 Vue build script"
    assert (frontend / "src" / "api" / "generated.ts").exists(), "缺少生成的 API 类型"
    index = frontend / "dist" / "index.html"
    assert index.exists(), "缺少 frontend/dist/index.html；请先执行 npm run build"
    html = index.read_text(encoding="utf-8")
    assert 'id="app"' in html, "dist marker 缺失"
    assets = list((frontend / "dist" / "assets").glob("*"))
    assert assets, "dist 没有 hashed assets"
    assert any("PlannedAppLayout" in item.name for item in assets), "缺少规划 Layout 构建产物"
    assert any("ConversationalAppLayout" in item.name for item in assets), "缺少对话 Layout 构建产物"
    assert (frontend / "src" / "views" / "SettingsView.vue").exists(), "缺少能力设置页面"
    assert (frontend / "src" / "views" / "planned" / "PlannedChaptersView.vue").exists(), "缺少章节编辑工作区"
    print(f"Vue build verification: ok ({len(assets)} assets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
