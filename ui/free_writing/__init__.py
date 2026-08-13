"""Public facade for the free-writing UI package."""

from __future__ import annotations

import importlib
import sys

from . import chapter_panel as _chapter_panel
from . import composer as _composer
from . import context_panel as _context_panel
from . import fragments as _fragments
from . import knowledge_panel as _knowledge_panel
from . import page as _page
from . import session_controls as _session_controls
from . import shared as _shared


def reload_components():
    """Reload component modules in dependency order for Streamlit development."""
    for module in (
        _shared,
        _session_controls,
        _fragments,
        _knowledge_panel,
        _chapter_panel,
        _composer,
        _context_panel,
        _page,
    ):
        importlib.reload(module)
    globals()["render_dynamic_generation_page"] = _page.render_dynamic_generation_page
    return sys.modules[__name__]


render_dynamic_generation_page = _page.render_dynamic_generation_page

__all__ = ["reload_components", "render_dynamic_generation_page"]
