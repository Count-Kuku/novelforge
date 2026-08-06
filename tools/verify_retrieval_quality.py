from __future__ import annotations

import math
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.core.schemas import (
    RetrievalChunk,
    RetrievalHit,
    RetrievalIndexManifest,
    RetrievalVectorStore,
)
from novelforge.services import retrieval_eval
from novelforge.services.retrieval import index as retrieval_index


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _chunk(chunk_id: str, content: str, source_type: str = "external_source") -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id,
        document_id=f"doc:{chunk_id}",
        project_name="quality_verify",
        source_type=source_type,
        scope="canon",
        title=f"Title {chunk_id}",
        content=content,
    )


def _hit(chunk: RetrievalChunk, score: float) -> RetrievalHit:
    return RetrievalHit(chunk=chunk, score=score, lexical_score=score)


def verify_vector_store_backward_compatibility() -> None:
    store = RetrievalVectorStore.model_validate({
        "project_name": "quality_verify",
        "built_at": "2026-08-05T00:00:00",
        "embedding_model": "embedding-a",
        "vectors": {"chunk-1": [0.1, 0.2]},
        "content_hashes": {},
    })
    check(store.build_mode == "full", "old vector store defaults to full build mode")
    check(store.reused_vector_count == 0, "old vector store defaults reused count")
    check(store.generated_vector_count == 0, "old vector store defaults generated count")
    check(store.removed_vector_count == 0, "old vector store defaults removed count")


def verify_incremental_vector_reuse() -> None:
    unchanged = _chunk("chunk-1", "unchanged content")
    changed = _chunk("chunk-2", "new content")
    unchanged_hash = sha256(f"{unchanged.title}\n{unchanged.content}".encode("utf-8")).hexdigest()
    previous = RetrievalVectorStore(
        project_name="quality_verify",
        built_at="2026-08-05T00:00:00",
        embedding_model="embedding-a",
        vectors={
            "chunk-1": [0.1, 0.2],
            "chunk-2": [0.2, 0.3],
            "stale-chunk": [0.3, 0.4],
        },
        content_hashes={
            "chunk-1": unchanged_hash,
            "chunk-2": "old-content-hash",
            "stale-chunk": "stale-content-hash",
        },
    )
    manifest = RetrievalIndexManifest(
        project_name="quality_verify",
        built_at="2026-08-05T00:01:00",
        document_count=2,
        chunk_count=2,
        chunks=[unchanged, changed],
    )

    with (
        patch.object(retrieval_index, "load_vector_store", return_value=previous),
        patch.object(retrieval_index._retrieval_api, "_active_embedding_model_name", return_value="embedding-a"),
        patch.object(retrieval_index._retrieval_api, "get_embedding", return_value=[0.9, 0.8]) as get_embedding,
        patch.object(retrieval_index._retrieval_api, "save_retrieval_vectors") as save_vectors,
    ):
        store = retrieval_index.build_vector_store("quality_verify", manifest)

    check(get_embedding.call_count == 1, "only changed chunk is embedded")
    check(store.vectors["chunk-1"] == [0.1, 0.2], "unchanged vector is reused")
    check(store.vectors["chunk-2"] == [0.9, 0.8], "changed vector is regenerated")
    check("stale-chunk" not in store.vectors, "stale vector is removed")
    check(store.build_mode == "incremental", "same model uses incremental mode")
    check(store.reused_vector_count == 1, "incremental reused count")
    check(store.generated_vector_count == 1, "incremental generated count")
    check(store.removed_vector_count == 1, "incremental removed count")
    check(save_vectors.call_count == 1, "incremental vector store is persisted once")

    with (
        patch.object(retrieval_index, "load_vector_store", return_value=store),
        patch.object(retrieval_index._retrieval_api, "_active_embedding_model_name", return_value="embedding-a"),
        patch.object(retrieval_index._retrieval_api, "get_embedding") as unchanged_embedding,
        patch.object(retrieval_index._retrieval_api, "save_retrieval_vectors"),
    ):
        unchanged_store = retrieval_index.build_vector_store("quality_verify", manifest)
    check(unchanged_embedding.call_count == 0, "unchanged rebuild makes no embedding calls")
    check(unchanged_store.reused_vector_count == 2, "unchanged rebuild reuses every vector")
    check(unchanged_store.generated_vector_count == 0, "unchanged rebuild generates no vectors")


