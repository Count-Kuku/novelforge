"""Stable public facade assembled from focused implementation modules.

The facade preserves the historic module-level API while keeping each domain
implementation small enough to review and test independently.
"""

from __future__ import annotations

import importlib
import logging
import sys
from types import ModuleType

_LOGGER = logging.getLogger("novelforge.services.memory")

_IMPLEMENTATION_MODULES: list[ModuleType] = []
# 符号名 -> 首次导出它的实现模块名，用于检测跨模块覆盖。
_SYMBOL_OWNER: dict[str, str] = {}


def _export_module(module: ModuleType) -> None:
    _IMPLEMENTATION_MODULES.append(module)
    module_name = getattr(module, "__name__", "")
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        owner = _SYMBOL_OWNER.get(name)
        # 跨模块覆盖告警：facade 用 globals() 平铺导出，两个模块定义同名函数时后者
        # 会静默顶替前者。这是真实事故源——服务门面版 load_entities(project_name)
        # 曾被 repository 版 load_entities(conn) 顶替，调用方拿到错误签名却无报错。
        # 同一模块因 importlib.reload 重复导出属正常，不告警。
        if owner is not None and owner != module_name and globals().get(name) is not value:
            _LOGGER.warning(
                "memory facade 符号冲突：%s 由 %s 覆盖 %s 中的定义，调用方可能拿到错误签名",
                name,
                module_name,
                owner,
            )
        _SYMBOL_OWNER[name] = module_name
        globals()[name] = value


def reload_implementation_modules():
    """Reload every implementation slice and refresh the public facade."""
    modules = list(_IMPLEMENTATION_MODULES)
    _IMPLEMENTATION_MODULES.clear()
    _SYMBOL_OWNER.clear()
    for module in modules:
        _export_module(importlib.reload(module))
    return sys.modules[__name__]

from . import paths as _paths
_export_module(_paths)

from . import rules as _rules
_export_module(_rules)

from . import storage_access as _storage_access
_export_module(_storage_access)

from . import project_registry as _project_registry
_export_module(_project_registry)

from . import db_availability as _db_availability
_export_module(_db_availability)

from . import llm_profiles as _llm_profiles
_export_module(_llm_profiles)

from . import asset_records as _asset_records
_export_module(_asset_records)

from . import context_directives as _context_directives
_export_module(_context_directives)

from . import domain_sync as _domain_sync
_export_module(_domain_sync)

from . import project_memory as _project_memory
_export_module(_project_memory)

from . import creative_sessions as _creative_sessions
_export_module(_creative_sessions)

from . import story_index as _story_index
_export_module(_story_index)

from . import story_lifecycle as _story_lifecycle
_export_module(_story_lifecycle)

from . import story_rules as _story_rules
_export_module(_story_rules)

from . import story_copy as _story_copy
_export_module(_story_copy)

from . import story_status as _story_status
_export_module(_story_status)

from . import story_memory as _story_memory
_export_module(_story_memory)

from . import creative_profiles as _creative_profiles
_export_module(_creative_profiles)

from . import creative_attachments as _creative_attachments
_export_module(_creative_attachments)

from . import creative_actions as _creative_actions
_export_module(_creative_actions)

from . import knowledge_paths as _knowledge_paths
_export_module(_knowledge_paths)

from . import knowledge_entities as _knowledge_entities
_export_module(_knowledge_entities)

from . import knowledge_revisions as _knowledge_revisions
_export_module(_knowledge_revisions)

from . import auto_review as _auto_review
_export_module(_auto_review)

from . import pending_knowledge as _pending_knowledge
_export_module(_pending_knowledge)

from . import knowledge_rules_options as _knowledge_rules_options
_export_module(_knowledge_rules_options)

from . import knowledge_center as _knowledge_center
_export_module(_knowledge_center)

from . import content_structure as _content_structure
_export_module(_content_structure)

from . import content_chapter as _content_chapter
_export_module(_content_chapter)

from . import knowledge_records as _knowledge_records
_export_module(_knowledge_records)

from . import content_reports as _content_reports
_export_module(_content_reports)

from . import long_reference_batches as _long_reference_batches
_export_module(_long_reference_batches)

from . import retrieval_assets as _retrieval_assets
_export_module(_retrieval_assets)

from . import database_sync as _database_sync
_export_module(_database_sync)

from . import ingestion_tasks as _ingestion_tasks
_export_module(_ingestion_tasks)

from . import web_research_tasks as _web_research_tasks
_export_module(_web_research_tasks)

class _FacadeModule(ModuleType):
    """Propagate compatibility patches to implementation modules.

    Existing tests and integrations historically patched attributes on the
    flat module. Keeping that behavior makes the package split non-breaking.
    """

    def __setattr__(self, name: str, value) -> None:
        super().__setattr__(name, value)
        if name.startswith("__"):
            return
        for module in _IMPLEMENTATION_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _FacadeModule
