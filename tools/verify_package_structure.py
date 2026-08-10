from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify() -> None:
    root_python_files = sorted(path.name for path in ROOT.glob("*.py"))
    check(root_python_files == ["app.py", "launcher.py"], "根目录只保留两个运行入口")

    expected_packages = [
        ROOT / "novelforge" / "core",
        ROOT / "novelforge" / "domain",
        ROOT / "novelforge" / "services",
        ROOT / "novelforge" / "workflows",
    ]
    check(all((path / "__init__.py").is_file() for path in expected_packages), "分层业务包完整")

    implementation_slices = [
        *sorted((ROOT / "novelforge" / "services" / "memory").glob("*.py")),
        *sorted((ROOT / "novelforge" / "services" / "retrieval").glob("*.py")),
        *sorted((ROOT / "novelforge" / "services" / "web_research").glob("*.py")),
        *sorted((ROOT / "novelforge" / "workflows" / "skills").glob("*.py")),
        *sorted((ROOT / "novelforge" / "workflows").glob("web_research*.py")),
        ROOT / "novelforge" / "domain" / "web_research_tasks.py",
        ROOT / "storage" / "repositories" / "durable_tasks.py",
        ROOT / "ui" / "web_research.py",
        ROOT / "ui" / "web_research_tasks.py",
    ]
    oversized = {
        str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
        for path in implementation_slices
        if len(path.read_text(encoding="utf-8").splitlines()) > 2200
    }
    check(not oversized, f"大模块实现切片不超过 2200 行：{oversized}")

    release_script = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
    check('"novelforge"' in release_script, "发布脚本复制 novelforge 业务包")
    check('"storage_architecture.md"' in release_script, "发布脚本包含存储架构文档")
    check("does not match VERSION" in release_script, "发布版本与 VERSION 文件保持一致")
    check("Get-FileHash" in release_script and '"$ZipPath.sha256"' in release_script, "发布包生成 SHA-256 校验文件")
    check(
        release_script.index('Copy-Item -LiteralPath $ResolvedRuntimeRoot')
        < release_script.index('Directory -Filter "__pycache__"'),
        "发布脚本会清理运行时缓存",
    )
    check(
        all(f'"{legacy_name}.py"' not in release_script for legacy_name in ("memory", "retrieval", "skills")),
        "发布脚本不再依赖旧根目录业务文件",
    )

    legacy_modules = {
        "memory",
        "retrieval",
        "skills",
        "schemas",
        "prompts",
        "llm",
        "project_manager",
        "source_workflows",
        "context_assembly",
        "setting_knowledge",
        "prompt_options",
    }
    stale_imports: list[str] = []
    source_roots = [ROOT / "app.py", ROOT / "novelforge", ROOT / "storage", ROOT / "ui", ROOT / "tools"]
    source_files: list[Path] = []
    for source_root in source_roots:
        source_files.extend([source_root] if source_root.is_file() else source_root.rglob("*.py"))
    for source_file in source_files:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = [node.module.split(".", 1)[0]]
            for module_name in imported:
                if module_name in legacy_modules:
                    stale_imports.append(f"{source_file.relative_to(ROOT)}:{node.lineno}:{module_name}")
    check(not stale_imports, f"代码不再使用旧根目录模块导入：{stale_imports}")

    from novelforge.services import memory, retrieval, web_research
    from novelforge.workflows import skills
    from novelforge.workflows import web_research_tasks

    check(callable(memory.load_memory), "memory 门面公开持久化 API")
    check(callable(retrieval.retrieve_context), "retrieval 门面公开检索 API")
    check(callable(web_research.search_web), "web_research 门面公开网络检索 API")
    check(callable(web_research.fetch_web_page), "web_research 门面公开安全抓取 API")
    check(callable(memory.list_web_research_tasks), "memory 门面公开网络研究任务 API")
    check(callable(web_research_tasks.create_web_research_task), "网络研究工作流公开持久任务 API")
    check(callable(skills.write_chapter), "skills 门面公开生成 API")


def main() -> int:
    try:
        verify()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
