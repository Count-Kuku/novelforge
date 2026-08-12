"""阶段 0：模型就绪、检索配置和关系图投影验收。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.core.llm import test_llm_capabilities
from novelforge.services.memory.core import _normalize_llm_profile
from novelforge.services.model_readiness import get_model_readiness, require_chat_ready
from novelforge.services.retrieval import resolve_retrieval_params
from novelforge.workflows import ingestion_tasks
from storage.repositories.knowledge import sync_knowledge_category
from storage.repositories.stories import sync_stories_index
from storage.schema import ensure_schema


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_model_readiness() -> None:
    deepseek = _normalize_llm_profile(
        {
            "id": "deepseek",
            "provider_type": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_key": "secret",
            "model_name": "deepseek-chat",
            "embedding_model_name": "text-embedding-3-small",
        },
        "deepseek",
    )
    check(deepseek["embedding_mode"] == "disabled", "旧 DeepSeek 配置默认显式关闭不兼容向量服务")
    readiness = get_model_readiness(deepseek)
    check(readiness["chat_available"], "配置完整但尚未测试的聊天模型允许进入操作")
    check(readiness["retrieval_mode"] == "lexical", "向量关闭时明确使用关键词检索")
    unverified_vector = _normalize_llm_profile(
        {
            "id": "openai",
            "provider_type": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "secret",
            "model_name": "chat-model",
            "embedding_mode": "same_provider",
            "embedding_model_name": "embed-model",
        },
        "openai",
    )
    check(
        get_model_readiness(unverified_vector)["retrieval_mode"] == "lexical",
        "未验证的向量配置不会冒充语义检索可用",
    )

    missing = {**deepseek, "api_key": ""}
    check(get_model_readiness(missing)["chat_status"] == "missing", "缺少 API Key 被识别为模型未就绪")
    try:
        require_chat_ready(missing, action="测试操作")
    except RuntimeError:
        pass
    else:
        raise AssertionError("缺少 API Key 时必须在持久化动作前失败")
    print("[PASS] 缺少 API Key 时操作前置校验失败")


class _FakeChatCompletions:
    def create(self, **_kwargs):
        return object()


class _FakeEmbeddings:
    def create(self, **_kwargs):
        item = type("EmbeddingItem", (), {"embedding": [0.1, 0.2]})()
        return type("EmbeddingResponse", (), {"data": [item]})()


class _FakeClient:
    def __init__(self, **_kwargs):
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions()})()
        self.embeddings = _FakeEmbeddings()


def verify_independent_capability_test() -> None:
    with patch("novelforge.core.llm._require_openai", return_value=_FakeClient):
        result = test_llm_capabilities(
            "https://chat.example/v1",
            "chat-key",
            "chat-model",
            embedding_mode="separate_provider",
            embedding_model_name="embed-model",
            embedding_base_url="https://embed.example/v1",
            embedding_api_key="embed-key",
        )
    check(result["chat_status"] == "ready", "聊天能力可独立验证")
    check(result["embedding_status"] == "ready", "独立向量能力可单独验证")
    with patch("novelforge.core.llm._require_openai", return_value=_FakeClient):
        disabled = test_llm_capabilities(
            "https://chat.example/v1",
            "chat-key",
            "chat-model",
            embedding_mode="disabled",
        )
    check(disabled["embedding_status"] == "disabled", "用户关闭向量与连接失败有不同状态")


def verify_retrieval_profile() -> None:
    drafting = resolve_retrieval_params(retrieval_profile="drafting")
    check("knowledge_world_rules" in drafting["allowed_source_types"], "正文检索覆盖世界规则")
    check("knowledge_timeline_events" in drafting["allowed_source_types"], "正文检索覆盖时间线")
    strict_timeline = resolve_retrieval_params(
        reference_focus=["时间线"],
        reference_strength="严格原作",
        retrieval_profile="drafting",
    )
    check(strict_timeline["top_k"] == 15, "参考强度会修改实际 top_k")
    check(strict_timeline["allowed_scopes"] == ["canon", "reference"], "严格原作会收窄资料范围")
    check("knowledge_timeline_events" in strict_timeline["allowed_source_types"], "参考重点会修改实际来源过滤")


def verify_preflight_before_persistence() -> None:
    batch = {
        "batch_id": "stage0-preflight",
        "title": "测试资料",
        "segments": [{"index": 1, "title": "片段", "content": "测试内容"}],
    }
    with (
        patch.object(ingestion_tasks, "require_chat_ready", side_effect=RuntimeError("missing")),
        patch.object(ingestion_tasks, "save_source_ingestion_task") as save_task,
    ):
        try:
            ingestion_tasks.create_long_reference_ingestion_task(
                "project",
                batch,
                [0],
                enabled_categories=["characters"],
                extraction_mode="deep",
                extract_limit=1,
                import_to_index=True,
                consolidate_after_extract=True,
                auto_confirm_safe_items=True,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("缺少聊天能力时不应创建资料提取任务")
        check(not save_task.called, "资料任务在能力校验通过前不会持久化")

    from ui import app_shell
    from ui.free_writing import composer

    with (
        patch.object(composer, "require_chat_ready", side_effect=RuntimeError("missing")),
        patch.object(composer, "create_writing_session") as create_session,
        patch.object(composer.st, "error"),
    ):
        composer._run_generation(
            "project",
            "default",
            "",
            {},
            "generate",
            None,
            "开始创作",
            {
                "word_count": "800-1200",
                "writing_guidance": {},
                "prompt_option_ids": [],
                "manual_knowledge_ids": [],
            },
            {"target_chapter_no": None, "auto_extract_mode": "on_accept"},
        )
        check(not create_session.called, "自由创作在能力校验通过前不会创建空会话")

    with patch.object(app_shell, "load_creative_profile", return_value={"is_configured": True}):
        check(
            app_shell.is_story_creative_profile_configured("project", "default"),
            "DB-only 创作配置不再依赖 JSON 镜像存在",
        )


def _active_edges(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT edge_id, source_node_id, target_node_id, relation_type, metadata_json
        FROM graph_edges WHERE deleted_at IS NULL ORDER BY edge_id
        """
    ).fetchall()


