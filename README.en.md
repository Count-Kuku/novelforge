[中文](./README.md) | [English](./README.en.md)

# NovelForge

Current version: `v0.5.0`

NovelForge is an LLM-powered writing workspace for long-form fiction, built around persistent project storage, retrieval-augmented generation, structured workflows, and future multi-agent collaboration.

It is designed for long-running writing scenarios such as fan fiction, web novels, and original long-form projects, where consistency, memory, planning, and iterative revision matter more than one-shot chat output.

## Overview

Most LLM writing tools are optimized for short conversations and single-pass generation.
NovelForge focuses on a different problem space:

- long-term project-based writing
- persistent world and story memory
- end-to-end workflow from story outline to chapter drafting
- retrieval-augmented context injection
- structured review and validation
- architecture that can evolve toward workflow runtimes and agent systems

The project is both:

- a practical writing tool for long-form fiction
- an experimental platform for learning LLM apps, RAG, workflows, and agent design

## Current Status

NovelForge is already beyond an early prototype.

Current maturity can be summarized as:

- V1 writing workspace: implemented
- V1.1 persistence, validation, and UX hardening: implemented
- V2 retrieval foundation: largely implemented
- V3 workflow and state foundation: partially implemented, with failed-run resume support
- V4 multi-agent architecture: planned
- V5 evaluation system: initial chapter-level foundation implemented

## Core Capabilities

- project-based story storage
- story spaces: one project can hold multiple independent stories that share project-level canon/reference knowledge while keeping story assets separate
- story management: stories can be renamed, described, and copied into newly registered story spaces
- Streamlit web UI
- full-story outline generation
- chapter outline generation
- chapter writing
- chapter review
- memory updates from written chapters
- form-based story memory editing
- configurable chapter target word count
- memory compaction for long-running projects
- layered global and project rules
- project resources page for browsing, editing, and cleaning project files
- core story state page for short, high-priority settings injected into generation
- core-setting-to-knowledge conversion for turning stable settings into pending structured knowledge before project-wide reuse
- source ingestion page for importing canon/reference/sample text and extracting structured knowledge
- source ledger for summarizing long-form batches, retrieval sources, knowledge-only sources, processing status, and segment-level provenance
- long-form source importer for splitting uploaded or pasted novels by chapter/title or length before batch indexing, with strict-canon, fanfic-foundation, and style-reference initialization presets plus clearer guidance for saving batches, indexing source text, and extracting knowledge
- long-form source batch manager for tracking whole-txt splitting, indexing, extraction, re-extraction, failures, and resume progress, with per-segment batch persistence after each extraction for terminal-interruption recovery
- one-click source processing for saving batches, indexing source text, extracting knowledge, auto-confirming low-risk items, and showing batch progress; pages refresh automatically after long-running batch actions complete
- pending-queue clear mode for auto-saving low-risk items, archiving weak-evidence items, and moving conflicts/duplicates into a manual review box; processing records support full rollback and restoring manual-review snapshots back into the pending queue
- deep source-extraction modes for general, deep, character, relationship, timeline, worldbuilding, style, strict-canon, and fanfic-reference extraction
- specialist extraction presets for balanced, character, relationship, timeline, worldbuilding, style, canon-audit, and fanfic-research passes with matching categories and modes
- extraction category default strategies for starting from specialist presets, all categories, or no preselected categories
- advanced custom extraction instructions for pasted sources, long-form quick processing, and manual extraction
- multi-specialist extraction plans for long-form batches, including fanfic foundation, character/relationship, world/timeline, style reference, and strict-canon audit pipelines, with optional post-plan consolidation
- batch-level knowledge consolidation for turning scattered pending items into more stable character cards, relationships, timelines, and setting records
- character entity cards generated from confirmed character, relationship, ability, dialogue, timeline, and constraint knowledge
- long-form source fingerprinting to detect repeated uploads and continue existing batches
- pending structured-knowledge queue for reviewing extracted items before persistence
- pending extraction quality panel for same-name duplicates, field conflicts, fact-level conflicts with resolution suggestions, alias candidates, and overlap with confirmed knowledge
- pending review workspace with filters for category, source, keyword, and risk type, plus sorting by risk, evidence strength, confidence, importance, recency, or category
- pending knowledge form editor for correcting category, name, summary, details, evidence, tags, quality scores, provenance, and canon status without raw JSON editing
- confirmed knowledge form editor for maintaining persisted knowledge, moving categories, deleting incorrect items, and rebuilding retrieval indexes
- version/worldline metadata for separating canon, project-main, AU, branch, and mixed knowledge scopes
- ingestion health overview for imported-but-unextracted material, failed extraction, quality risks, category gaps, and worldline distribution
- project-level extraction plan templates with save, inspect, delete, and JSON-edit support for reusing multi-specialist pipelines across batches
- setting entity cards generated from world rules, locations, organizations, abilities, items, and constraints
- entity alias library for preserving canonical names and aliases from quality-review hints, expanding aliases at query time, improving retrieval, character-card aggregation, and later extraction name normalization
- structured-knowledge organizer for duplicate detection, merging, deletion, and raw editing
- source package report generated from confirmed structured knowledge
- retrieval center for index rebuilds, RAG health inspection, recall tests, debug inspection, and conflict handling
- project creative profile for task nature, target length, workflow depth, and reference strength, with custom values supported
- story-level worldline settings in the creative profile, including worldline ID/name and RAG worldline mode for later discussions and generation
- creative-profile discussion assist for turning natural-language goals into structured story creative settings
- quick-generation playground that can run direct prose, short-form structure, or chapter-plan based generation from the creative profile
- structured knowledge ingestion from source material into characters, items, abilities, world rules, events, relationships, style, and constraints
- lexical, semantic, and hybrid retrieval
- task-aware retrieval profiles for creative-profile discussion, outline discussion, volume discussion, arc discussion, chapter discussion, outline generation, chapter planning, drafting, and review/evaluation
- authority-aware and conflict-aware evidence presentation
- retrieval debug preview with selectable task profiles, query terms, candidate chunks, semantic status, and reranked hits
- persisted retrieval conflict resolutions
- character, timeline, foreshadowing, and consistency analysis
- chapter quality evaluation with structured scoring reports
- structured planning discussions for outline, volume, arc, and chapter direction
- approval-based planning artifacts
- one-click chapter pipeline with run snapshots and failed-run resume
- volume and arc planning hierarchy
- arc-level chapter allocation plans
- lightweight writing guidance controls
- in-app model endpoint and key configuration
- grouped navigation ordered by workbench, sources, planning, and writing; source ingestion is the first item in the sources group
- project overview metrics can jump directly into the resource browser for matching resource types

