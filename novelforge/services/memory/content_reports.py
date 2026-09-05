"""Implementation slice for the memory facade: analysis, evaluation and pipeline reports."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

def save_analysis_report(project_name: str, analysis_type: str, chapter_no: int, content: str, story_id: str = "default"):
    analysis_type = _memory_api.normalize_storage_component(analysis_type, "Analysis type")
    path = _memory_api._story_path_from_project_path(project_name, story_id, "analysis")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="analysis_markdown",
        logical_key=f"{analysis_type}_chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"{analysis_type} Chapter {chapter_no:03d} Analysis",
        mime_type="text/markdown",
        metadata={"analysis_type": analysis_type, "chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_analysis_report(project_name: str, analysis_type: str, chapter_no: int, story_id: str = "default") -> str:
    analysis_type = _memory_api.normalize_storage_component(analysis_type, "Analysis type")
    file = _memory_api._story_path_from_project_path(project_name, story_id, "analysis") / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def source_package_report_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "analysis"
    path.mkdir(exist_ok=True)
    return path / "source_package.md"


def save_source_package_report(project_name: str, content: str):
    file = source_package_report_path(project_name)
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="source_package_report",
        logical_key="source_package",
        title="Source Package Report",
        mime_type="text/markdown",
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_source_package_report(project_name: str) -> str:
    file = source_package_report_path(project_name)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def evaluation_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "evaluation")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_evaluation_report(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="evaluation_markdown",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Evaluation",
        mime_type="text/markdown",
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_evaluation_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    payload = data if isinstance(data, dict) else {}
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="evaluation_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Evaluation JSON",
        mime_type="application/json",
        payload=payload,
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_evaluation_report(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def load_evaluation_json(project_name: str, chapter_no: int, story_id: str = "default") -> dict | None:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="evaluation_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        return db_payload
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="evaluation_json",
            logical_key=f"chapter_{chapter_no:03d}",
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Evaluation JSON",
            payload=payload,
            metadata={"chapter_no": chapter_no},
        )
        return payload
    except Exception:
        return None


def runs_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pipeline_run(project_name: str, run_id: str, content: str, story_id: str = "default"):
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    try:
        payload = _memory_api.json.loads(content)
    except Exception:
        payload = None
    artifact_asset_id = _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="workflow_run_snapshot",
        logical_key=str(run_id),
        story_id=story_id,
        title=f"Workflow Run {run_id}",
        mime_type="application/json",
        payload=payload if isinstance(payload, dict) else {"raw": content},
        metadata={"run_id": str(run_id)},
    )
    if isinstance(payload, dict):
        if not artifact_asset_id:
            asset_id_source = f"{story_id or 'project'}:workflow_run_snapshot:{run_id}"
            artifact_asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
        _memory_api._sync_workflow_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_workflow_run_snapshot(
                conn,
                run_id=str(run_id),
                payload=payload,
                story_id=story_id,
                artifact_asset_id=artifact_asset_id,
            ),
        )


def load_pipeline_run(project_name: str, run_id: str, story_id: str = "default") -> str:
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    db_payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_workflow_run_snapshot(conn, run_id, story_id),
        "workflow run snapshot",
    )
    if db_payload is not None:
        if not db_payload:
            return ""
        return _memory_api.json.dumps(db_payload, ensure_ascii=False, indent=2)
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def _list_pipeline_runs_from_files(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[str]:
    path = runs_path(project_name, story_id)
    files = sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if chapter_no is None:
        return [file.stem for file in files]
    chapter_prefix = f"chapter_{chapter_no:03d}_"
    return [file.stem for file in files if file.stem.startswith(chapter_prefix)]


def list_pipeline_runs(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[str]:
    db_run_ids = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.list_workflow_run_ids(conn, story_id=story_id, chapter_no=chapter_no),
        "workflow run list",
    )
    if db_run_ids is not None:
        return db_run_ids
    run_ids = _list_pipeline_runs_from_files(project_name, chapter_no=chapter_no, story_id=story_id)
    if db_run_ids == [] and run_ids:
        for run_id in run_ids:
            raw = (runs_path(project_name, story_id) / f"{run_id}.json").read_text(encoding="utf-8")
            try:
                payload = _memory_api.json.loads(raw)
            except Exception:
                payload = None
            if not isinstance(payload, dict):
                continue
            asset_id_source = f"{story_id or 'project'}:workflow_run_snapshot:{run_id}"
            artifact_asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
            _memory_api._sync_workflow_to_db_best_effort(
                project_name,
                lambda conn, payload=payload, run_id=run_id, artifact_asset_id=artifact_asset_id: _memory_api.sync_workflow_run_snapshot(
                    conn,
                    run_id=str(run_id),
                    payload=payload,
                    story_id=story_id,
                    artifact_asset_id=artifact_asset_id,
                ),
            )
    return run_ids


def list_pipeline_run_summaries(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[dict]:
    db_runs = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.list_workflow_run_summaries(conn, story_id=story_id, chapter_no=chapter_no),
        "workflow run summary list",
    )
    if db_runs is not None:
        return db_runs
    summaries: list[dict] = []
    for run_id in _list_pipeline_runs_from_files(project_name, chapter_no=chapter_no, story_id=story_id):
        file = runs_path(project_name, story_id) / f"{run_id}.json"
        payload: dict = {}
        try:
            raw = file.read_text(encoding="utf-8")
            parsed = _memory_api.json.loads(raw)
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}
        try:
            payload_chapter_no = int(payload.get("chapter_no"))
        except (TypeError, ValueError):
            match = _memory_api.re.search(r"chapter_(\d+)_", run_id)
            payload_chapter_no = int(match.group(1)) if match else None
        summaries.append({
            "run_id": run_id,
            "story_id": story_id,
            "workflow_type": payload.get("workflow_type", "chapter_pipeline"),
            "status": payload.get("status") or ("completed" if payload.get("success") is True else "unknown"),
            "chapter_no": payload_chapter_no,
            "updated_at": _memory_api.datetime.fromtimestamp(file.stat().st_mtime).isoformat(timespec="seconds") if file.exists() else "",
            "started_at": payload.get("started_at", ""),
            "finished_at": payload.get("finished_at", ""),
            "payload": payload,
        })
    return summaries


def delete_pipeline_run_record(project_name: str, run_id: str, story_id: str = "default") -> bool:
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    if _memory_api._project_db_marked_unavailable(project_name):
        return False
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            deleted = _memory_api.delete_workflow_run_snapshot(conn, run_id=run_id, story_id=story_id)
            conn.commit()
            return bool(deleted)
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(project_name)
        _memory_api.logging.getLogger("novelforge.storage").warning(
            "Failed to delete workflow run from project database for %s/%s: %s",
            project_name,
            run_id,
            exc,
        )
        _memory_api._raise_if_db_only(f"Failed to delete workflow run from project database for {project_name}/{run_id}.", exc)
        return False
