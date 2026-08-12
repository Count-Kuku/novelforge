"""Central capability registry and operation requirement negotiation."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Callable


CAPABILITY_CHAT = "chat"
CAPABILITY_EMBEDDING = "embedding"
CAPABILITY_SEARCH = "search"
CAPABILITY_OCR = "ocr"


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability: str
    status: str
    available: bool
    message: str = ""
    provider: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationRequirements:
    operation: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    degradations: dict[str, str] = field(default_factory=dict)


OPERATION_REQUIREMENTS = {
    "creative_writing": OperationRequirements(
        "creative_writing",
        required=(CAPABILITY_CHAT,),
        optional=(CAPABILITY_EMBEDDING,),
        degradations={CAPABILITY_EMBEDDING: "语义检索不可用，自动降级为关键词检索。"},
    ),
    "source_ingestion": OperationRequirements(
        "source_ingestion",
        optional=(CAPABILITY_CHAT, CAPABILITY_EMBEDDING, CAPABILITY_OCR),
        degradations={
            CAPABILITY_CHAT: "保留原始资料，暂不执行 AI 提炼。",
            CAPABILITY_EMBEDDING: "资料索引自动降级为关键词索引。",
            CAPABILITY_OCR: "只读取文档文本层，扫描页保留待处理提示。",
        },
    ),
    "knowledge_query": OperationRequirements(
        "knowledge_query",
        optional=(CAPABILITY_EMBEDDING,),
        degradations={CAPABILITY_EMBEDDING: "知识查询使用关键词排序。"},
    ),
    "web_research": OperationRequirements(
        "web_research",
        required=(CAPABILITY_CHAT, CAPABILITY_SEARCH),
    ),
    "document_ocr": OperationRequirements("document_ocr", required=(CAPABILITY_OCR,)),
}


Probe = Callable[[], CapabilityStatus]


class CapabilityRegistry:
    def __init__(self) -> None:
        self._probes: dict[str, Probe] = {}

    def register(self, capability: str, probe: Probe) -> None:
        self._probes[str(capability)] = probe

    def inspect(self, capability: str) -> CapabilityStatus:
        probe = self._probes.get(str(capability))
        if probe is None:
            return CapabilityStatus(str(capability), "missing", False, "能力探针未注册。")
        try:
            return probe()
        except Exception as exc:
            return CapabilityStatus(str(capability), "failed", False, str(exc))

    def snapshot(self) -> dict[str, dict]:
        return {name: asdict(self.inspect(name)) for name in sorted(self._probes)}

    def negotiate(self, requirements: OperationRequirements) -> dict:
        names = dict.fromkeys((*requirements.required, *requirements.optional))
        statuses = {name: self.inspect(name) for name in names}
        blockers = [statuses[name] for name in requirements.required if not statuses[name].available]
        degradations = [
            {
                "capability": name,
                "message": requirements.degradations.get(name, statuses[name].message),
            }
            for name in requirements.optional
            if not statuses[name].available
        ]
        return {
            "operation": requirements.operation,
            "ready": not blockers,
            "statuses": {name: asdict(status) for name, status in statuses.items()},
            "blockers": [asdict(item) for item in blockers],
            "degradations": degradations,
        }


def _model_status(capability: str) -> CapabilityStatus:
    from novelforge.services.model_readiness import get_model_readiness

    readiness = get_model_readiness()
    if capability == CAPABILITY_CHAT:
        return CapabilityStatus(
            capability,
            str(readiness["chat_status"]),
            bool(readiness["chat_available"]),
            str(readiness["chat_message"]),
            str(readiness.get("profile_name") or ""),
        )
    return CapabilityStatus(
        capability,
        str(readiness["embedding_status"]),
        bool(readiness["embedding_available"]),
        str(readiness["embedding_message"]),
        str(readiness.get("profile_name") or ""),
        {"retrieval_mode": readiness.get("retrieval_mode")},
    )


def _search_status() -> CapabilityStatus:
    from novelforge.services.credentials import resolve_or_migrate_environment_credential

    key = resolve_or_migrate_environment_credential(
        purpose="web-search",
        owner_id="brave",
        environment_key="BRAVE_SEARCH_API_KEY",
    )
    available = bool(key)
    return CapabilityStatus(
        CAPABILITY_SEARCH,
        "ready" if available else "missing",
        available,
        "Brave Search 已配置。" if available else "尚未配置 Brave Search API Key。",
        "brave",
    )


def _ocr_status() -> CapabilityStatus:
    from novelforge.services.document_parsing import get_local_ocr_readiness

    readiness = get_local_ocr_readiness()
    available = bool(readiness.get("available"))
    return CapabilityStatus(
        CAPABILITY_OCR,
        "ready" if available else "missing",
        available,
        str(readiness.get("message") or ""),
        "tesseract",
        dict(readiness),
    )


def build_default_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_CHAT, lambda: _model_status(CAPABILITY_CHAT))
    registry.register(CAPABILITY_EMBEDDING, lambda: _model_status(CAPABILITY_EMBEDDING))
    registry.register(CAPABILITY_SEARCH, _search_status)
    registry.register(CAPABILITY_OCR, _ocr_status)
    return registry


def requirements_for_operation(operation: str) -> OperationRequirements:
    name = str(operation or "").strip()
    if name not in OPERATION_REQUIREMENTS:
        raise KeyError(f"未声明操作能力需求：{name}")
    return OPERATION_REQUIREMENTS[name]


def negotiate_operation(operation: str, *, registry: CapabilityRegistry | None = None) -> dict:
    active_registry = registry or build_default_capability_registry()
    return active_registry.negotiate(requirements_for_operation(operation))


def require_operation_capabilities(operation: str, *, action: str = "当前操作") -> dict:
    result = negotiate_operation(operation)
    if result["ready"]:
        return result
    details = "；".join(
        str(item.get("message") or item.get("capability") or "能力不可用")
        for item in result["blockers"]
    )
    raise RuntimeError(f"{action}无法开始：{details}")