## Documentation Scope

This README is user-facing. It focuses on what NovelForge does, how to start using it, and how the source-ingestion, retrieval, planning, and writing flows work.

For deeper architecture, module responsibilities, storage layout, implementation notes, and roadmap details, see [project.md](./project.md).

## Typical Workflow

NovelForge supports both direct generation and discussion-first planning.

Typical chapter workflow:

1. discuss story or chapter direction
2. generate the full-story outline or chapter outline
3. write chapter content
4. review quality and consistency
5. update story memory
6. inspect analysis or retrieval evidence when needed
7. run chapter evaluation or resume a failed pipeline run when needed

The system also supports a combined pipeline:

```text
Plan -> Write -> Review -> Update Memory
```

## Sources, Core State, And Retrieval

NovelForge includes a project-scoped retrieval layer that works across both internal writing assets and external reference material.

The app separates three related concepts:

- `Resource Browser`: file-level management for outlines, chapters, reports, run snapshots, and source files, plus read-only inspection for structured knowledge, pending knowledge, and long-form batches.
- `Core State`: compact story settings that are injected with high priority, such as key canon mode, relationships, timeline items, and hard constraints.
- `Structured Knowledge Base`: long-lived project knowledge such as character cards, world rules, locations, organizations, power systems, relationships, timelines, and hard constraints, shared across stories and retrieval.
- `Source Ingestion` / `Retrieval Center`: ingestion imports and structures material; retrieval rebuilds indexes, tests recall, inspects debug output, and stores conflict decisions.
- `Long-Form Source Batches`: after a full txt upload, each segment records whether it has been indexed, extracted, failed, or is still pending.
- `Source Fingerprint`: stores content hash, file name, total length, and segment count to detect repeated full-source uploads.
- `Pending Structured Knowledge`: extracted items can be staged for review before they become indexed structured knowledge.
- `Structured Knowledge Organizer`: after long-form extraction, duplicate characters, abilities, locations, and other repeated entries can be merged or removed.
- `Source Package Report`: confirmed structured knowledge can be rendered into a saved and searchable project reference report.

Current retrieval capabilities include:

