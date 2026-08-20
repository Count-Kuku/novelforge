"""Benchmark the 10k-item knowledge search and pagination contract locally."""

from __future__ import annotations

import statistics
import time

from tools.verify_utils import isolated_workspace


def main() -> None:
    from novelforge.services.memory import create_project, project_path
    from novelforge.services.memory.knowledge_center import search_knowledge_center
    from novelforge.services.memory import open_project_db
    from storage.repositories import process_knowledge_index_jobs, upsert_knowledge_category_item

    with isolated_workspace("novelforge_large_search_"):
        project_name = create_project("large-search")
        with open_project_db(project_path(project_name)) as conn:
            for index in range(10_000):
                upsert_knowledge_category_item(
                    conn,
                    "characters",
                    {
                        "id": f"large-character-{index:05d}",
                        "name": f"角色 {index:05d}",
                        "summary": f"北港城第 {index:05d} 号角色档案，拥有编号线索 {index:05d}。",
                        "story_id": "default",
                        "typed_data": {"aliases": [f"角色{index:05d}"]},
                    },
                )
            process_knowledge_index_jobs(conn, limit=20_000)
            conn.commit()

        timings: list[float] = []
        first_page = None
        for _ in range(12):
            started = time.perf_counter()
            result = search_knowledge_center(
                project_name,
                query="北港城 05000",
                story_id="default",
                cursor="",
                page_size=40,
            )
            timings.append((time.perf_counter() - started) * 1000)
            first_page = result
        assert first_page and len(first_page["items"]) <= 40
        assert all(item["record_type"] == "knowledge" for item in first_page["items"])
        assert first_page["next_cursor"] or len(first_page["items"]) < 40
        p95 = sorted(timings)[max(0, int(len(timings) * 0.95) - 1)]
        assert p95 < 300, f"10k knowledge search p95 too slow: {p95:.1f}ms"
        print(f"large knowledge search verification: ok (count=10000, p95={p95:.1f}ms, median={statistics.median(timings):.1f}ms)")


if __name__ == "__main__":
    main()
