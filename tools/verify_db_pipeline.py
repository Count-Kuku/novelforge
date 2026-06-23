from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import (
    append_auto_review_run,
    append_retrieval_eval_run,
    append_retrieval_feedback,
    create_long_reference_batch,
    create_project,
    inspect_project_database,
    save_creative_profile,
    save_character_entities,
    save_entity_aliases,
    save_evaluation_json,
    save_extraction_plan_templates,
    save_knowledge_category,
    save_pending_knowledge_items,
    save_pipeline_run,
    save_project_prompt_options,
    save_project_rules,
    save_review_json,
    save_retrieval_manifest,
    save_retrieval_vectors,
    save_setting_entities,
    save_story_chapter_summaries,
    save_story_prompt_options,
    save_story_rules,
    upsert_retrieval_eval_case,
)


def _project_name_from_args() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1].strip()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"_db_verify_{stamp}"


def main() -> int:
    project_name = _project_name_from_args()
    create_project(project_name)

    save_creative_profile(project_name, {
        "is_configured": True,
        "story_mode": "长篇连载",
        "genre": "验证类型",
        "tone": "清晰",
    })
    save_project_rules(project_name, {
        "write": ["验证项目写作规则"],
        "review": [],
    })
    save_story_rules(project_name, "default", {
        "review": ["验证故事审阅规则"],
    })
    save_project_prompt_options(project_name, [
        {
            "id": "prompt_project_verify_001",
            "name": "验证项目提示选项",
            "capability": "write",
            "category": "custom",
            "slot": "custom",
            "content": "项目提示选项验证。",
            "enabled": True,
        }
    ])
    save_story_prompt_options(project_name, "default", [
        {
            "id": "prompt_story_verify_001",
            "name": "验证故事提示选项",
            "capability": "review",
            "category": "custom",
            "slot": "custom",
            "content": "故事提示选项验证。",
            "enabled": True,
        }
    ])
    save_story_chapter_summaries(project_name, "default", [
        {"chapter_no": 1, "summary": "验证章节摘要。"}
    ])
    save_character_entities(project_name, [
        {"name": "验证角色A", "summary": "验证角色卡。"}
    ])
    save_setting_entities(project_name, [
        {"name": "验证地点", "summary": "验证设定卡。"}
    ])
    save_extraction_plan_templates(project_name, [
        {"name": "验证抽取模板", "steps": ["extract", "review"]}
    ])

    save_knowledge_category(project_name, "characters", [
        {
            "id": "char_verify_001",
            "name": "验证角色A",
            "summary": "数据库验证用角色。",
            "confidence": 0.9,
            "worldline_id": "main",
        }
    ])
    save_knowledge_category(project_name, "relationships", [
        {
            "id": "rel_verify_001",
            "name": "验证角色A与验证角色B",
            "source": "验证角色A",
            "target": "验证角色B",
            "relation": "ally_of",
            "confidence": 0.8,
        }
    ])
    save_pending_knowledge_items(project_name, [
        {
            "pending_id": "pending_verify_001",
            "category": "items",
            "name": "验证道具",
            "status": "pending",
        }
    ])
    save_entity_aliases(project_name, [
        {
            "id": "alias_verify_001",
            "canonical_name": "验证角色A",
            "aliases": ["A", "角色A"],
            "category": "characters",
        }
    ])

    create_long_reference_batch(
        project_name,
        title="验证长篇资料",
        scope="reference",
        authority="curated",
        source_type="canon",
        content_fingerprint="verify_fingerprint",
        segments=[
            {"title": "验证片段一", "content": "验证正文一", "import_status": "imported", "extract_status": "queued"},
            {"title": "验证片段二", "content": "验证正文二"},
        ],
    )

    manifest = {
        "project_name": project_name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "documents": [
            {
                "doc_id": "verify_doc_001",
                "project_name": project_name,
                "source_type": "outline",
                "scope": "project",
                "title": "验证文档",
                "content": "验证检索文档。",
                "metadata": {"worldline_id": "main"},
            }
        ],
        "chunks": [
            {
                "chunk_id": "verify_doc_001#chunk001",
                "document_id": "verify_doc_001",
                "project_name": project_name,
                "source_type": "outline",
                "scope": "project",
                "title": "验证文档",
                "content": "验证检索片段。",
                "metadata": {"chunk_index": 1},
            }
        ],
    }
    save_retrieval_manifest(project_name, json.dumps(manifest, ensure_ascii=False, indent=2))
    save_retrieval_vectors(project_name, json.dumps({
        "project_name": project_name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "embedding_model": "verify-embedding",
        "vectors": {"verify_doc_001#chunk001": [0.1, 0.2, 0.3]},
    }, ensure_ascii=False, indent=2))

    append_auto_review_run(project_name, {"run_id": "auto_verify_001", "status": "active"})
    upsert_retrieval_eval_case(project_name, {
        "case_id": "case_verify_001",
        "query": "验证角色",
        "expected_terms": ["验证角色"],
    })
    append_retrieval_eval_run(project_name, {
        "run_id": "eval_run_verify_001",
        "case_id": "case_verify_001",
        "status": "passed",
    })
    append_retrieval_feedback(project_name, {
        "feedback_id": "feedback_verify_001",
        "chunk_id": "verify_doc_001#chunk001",
        "rating": "helpful",
        "note": "验证反馈",
    })
    save_review_json(project_name, 1, {"score": 8, "notes": ["verify"]})
    save_evaluation_json(project_name, 1, {"overall_score": 8, "notes": ["verify"]})

    save_pipeline_run(project_name, "workflow_verify_001", json.dumps({
        "run_id": "workflow_verify_001",
        "project_name": project_name,
        "chapter_no": 1,
        "success": True,
        "steps": {
            "write_chapter": {
                "step_name": "write_chapter",
                "success": True,
                "status": "completed",
                "data": {"chapter": "验证章节"},
            }
        },
    }, ensure_ascii=False, indent=2))

    health = inspect_project_database(project_name)
    print(json.dumps({
        "project_name": project_name,
        "health": health,
    }, ensure_ascii=False, indent=2))
    return 0 if health.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
