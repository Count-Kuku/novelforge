"""Read-only model capability status and operation preflight helpers."""

from __future__ import annotations

from novelforge.services.memory import get_active_llm_profile


def get_model_readiness(profile: dict | None = None) -> dict:
    active = dict(profile or get_active_llm_profile() or {})
    api_key = str(active.get("api_key") or "").strip()
    base_url = str(active.get("base_url") or "").strip()
    model_name = str(active.get("model_name") or "").strip()
    chat_status = str(active.get("chat_status") or "unverified").strip()
    chat_message = str(active.get("chat_status_message") or "").strip()
    if not api_key:
        chat_status = "missing"
        chat_message = "尚未填写 API Key。"
    elif not base_url or not model_name:
        chat_status = "missing"
        chat_message = "模型服务网址或聊天模型名不完整。"

    embedding_mode = str(active.get("embedding_mode") or "disabled").strip()
    embedding_model = str(active.get("embedding_model_name") or "").strip()
    embedding_status = str(active.get("embedding_status") or "unverified").strip()
    embedding_message = str(active.get("embedding_status_message") or "").strip()
    if embedding_mode == "disabled":
        embedding_status = "disabled"
        embedding_message = "语义向量已关闭，资料检索使用关键词模式。"
    elif not embedding_model:
        embedding_status = "missing"
        embedding_message = "尚未填写语义向量模型名，资料检索使用关键词模式。"
    elif embedding_mode == "separate_provider":
        embedding_key = str(active.get("embedding_api_key") or "").strip()
        embedding_url = str(active.get("embedding_base_url") or "").strip()
        if not embedding_key or not embedding_url:
            embedding_status = "missing"
            embedding_message = "独立向量服务的地址或 API Key 不完整，资料检索使用关键词模式。"
    elif embedding_mode == "local" and not str(active.get("embedding_base_url") or base_url).strip():
        embedding_status = "missing"
        embedding_message = "本地向量服务地址未设置，资料检索使用关键词模式。"

    semantic_available = embedding_status == "ready"
    return {
        "profile_id": str(active.get("id") or ""),
        "profile_name": str(active.get("name") or ""),
        "chat_status": chat_status,
        "chat_message": chat_message,
        "chat_available": chat_status in {"ready", "unverified"},
        "embedding_mode": embedding_mode,
        "embedding_status": embedding_status,
        "embedding_message": embedding_message,
        "embedding_available": semantic_available,
        "retrieval_mode": "hybrid" if semantic_available else "lexical",
        "verified_at": str(active.get("capabilities_verified_at") or ""),
    }


def require_chat_ready(profile: dict | None = None, *, action: str = "当前操作") -> dict:
    readiness = get_model_readiness(profile)
    if readiness["chat_status"] == "failed":
        raise RuntimeError(
            f"{action}无法开始：最近一次聊天模型验证失败。"
            f"{readiness['chat_message'] or '请先在“模型与费用”中重新测试连接。'}"
        )
    if not readiness["chat_available"]:
        raise RuntimeError(
            f"{action}无法开始：{readiness['chat_message']}请先在“模型与费用”中完成模型接入。"
        )
    return readiness