- project knowledge retrieval
- canon and reference retrieval
- long-form text splitting by chapter title or length before batch import
- long-form batch progress tracking with continue-indexing, continue-extraction, retry-failed, and re-extract-completed actions
- batch-level pending-knowledge consolidation with balanced, character-card, timeline, strict-canon, and style-focused modes
- repeated-upload detection with an option to bind to an existing batch
- document chunk indexing
- improved Chinese phrase recall through short ngram tokenization for names, items, abilities, and setting phrases
- entity-alias query expansion so canonical names, aliases, translated names, and short names can recall the same knowledge group
- semantic embedding retrieval
- hybrid lexical + semantic ranking
- worldline-aware retrieval with optional preference weighting or strict filtering; once a story creative profile saves a worldline, discussions, outline generation, chapter planning, drafting, and review use it automatically
- lightweight result diversification so one document or source type does not dominate all top hits
- retrieval feedback weighting: current hits can be marked helpful, priority, irrelevant, or wrong; later reranking uses those signals and exposes the adjustment in score breakdowns
- RAG evaluation workbench for saving fixed test queries, expected terms/chunks/source types, running single or full suites, and storing run results
- pre-generation retrieval briefing that summarizes source distribution, priority references, constraints/settings, and conflict resolutions before detailed evidence chunks
- post-generation source-usage reports on discussion, outline, planning, drafting, review, and evaluation pages, showing retrieved source distribution, priority references, hard constraints, and conflict resolutions
- explainable retrieval evidence in previews, workflow traces, and prompt context through matched terms, expanded aliases, recall reasons, score breakdowns, and evidence_meta
- RAG health inspection for index document/chunk counts, current source chunks, vector counts, missing vectors, stale chunks, source distribution, scope distribution, active embedding model, and embedding-model mismatch warnings
- retrieval center can rebuild keyword-only indexes or full indexes; keyword RAG remains usable when embeddings are unavailable
- discussion-first planning now uses RAG: creative-profile, outline, volume, arc, and chapter discussions can retrieve relevant settings, structured knowledge, imported sources, and approved discussion artifacts
- source authority weighting
- scope-grouped evidence display
- conflict warnings when project evidence and external evidence overlap
- persisted conflict resolutions that can be recalled as project knowledge
- optional retrieval debug output for inspecting recall and ranking behavior
- structured knowledge extraction from pasted material with human confirmation before persistence
- pasted-material extraction can use the same general, deep, character, relationship, timeline, worldbuilding, style, strict-canon, and fanfic-reference strategies as long-form batches
- source ledger aggregates long-form batches, imported retrieval sources, and knowledge-only sources with import, extraction, failure, pending, and confirmed counts
- long-form source details can inspect segment text and trace related pending or confirmed knowledge items
- pending review queue for accepting, discarding, or editing extracted knowledge before indexing
- pending review includes extraction-quality checks for same-name duplicates, same-name field conflicts, fact-level conflicts, alias candidates, and existing confirmed-knowledge overlap, with suggestions and merge actions for same-name groups
- automatic review policy and processing records for one-click, pasted-source, and pending-queue clear actions, including configurable thresholds, grade-B handling, manual-review categories, confirm/archive/manual-review decisions, pending snapshots, write targets, run-level rollback, single-item return, and manual-review snapshot restore
- alias-candidate hints can be saved into `knowledge/entities/aliases.json`; alias groups are indexed as `entity_alias_group`
- pending review supports category, source, keyword, and quality-risk filtering, plus risk-first, low-evidence, low-confidence, high-importance, newest-first, and category/name sorting
- pending review and confirmed-knowledge organization support worldline filtering for separating canon, project-main, and AU branch material
- individual pending items can be edited through a form, saved back to the pending queue, or saved and confirmed into the indexed knowledge base
- confirmed knowledge items can be edited through a form after persistence, including category, name, summary, details, evidence, quality scores, provenance, and tags
- core settings can be queued as pending structured knowledge, then confirmed into the project knowledge base for retrieval and cross-story reuse
- category-level structured-knowledge organization with duplicate detection, merge preview, deletion, and raw editing
- batched structured-knowledge extraction from selected long-form source segments
- selectable extraction strategies for general, deep, character, relationship, timeline, worldbuilding, style, strict-canon, and fanfic-reference passes
- long-form batches include an extraction coverage report for category coverage, missing/weak categories, low-evidence items, low-confidence items, no-evidence items, and segment progress
- re-extraction stores detailed comparisons against existing pending knowledge for that segment, including added, matched, possibly missing, changed fields, and old/new item snapshots
- re-extraction diff details can accept the new pass or keep the old pass by deleting the corresponding pending items
- multi-specialist extraction plans record per-step processed segment counts, queued knowledge counts, failures, and the latest plan summary on the batch; plans can optionally consolidate batch pending knowledge after extraction
- multi-specialist extraction plans can be saved as project templates and reused by later long-form batches
- extracted items preserve confidence, importance, evidence strength, canon status, extraction mode, and source-segment trace metadata
- extracted evidence can preserve and edit paragraph index, segment character offset, and a short context window for source review
- consolidation reads pending items linked to the current batch, merges duplicate entities and representative evidence, then replaces scattered pending items with consolidated pending records
- character entity cards are saved to `knowledge/entities/characters.json` and indexed as `entity_character_card`
- setting entity cards are saved to `knowledge/entities/settings.json` and indexed as `entity_setting_card`
- entity alias groups are saved to `knowledge/entities/aliases.json`, indexed as `entity_alias_group`, used when generating character entity cards, and injected into later extraction prompts as canonical-name context
- source package report generation from confirmed knowledge, saved into the retrieval index
- confirmed structured knowledge is indexed for later generation, review, analysis, and evaluation

