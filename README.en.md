[中文](./README.md) | [English](./README.en.md)

# NovelForge

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
- long-form source importer for splitting uploaded or pasted novels by chapter/title or length before batch indexing, with clearer guidance for saving batches, indexing source text, and extracting knowledge
- long-form source batch manager for tracking whole-txt splitting, indexing, extraction, re-extraction, failures, and resume progress, with per-segment batch persistence after each extraction for terminal-interruption recovery
- one-click source processing for saving batches, indexing source text, extracting knowledge, auto-confirming low-risk items, and leaving conflicts or weak-evidence items for manual review
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
- entity alias library for preserving canonical names and aliases from quality-review hints, improving retrieval, character-card aggregation, and later extraction name normalization
- structured-knowledge organizer for duplicate detection, merging, deletion, and raw editing
- source package report generated from confirmed structured knowledge
- retrieval center for index rebuilds, recall tests, debug inspection, and conflict handling
- project creative profile for task nature, target length, workflow depth, and reference strength, with custom values supported
- creative task wizard for turning Chinese task goals into project creative settings
- dynamic generation entry that can run direct prose, short-form structure, or chapter-plan based generation from the creative profile
- structured knowledge ingestion from source material into characters, items, abilities, world rules, events, relationships, style, and constraints
- lexical, semantic, and hybrid retrieval
- authority-aware and conflict-aware evidence presentation
- retrieval debug preview for query terms, candidate chunks, and reranked hits
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

## Design Principles

NovelForge follows a few core principles:

1. Persistence before intelligence
2. Workflow before agents
3. Skills before autonomy
4. Project-oriented architecture
5. Model independence through an OpenAI-compatible interface

## Architecture

High-level flow:

```text
User
-> Streamlit UI (app.py)
-> Skill Layer (skills.py)
-> Prompt Layer (prompts.py)
-> LLM Interface (llm.py)
-> OpenAI-compatible API
-> Memory / Storage / Retrieval
```

Main file responsibilities:

- `app.py`: UI and interaction flow
- `skills.py`: writing and analysis capabilities
- `prompts.py`: prompt templates and composition
- `llm.py`: model abstraction and API integration
- `memory.py`: persistent storage and project data management
- `merge.py`: settings merge engine for cross-scope conflict detection and resolution (story, project, story-to-story)
- `schemas.py`: structured output contracts and validation
- `retrieval.py`: indexing, retrieval, and context formatting

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

- `Project Resources`: file-level management for outlines, chapters, reports, run snapshots, and source files.
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
- semantic embedding retrieval
- hybrid lexical + semantic ranking
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

The in-app creative task wizard can create this profile from plain Chinese task choices such as what to write, target length, output goal, reference strength, conflict policy, and notes.

The in-app `快速生成` (quick generation) page is designed for testing and experimentation:

- Works with just a prompt — no creative profile required
- Optional advanced configuration for fine control
- Suitable for side stories, continuations, prequels, crossovers, fragments, and other lightweight tasks

Full automatic orchestration for long-form volume/arc/chapter pipelines is still planned.

## Project Storage Structure

Each story is stored as an independent project under `data/projects/`.

Typical structure:

```text
data/
  global_rules.json
  projects/
    your_project/
      memory.json
      rules.json
      creative_profile.json
      outline.md
      knowledge/
      volumes/
      arcs/
      chapter_outlines/
      chapters/
      reviews/
      analysis/
      evaluation/
      retrieval/
      runs/
```

This keeps planning, draft chapters, reviews, analysis, and retrieval artifacts attached to the same project instead of scattering them across chat history.

Newer persisted artifacts include:

- `arcs/arc_xxx.chapter_plan.json`: arc-level chapter allocation plans
- `creative_profile.json`: project-level creative profile
- `knowledge/*.json`: confirmed structured knowledge records
- `knowledge/entities/characters.json`: character entity cards generated from confirmed structured knowledge
- `knowledge/entities/aliases.json`: canonical entity names and aliases
- `knowledge/pending.json`: pending structured-knowledge review queue
- `analysis/source_package.md`: source package report generated from structured knowledge
- `evaluation/chapter_xxx.md` / `.json`: chapter evaluation reports and structured scores
- `retrieval/conflict_resolutions.json`: saved retrieval conflict decisions
- `runs/*.json`: resumable pipeline run snapshots

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
.\build_release.ps1 -Version v0.1.0
```

3. The script will automatically:

- install `pyinstaller` into `.venv`
- build `NovelForge.exe` from `launcher.py`
- assemble `release/NovelForge-Portable/`
- create `release/NovelForge-windows-portable-v0.1.0.zip`
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

## Roadmap

### V2 backend maturation

- dedicated vector database backend
- deeper fact-level conflict recommendation logic
- stronger retrieval robustness

### V3 workflow runtime adoption

- graph or runtime-based workflow orchestration
- richer first-class retry and resume policies
- branching workflow execution

### V4 multi-agent architecture

Planned roles include:

- ChiefEditorAgent
- PlotAgent
- WriterAgent
- ReviewAgent
- MemoryAgent
- ResearchAgent

The first pre-agent step is implemented: source material can be split into typed structured knowledge and confirmed by the user before indexing. These extractors can later become specialist ingestion agents.

### V5 evaluation system

The initial chapter-level evaluation foundation is implemented and can persist Markdown and JSON reports.

Current evaluation dimensions include:

- character consistency
- writing quality
- plot progression quality
- information density
- emotional impact
- foreshadowing handling

Planned next steps:

- cross-version chapter comparison
- cross-run metric tracking
- automated evaluation suites for model and prompt changes

## Development Notes

The project keeps responsibilities intentionally separated:

- keep UI logic light in `app.py`
- add new writing capabilities through `skills.py`
- keep prompt engineering in `prompts.py`
- keep persistence logic in `memory.py`
- isolate model integration changes in `llm.py`
- define structured LLM outputs through `schemas.py`

For deeper implementation details and roadmap context, see `project.md`.

## License

The repository currently does not include a license file.
