from __future__ import annotations

import math
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.core.schemas import RetrievalChunk, RetrievalHit, RetrievalIndexManifest, RetrievalVectorStore
from novelforge.domain.ingestion_task_estimates import estimate_ingestion_task
from novelforge.services import retrieval_eval
from novelforge.services.memory.references import normalize_retrieval_eval_case
from novelforge.services.retrieval import index as retrieval_index
from ui.retrieval_eval_panel import _eval_result_rows


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _chunk(chunk_id: str, content: str, source_type: str = "external_source") -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id,
        document_id=f"doc:{chunk_id}",
        project_name="retrieval_hardening",
        source_type=source_type,
        scope="canon",
        title=f"Title {chunk_id}",
        content=content,
    )


def _content_hash(chunk: RetrievalChunk) -> str:
    return sha256(f"{chunk.title}\n{chunk.content}".encode("utf-8")).hexdigest()


def _hit(chunk: RetrievalChunk) -> RetrievalHit:
    return RetrievalHit(chunk=chunk, score=1.0, lexical_score=1.0)


def verify_dimension_change_forces_uniform_rebuild() -> None:
    unchanged = _chunk("chunk-1", "unchanged")
    changed = _chunk("chunk-2", "changed")
    previous = RetrievalVectorStore(
        project_name="retrieval_hardening",
        built_at="2026-08-05T00:00:00",
        embedding_model="same-name-model",
        vectors={"chunk-1": [0.1, 0.2], "chunk-2": [0.2, 0.3]},
        content_hashes={"chunk-1": _content_hash(unchanged), "chunk-2": "old-hash"},
    )
    manifest = RetrievalIndexManifest(
        project_name="retrieval_hardening",
        built_at="2026-08-06T00:00:00",
        document_count=2,
        chunk_count=2,
        chunks=[unchanged, changed],
    )
    with (
        patch.object(retrieval_index, "load_vector_store", return_value=previous),
        patch.object(retrieval_index._retrieval_api, "_active_embedding_model_name", return_value="same-name-model"),
        patch.object(
            retrieval_index._retrieval_api,
            "get_embedding",
            side_effect=[[0.9, 0.8, 0.7], [0.6, 0.5, 0.4]],
        ) as get_embedding,
        patch.object(retrieval_index._retrieval_api, "save_retrieval_vectors") as save_vectors,
    ):
        store = retrieval_index.build_vector_store("retrieval_hardening", manifest)

    check({len(vector) for vector in store.vectors.values()} == {3}, "dimension change leaves a uniform vector store")
    check(store.build_mode == "full", "dimension change is recorded as full build")
    check(store.reused_vector_count == 0, "dimension change does not report stale reuse")
    check(store.generated_vector_count == 2, "dimension change reports every vector as generated")
    check(get_embedding.call_count == 2, "dimension change regenerates the previously reused chunk")
    check(save_vectors.call_count == 1, "uniform vector store is persisted once")


def verify_invalid_vectors_are_rejected_and_reported() -> None:
    chunk = _chunk("chunk-invalid", "content")
    manifest = RetrievalIndexManifest(
        project_name="retrieval_hardening",
        built_at="2026-08-06T00:00:00",
        document_count=1,
        chunk_count=1,
        chunks=[chunk],
    )
    with (
        patch.object(retrieval_index, "load_vector_store", return_value=None),
        patch.object(retrieval_index._retrieval_api, "_active_embedding_model_name", return_value="model"),
        patch.object(retrieval_index._retrieval_api, "get_embedding", return_value=[0.0, 0.0]),
        patch.object(retrieval_index._retrieval_api, "save_retrieval_vectors") as save_vectors,
    ):
        try:
            retrieval_index.build_vector_store("retrieval_hardening", manifest)
        except RuntimeError as exc:
            error = str(exc)
        else:
            error = ""
    check("零向量" in error, "zero embedding is rejected with an actionable error")
    check(save_vectors.call_count == 0, "invalid vector store is not persisted")

    chunks = [_chunk(f"chunk-{index}", f"content-{index}") for index in range(1, 5)]
    health_manifest = RetrievalIndexManifest(
        project_name="retrieval_hardening",
        built_at="2026-08-06T00:00:00",
        document_count=4,
        chunk_count=4,
        chunks=chunks,
    )
    store = RetrievalVectorStore(
        project_name="retrieval_hardening",
        built_at="2026-08-06T00:00:00",
        embedding_model="model",
        vectors={
            "chunk-1": [0.1, 0.2],
            "chunk-2": [0.1, 0.2, 0.3],
            "chunk-3": [0.0, 0.0],
            "chunk-4": [0.4, 0.5],
        },
        content_hashes={
            "chunk-1": _content_hash(chunks[0]),
            "chunk-2": _content_hash(chunks[1]),
            "chunk-3": _content_hash(chunks[2]),
            "chunk-4": "stale-hash",
        },
    )
    summary = retrieval_index._vector_health_summary(health_manifest, store)
    check(summary["vector_dimension_counts"] == {2: 2, 3: 1}, "health reports every valid vector dimension")
    check(summary["invalid_vector_count"] == 1, "health reports invalid vectors")
    check(summary["inconsistent_vector_dimension_count"] == 1, "health reports minority dimensions")
    check(summary["stale_content_vector_count"] == 1, "health reports stale content hashes")
    check(summary["usable_vector_count"] == 1, "health counts only semantically usable vectors")
    check(summary["missing_vector_count"] == 3, "unusable vectors contribute to missing semantic coverage")