## Creative Profile

Each project can store a creative profile describing the intended generation path:

- task nature: main story, side story, continuation, prequel, transmigration/AU, completion, scene fragment, or a custom value
- target length and optional word count, both customizable
- workflow depth, from direct prose generation to full long-form outline hierarchy
- reference strength: light, medium, strong, strict canon, or style-focused
- reference focus such as characters, worldbuilding, events, abilities, timeline, writing style, dialogue style, techniques, and hard constraints, with custom tags supported

This profile is injected into major generation, discussion, review, and analysis prompts so model behavior can adapt to length, workflow depth, and reference strength.

If the user is not sure how to configure the profile, the in-app creative-profile discussion assist can turn natural-language goals into recommended settings, backfill the form, and save an approved discussion artifact.

The in-app `快速生成` (quick generation) page is designed for testing and experimentation:

- Works with just a prompt — no creative profile required
- Optional advanced configuration for fine control
- Suitable for side stories, continuations, prequels, crossovers, fragments, and other lightweight tasks

Full automatic orchestration for long-form volume/arc/chapter pipelines is still planned.

## Data And Backups

NovelForge stores project data locally under `data/`, including project settings, story spaces, chapters, reviews, source materials, structured knowledge, retrieval indexes, and run history.

Recommendations:

- Back up the whole `data/` directory regularly.
- For the portable build, back up the app folder's `data/` directory and `.env`.
- For the full file layout and storage responsibilities, see the project storage section in [project.md](./project.md).

## Setup And Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure model access

You can configure model settings in either of these ways:

- edit `.env` manually
- use the in-app `模型配置` page to create and switch between multiple profiles

Typical environment values:

```env
LLM_API_KEY=
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_EMBEDDING_MODEL=text-embedding-3-small
```

### 3. Start the app

```bash
streamlit run app.py
```

## Local Windows Portable Build

NovelForge can also be packaged as a local Windows portable app that automatically starts the Streamlit server and opens the browser.

### Distribution shape

The intended local distribution is:

- `NovelForge.exe` as a lightweight launcher
- bundled `.venv` runtime
- project source files
- local `data/` directory for project storage

When the user launches `NovelForge.exe`, it will:

1. start a local Streamlit server on `127.0.0.1`, preferring `8501`
2. wait until the app is reachable
3. open the browser automatically

### Build steps

1. Create and prepare the local virtual environment:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

2. Run the packaging script from PowerShell:

```powershell
.\build_release.ps1 -Version v0.5.0
```

3. The script will automatically:

- install `pyinstaller` into `.venv`
- build `NovelForge.exe` from `launcher.py`
- assemble `release/NovelForge-Portable/`
- create `release/NovelForge-windows-portable-v0.5.0.zip`
- save a local build log under `release/`

### Notes

- extract the portable build into a writable folder such as `D:\Apps\NovelForge\`
- avoid protected folders such as `C:\Program Files\`
- user data will remain in the local `data/` folder and `.env`
- the launcher prefers `8501` and automatically falls back to nearby ports when needed
- if startup fails, check `launcher.log` in the app directory
- if one candidate port is occupied by another app, the launcher tries the next port instead of opening the wrong page
- build-time logs are written to `release/build_release-<version>.log`

## Model Strategy

The project is designed around an OpenAI-compatible API layer.

Current default direction:

- DeepSeek

Planned or compatible directions:

- GPT
- Claude
- Qwen
- local or self-hosted OpenAI-compatible models

## Development And Architecture Notes

README keeps to usage-level guidance. The following content is maintained in [project.md](./project.md):

- architecture and module responsibilities
- project storage layout
- RAG, source extraction, workflow, and evaluation implementation notes
- roadmap
- development boundaries and extension guidance

## License

The repository currently does not include a license file.