def verify_embedding_model_change_forces_full_build() -> None:
    chunk = _chunk("chunk-1", "unchanged content")
    previous = RetrievalVectorStore(
        project_name="quality_verify",
        built_at="2026-08-05T00:00:00",
        embedding_model="embedding-a",
        vectors={"chunk-1": [0.1, 0.2]},
        content_hashes={
            "chunk-1": sha256(f"{chunk.title}\n{chunk.content}".encode("utf-8")).hexdigest(),
        },
    )
    manifest = RetrievalIndexManifest(
        project_name="quality_verify",
        built_at="2026-08-05T00:01:00",
        chunk_count=1,
        chunks=[chunk],
    )
    with (
        patch.object(retrieval_index, "load_vector_store", return_value=previous),
        patch.object(retrieval_index._retrieval_api, "_active_embedding_model_name", return_value="embedding-b"),
        patch.object(retrieval_index._retrieval_api, "get_embedding", return_value=[0.7, 0.6]) as get_embedding,
        patch.object(retrieval_index._retrieval_api, "save_retrieval_vectors"),
    ):
        store = retrieval_index.build_vector_store("quality_verify", manifest)

    check(get_embedding.call_count == 1, "model change regenerates unchanged chunk")
    check(store.build_mode == "full", "model change uses full build mode")
    check(store.reused_vector_count == 0, "model change does not reuse vectors")
    check(store.generated_vector_count == 1, "model change generated count")


def verify_ranking_metrics() -> None:
    first = _hit(_chunk("chunk-1", "unrelated"), 2.0)
    second = _hit(_chunk("chunk-2", "target answer"), 1.0)
    metrics = retrieval_eval._ranking_metrics(
        [first, second],
        expected_terms=[],
        expected_chunk_ids=["chunk-2"],
        expected_source_types=[],
    )
    check(metrics["recall_at_k"] == 1.0, "exact chunk recall at k")
    check(metrics["first_relevant_rank"] == 2, "first relevant rank")
    check(metrics["mrr"] == 0.5, "reciprocal rank at position two")
    check(math.isclose(metrics["ndcg_at_k"], 1 / math.log2(3)), "ndcg at position two")
    check(metrics["relevant_hit_count"] == 1, "relevant hit count")

    soft_metrics = retrieval_eval._ranking_metrics(
        [second],
        expected_terms=["target"],
        expected_chunk_ids=[],
        expected_source_types=[],
    )
    check(soft_metrics["recall_at_k"] == 1.0, "legacy term expectation recall")
    check(soft_metrics["mrr"] == 1.0, "legacy term expectation mrr")
    check(soft_metrics["ndcg_at_k"] == 1.0, "legacy term expectation ndcg")

    multi_soft_metrics = retrieval_eval._ranking_metrics(
        [
            _hit(_chunk("chunk-soft", "target answer and canon fact"), 2.0),
            _hit(_chunk("chunk-soft-other", "unrelated"), 1.0),
        ],
        expected_terms=["target", "canon fact"],
        expected_chunk_ids=[],
        expected_source_types=[],
    )
    check(multi_soft_metrics["recall_at_k"] == 1.0, "multiple soft expectations share one hit")
    check(multi_soft_metrics["ndcg_at_k"] == 1.0, "soft ndcg does not invent extra relevant documents")

    empty_metrics = retrieval_eval._ranking_metrics(
        [first],
        expected_terms=["missing"],
        expected_chunk_ids=[],
        expected_source_types=[],
    )
    check(empty_metrics["recall_at_k"] == 0.0, "zero recall")
    check(empty_metrics["first_relevant_rank"] == 0, "zero recall rank")
    check(empty_metrics["mrr"] == 0.0, "zero recall mrr")
    check(empty_metrics["ndcg_at_k"] == 0.0, "zero recall ndcg")


def verify_eval_run_aggregation() -> None:
    relevant_hit = _hit(_chunk("chunk-2", "target answer"), 1.0)
    irrelevant_hit = _hit(_chunk("chunk-1", "unrelated"), 1.0)

    def fake_retrieve_context(_project_name: str, query: str, **_kwargs):
        return [relevant_hit] if query == "hit" else [irrelevant_hit]

    with (
        patch.object(retrieval_eval, "retrieve_context", side_effect=fake_retrieve_context),
        patch.object(retrieval_eval, "append_retrieval_eval_run", side_effect=lambda _project, payload: payload),
    ):
        run = retrieval_eval.run_retrieval_eval_cases("quality_verify", [
            {
                "case_id": "hit",
                "name": "hit",
                "query": "hit",
                "expected_chunk_ids": ["chunk-2"],
            },
            {
                "case_id": "miss",
                "name": "miss",
                "query": "miss",
                "expected_chunk_ids": ["chunk-2"],
            },
        ])

    check(run["case_count"] == 2, "aggregate case count")
    check(run["passed_count"] == 1, "aggregate passed count")
    check(run["mean_recall_at_k"] == 0.5, "aggregate mean recall")
    check(run["mean_mrr"] == 0.5, "aggregate mean mrr")
    check(run["mean_ndcg_at_k"] == 0.5, "aggregate mean ndcg")
    check(run["zero_recall_count"] == 1, "aggregate zero recall count")


def main() -> None:
    verify_vector_store_backward_compatibility()
    verify_incremental_vector_reuse()
    verify_embedding_model_change_forces_full_build()
    verify_ranking_metrics()
    verify_eval_run_aggregation()
    print(f"Retrieval quality verification passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