def verify_eval_normalization_and_metric_semantics() -> None:
    parsed = retrieval_eval.parse_multiline_or_comma_values("Alpha, alpha\nBeta，ALPHA")
    check(parsed == ["Alpha", "Beta"], "free-text expectations are stably deduplicated")

    normalized = normalize_retrieval_eval_case({
        "query": "query",
        "expected_terms": ["Target", "target"],
        "expected_chunk_ids": ["chunk-a", "chunk-a"],
        "expected_source_types": ["external_source", "external_source"],
        "min_expected_matches": 20,
    })
    check(normalized["expected_terms"] == ["Target"], "persisted terms deduplicate case-insensitively")
    check(normalized["expected_chunk_ids"] == ["chunk-a"], "persisted chunk IDs are deduplicated")
    check(normalized["expected_source_types"] == ["external_source"], "persisted source types are deduplicated")
    check(normalized["min_expected_matches"] == 3, "minimum matches cannot exceed unique expectations")

    term_hit = _hit(_chunk("other-chunk", "contains target answer"))
    metrics = retrieval_eval._ranking_metrics(
        [term_hit],
        expected_terms=["target"],
        expected_chunk_ids=["missing-chunk"],
        expected_source_types=[],
    )
    check(metrics["recall_at_k"] == 0.5, "mixed expectations retain coverage recall")
    check(metrics["mrr"] == 1.0, "soft relevance contributes to MRR when exact chunks are also configured")
    check(metrics["ndcg_at_k"] == 1.0, "soft relevance contributes to nDCG when exact chunks are also configured")


def verify_eval_errors_do_not_pollute_quality_means() -> None:
    hit = _hit(_chunk("chunk-hit", "target answer"))

    def fake_retrieve(_project_name: str, query: str, **_kwargs):
        if query == "error":
            raise RuntimeError("embedding provider unavailable")
        return [hit]

    with (
        patch.object(retrieval_eval, "retrieve_context", side_effect=fake_retrieve),
        patch.object(retrieval_eval, "append_retrieval_eval_run", side_effect=lambda _project, payload: payload),
    ):
        run = retrieval_eval.run_retrieval_eval_cases("retrieval_hardening", [
            {"case_id": "success", "name": "success", "query": "success", "expected_terms": ["target"]},
            {"case_id": "error", "name": "error", "query": "error", "expected_terms": ["target"]},
        ])

    check(run["case_count"] == 2, "aggregate retains every active case")
    check(run["error_count"] == 1, "aggregate separates execution errors")
    check(run["metric_case_count"] == 1, "quality denominator includes only evaluated rankings")
    check(run["mean_recall_at_k"] == 1.0, "execution errors do not lower mean recall")
    check(run["mean_mrr"] == 1.0, "execution errors do not lower mean MRR")
    check(run["mean_ndcg_at_k"] == 1.0, "execution errors do not lower mean nDCG")
    check(run["zero_recall_count"] == 0, "execution errors are not labeled zero recall")
    check(run["failed_count"] == 1, "execution errors still fail the case run")


def verify_legacy_run_and_nonfinite_rates() -> None:
    rows = _eval_result_rows({
        "results": [{
            "name": "legacy",
            "passed": True,
            "matched_count": 1,
            "expectation_count": 1,
            "top_hit": {},
        }],
    })
    check(rows[0]["Recall@K"] == "未记录", "legacy rows do not invent zero recall")
    check(rows[0]["MRR"] == "未记录", "legacy rows do not invent zero MRR")
    check(rows[0]["nDCG@K"] == "未记录", "legacy rows do not invent zero nDCG")

    estimate = estimate_ingestion_task(
        {"segments": [{"content": "资料内容" * 100}]},
        [0],
        enabled_categories=["characters"],
        extraction_mode="general",
        import_to_index=True,
        consolidate_after_extract=False,
        model_profile={
            "input_price_per_million": float("nan"),
            "output_price_per_million": float("inf"),
            "embedding_price_per_million": float("-inf"),
        },
    )
    check(not estimate["pricing_configured"], "non-finite rates are treated as unconfigured")
    check(math.isfinite(estimate["estimated_cost_usd"]), "non-finite rates cannot produce non-finite cost")
    check(estimate["estimated_cost_usd"] == 0.0, "invalid rates do not invent a cost")
    check(len(estimate["missing_price_components"]) == 3, "every invalid active rate is reported missing")


def verify_documented_configuration_precedence() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    check("LLM_EMBEDDING_MODEL" in env_example, "environment template includes embedding model")
    check("global.db" in readme and "权威来源" in readme, "Chinese README explains DB-first model profile precedence")
    check("global.db" in readme_en and "authoritative" in readme_en, "English README explains DB-first model profile precedence")


def main() -> None:
    verify_dimension_change_forces_uniform_rebuild()
    verify_invalid_vectors_are_rejected_and_reported()
    verify_eval_normalization_and_metric_semantics()
    verify_eval_errors_do_not_pollute_quality_means()
    verify_legacy_run_and_nonfinite_rates()
    verify_documented_configuration_precedence()
    print(f"Retrieval hardening verification passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
