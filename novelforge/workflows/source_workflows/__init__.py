"""Facade re-exporting the source-workflow implementation modules."""
from __future__ import annotations

import sys
from types import ModuleType

from . import _base as __base
from . import reports_imports as _reports_imports
from . import extraction as _extraction
from . import consolidation as _consolidation

_IMPLEMENTATION_MODULES = [
    __base,
    _reports_imports,
    _extraction,
    _consolidation,
]

__all__ = [
    'AUTHORITY_LABELS',
    'CHAPTER_TITLE_PATTERN',
    'DEFAULT_WORLDLINE_ID',
    'DEFAULT_WORLDLINE_LABEL',
    'LOGGER',
    'SCOPE_LABELS',
    'derive_worldline_id',
    'label_authority',
    'label_scope',
    'build_long_reference_source_name',
    'build_source_package_report',
    'calculate_text_fingerprint',
    'decode_uploaded_text',
    'extract_pasted_reference_to_pending',
    'find_matching_long_reference_batches',
    'format_knowledge_item_for_report',
    'import_long_reference_segments',
    'import_organized_reference_entries',
    'normalize_text_for_fingerprint',
    'save_manual_retrieval_source_card',
    'split_long_reference_text',
    'build_extraction_coverage_report',
    'compare_extracted_items',
    'delete_extraction_plan_template',
    'extract_long_reference_segments_to_queue',
    'get_batch_pending_knowledge_items',
    'knowledge_identity',
    'locate_evidence_contexts',
    'make_extraction_plan_template_id',
    'run_long_reference_extraction_plan',
    'upsert_extraction_plan_template',
    'auto_confirm_pending_items_without_risk',
    'build_ingestion_health_report',
    'build_ingestion_source_ledger',
    'build_ingestion_workbench',
    'consolidate_batch_pending_items',
    'enrich_consolidated_knowledge_items',
    'get_segment_related_knowledge_items',
    'read_retrieval_source_payload',
    'run_long_reference_quick_process',
    'summarize_source_knowledge_counts',
]


class _FacadeModule(ModuleType):
    """Forward attribute writes (patch) to the owning implementation module."""

    def __setattr__(self, name, value):
        for impl in _IMPLEMENTATION_MODULES:
            if hasattr(impl, name):
                setattr(impl, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _FacadeModule

for _sym in __all__:
    for _impl in _IMPLEMENTATION_MODULES:
        if hasattr(_impl, _sym):
            globals()[_sym] = getattr(_impl, _sym)
            break

# Re-export imported symbols (e.g. list_long_reference_batches, extract_reference_knowledge)
# and private cross-module helpers (e.g. _safe_stream_emit) so the facade reproduces the
# original flat module's attribute surface for patch.object() and _sw.X access.
for _impl in _IMPLEMENTATION_MODULES:
    for _name, _value in vars(_impl).items():
        if _name.startswith("__") or _name == "_sw":
            continue
        if _name not in globals():
            globals()[_name] = _value
