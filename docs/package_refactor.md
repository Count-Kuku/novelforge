# Package refactor

## Goal

Keep the repository root limited to executable and distribution entrypoints,
group business code by responsibility, and prevent large facade modules from
growing as single files.

## Package layout

```text
novelforge/
├── core/       # schemas, prompts, model client, generic helpers
├── domain/     # knowledge and novel-writing domain rules
├── services/   # persistence, project resources, retrieval
└── workflows/  # application orchestration and generation flows
```

The repository root keeps `app.py` and `launcher.py` because Streamlit,
PyInstaller, and desktop launch scripts use them as executable entrypoints.

## Dependency direction

```text
ui -> workflows -> domain -> core
ui -> services -> domain/core
workflows -> services/domain/core
services -> storage/domain/core
```

`core` must not import UI or application workflows. Domain modules should not
depend on Streamlit. UI code may orchestrate public APIs, but it must not reach
into implementation slices such as `memory.stories` or `retrieval.search`.

## Large-module facades

Three historic modules remain stable public facades while their implementations
are split by responsibility:

- `novelforge.services.memory`: core project storage, stories, knowledge,
  generated content, and reference/runtime assets.
- `novelforge.services.retrieval`: text processing, document collection,
  index management, search/reranking, and external source ingestion.
- `novelforge.workflows.skills`: shared workflow helpers, discussions,
  generation, review/analysis, and resumable pipelines.

Callers import from the facade, not an implementation slice. The facade also
propagates attribute patches to its slices so existing tests and integrations
that patch module-level dependencies retain their previous behavior.

## Migration rules

1. New shared models and prompt primitives go under `novelforge.core`.
2. New business rules and knowledge transformations go under
   `novelforge.domain`.
3. New persistence and retrieval behavior goes under `novelforge.services`.
4. New multi-step generation behavior goes under `novelforge.workflows`.
5. Do not add new business `.py` files to the repository root.
6. Keep facade imports stable and add implementation slices when a facade file
   would otherwise exceed a reviewable size.
7. Update `build_release.ps1` whenever a new top-level package is introduced.

## Verification

The refactor is guarded by the existing `tools/verify_*.py` suite. Package
layout checks additionally verify that root Python files remain limited to the
two entrypoints and that implementation slices stay below the configured size
limit.
