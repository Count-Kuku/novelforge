"""Free-form interactive writing workflows.

This package preserves the historic ``novelforge.workflows.interactive_writing``
module API while splitting the 1300-line monolith into session/context/generation/
fragment-ops submodules. Callers keep importing unchanged.
"""

from __future__ import annotations

import sys
from types import ModuleType

from . import _session
from . import _context
from . import _generation
from . import _fragment_ops

from ._session import (
    _bundle_or_raise,
    _fragment_map,
    _now,
    _recent_fragment_text,
    _summary_refresh_material,
    accepted_active_fragments,
    active_fragment_chain,
    create_writing_session,
)
from ._context import (
    _claimed_attachment_blocks,
    _resolve_generation_branch,
    _session_context_blocks,
)
from ._generation import (
    build_writing_fragment_preflight,
    build_writing_session_query,
    generate_writing_fragment,
    preview_writing_context,
)
from ._fragment_ops import (
    accept_writing_fragment,
    compile_session_text,
    extract_fragment_knowledge,
    maybe_refresh_session_summary,
    pending_knowledge_for_fragment,
    save_writing_session_as_chapter,
    select_writing_fragment_variant,
)

# Re-export patchable dependencies (tests patch these on the flat module).
from novelforge.core.llm import call_llm
from novelforge.services.capabilities import require_operation_capabilities

_IMPLEMENTATION_MODULES: list[ModuleType] = [
    _session,
    _context,
    _generation,
    _fragment_ops,
]


class _FacadeModule(ModuleType):
    """Propagate compatibility patches to implementation submodules."""

    def __setattr__(self, name: str, value) -> None:
        super().__setattr__(name, value)
        if name.startswith("__"):
            return
        for module in _IMPLEMENTATION_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _FacadeModule

__all__ = [
    "create_writing_session",
    "active_fragment_chain",
    "accepted_active_fragments",
    "build_writing_session_query",
    "build_writing_fragment_preflight",
    "preview_writing_context",
    "generate_writing_fragment",
    "accept_writing_fragment",
    "select_writing_fragment_variant",
    "maybe_refresh_session_summary",
    "extract_fragment_knowledge",
    "pending_knowledge_for_fragment",
    "compile_session_text",
    "save_writing_session_as_chapter",
]