def verify_graph_projection() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    sync_stories_index(
        conn,
        {"stories": [{"story_id": "default", "name": "默认故事"}], "active_story_id": "default"},
    )
    item = {
        "id": "relationship-1",
        "story_id": "default",
        "category": "relationships",
        "name": "师徒关系",
        "typed_data": {"subject": "林雨", "object": "顾川", "relation_type": "师徒"},
    }
    sync_knowledge_category(conn, "relationships", [item])
    first = _active_edges(conn)
    check(len(first) == 1 and first[0]["relation_type"] == "师徒", "关系图读取 typed_data.relation_type")

    updated = {
        **item,
        "typed_data": {"subject": "林雨", "object": "沈舟", "relation_type": "盟友"},
    }
    sync_knowledge_category(conn, "relationships", [updated])
    second = _active_edges(conn)
    check(len(second) == 1 and second[0]["relation_type"] == "盟友", "关系修改会替换旧活动边")
    check(second[0]["edge_id"] != first[0]["edge_id"], "关系目标变化不会复用错误旧边")

    sync_knowledge_category(conn, "relationships", [])
    check(not _active_edges(conn), "删除关系知识会软删除其活动边")

    moved = {**updated, "category": "characters", "name": "林雨"}
    sync_knowledge_category(conn, "relationships", [updated])
    sync_knowledge_category(conn, "characters", [moved])
    check(not _active_edges(conn), "知识移出关系分类后不保留孤儿边")
    conn.close()


def main() -> int:
    verify_model_readiness()
    verify_independent_capability_test()
    verify_retrieval_profile()
    verify_preflight_before_persistence()
    verify_graph_projection()
    print("阶段 0 升级验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
