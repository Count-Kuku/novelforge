"""Stable public facade assembled from focused implementation modules.

The facade preserves the historic module-level API while keeping each domain
implementation small enough to review and test independently.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

_IMPLEMENTATION_MODULES: list[ModuleType] = []


def _export_module(module: ModuleType) -> None:
    _IMPLEMENTATION_MODULES.append(module)
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        globals()[name] = value


def reload_implementation_modules():
    """Reload every implementation slice and refresh the public facade."""
    modules = list(_IMPLEMENTATION_MODULES)
    _IMPLEMENTATION_MODULES.clear()
    for module in modules:
        _export_module(importlib.reload(module))
    return sys.modules[__name__]

from . import core as _core
_export_module(_core)

from . import stories as _stories
_export_module(_stories)

from . import knowledge as _knowledge
_export_module(_knowledge)

from . import content as _content
_export_module(_content)

from . import references as _references
_export_module(_references)

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
