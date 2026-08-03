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

from . import common as _common
_export_module(_common)

from . import discussions as _discussions
_export_module(_discussions)

from . import generation as _generation
_export_module(_generation)

from . import analysis as _analysis
_export_module(_analysis)

from . import pipeline as _pipeline
_export_module(_pipeline)

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
