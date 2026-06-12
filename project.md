# NovelForge

## Project Overview

NovelForge is a long-form novel writing system built around LLMs, memory management, workflow automation, and future multi-agent collaboration.

The primary goal is not to create a chatbot, but to build a persistent writing workspace capable of supporting long-term novel creation, especially fan fiction and web novels.

The project is designed as a learning platform for:

* LLM Application Development
* Agent Systems
* Workflow Design
* Memory Management
* RAG (Retrieval-Augmented Generation)
* Long-Context Story Generation

---

# Current Stage

NovelForge is no longer best described as "only V1".

The roadmap labels `V1` through `V5` still describe the long-term evolution path, but the current codebase is more accurately described by implementation maturity:

* `V1` core writing workspace: implemented
* `V1.1` persistence, validation, and UI hardening: implemented
* `V2` RAG foundation: largely implemented
* `V3` workflow/state foundation for graph execution: partially implemented
* `V4` multi-agent architecture: planned
* `V5` evaluation system: planned

Current practical status:

* Project-based storage
* Outline generation
* Chapter outline generation
* Chapter writing
* Chapter review
* Memory update
* DeepSeek API integration
* Configurable OpenAI-compatible model endpoint
* Structured review status output
* Safer memory update validation
* Streamlit UI
* Configurable temperature and system message for LLM calls
* Form-based memory editing (no raw JSON required)
* Configurable target word count per chapter
* Memory compaction for long-running projects
* Pipeline with per-step error isolation and partial result recovery
* Configurable recent summary count (default 5)
* Layered prompt rules (global + project scope)
* In-app rule management and requirement capture
* Character/timeline/foreshadowing/consistency analysis
* Persistent analysis report storage
* Pydantic schema validation for core LLM outputs
* Retrieval document/chunk schema for RAG workflows
* Searchable project/external knowledge index with scoped retrieval
* Hybrid retrieval with lexical + semantic scoring
* Retrieval evidence grouping, authority weighting, conflict warnings, and reranking
* Structured pasted-reference organization and single-page URL reference ingestion for canon/reference knowledge
* Discussion-first planning support for full-story outline and chapter direction before formal generation
* Persisted chapter pipeline state snapshots, transition logs, and resumable workflow hints
* Story-state oriented memory fields for canon mode, AU rules, relationships, and active constraints
* Multi-turn planning discussion UI with continuously updated discussion conclusions
* Project management workspace with project overview, rename/delete, and resource CRUD
* IDE-style resource browser for outlines, chapters, reviews, analysis reports, run snapshots, and external sources

In short: the project already has a working V1 product, substantial V2 groundwork and implementation, and meaningful V3 preparation.

---

# Design Philosophy

NovelForge follows several principles:

1. Persistence before intelligence

A system that remembers is more useful than a system that only generates.

2. Workflow before agents

Stable workflows should be built before introducing multiple agents.

3. Skills before autonomy

Reusable skills are preferred over unconstrained agent behavior.

4. Project-oriented architecture

All writing should belong to a project with persistent files.

5. Model independence

The project should support switching between DeepSeek, GPT, Claude, Qwen, and other models with minimal code changes.

---

# Architecture Overview

Current architecture:

User
↓
Streamlit UI
(app.py)
↓
Skill Layer
(skills.py)
↓
Prompt Layer
(prompts.py)
↓
LLM Interface
(llm.py)
↓
OpenAI-compatible API endpoint
↓
Memory Layer
(memory.py)
↓
Project Storage
↓
Prompt Rules
(global + project scoped)
↓
Retrieval Layer
(retrieval.py)

---

# Directory Structure

novelforge/

├── app.py

├── llm.py

├── memory.py

├── retrieval.py

├── schemas.py

├── prompts.py

├── skills.py

├── requirements.txt

├── .env

├── .env.example

├── project.md

└── data/

```
├── global_rules.json

└── projects/

    └── {project_name}/

        ├── memory.json

        ├── rules.json

        ├── outline.md

        ├── chapter_outlines/

        ├── chapters/

        ├── reviews/

        ├── analysis/

        └── retrieval/

            ├── manifest.json

            ├── vectors.json

            └── sources/
```

---

# File Responsibilities

## app.py

Streamlit user interface.

Responsibilities:

* Project selection
* User interaction
* Displaying outputs
* Calling skills
* Managing UI state
* Consuming structured review/update results produced by the schema layer
* Rendering shared workflow step status / validation / JSON / retrieval blocks through reusable UI helpers
* Managing retrieval sources, index rebuilds, and retrieval preview
* Exposing retrieval mode and score breakdown for debugging/learning
* Organizing pasted reference text and URL pages into structured retrieval-ready entries before ingestion
* Discussing outline and chapter direction in structured form before committing to formal generation steps
* Listing and deleting imported external source files from the retrieval center, with automatic index rebuild after removal
* Providing a project overview page with project-level statistics, rename, and delete operations
* Managing project resources through an IDE-style browser with unified preview/edit/save/delete behavior
* Supporting direct CRUD for outlines, chapter files, review artifacts, analysis artifacts, run snapshots, and external sources from the UI
* Supporting batch cleanup for chapter bundles, run snapshots, and external sources

UI features:

* Memory editing via structured form (title, genre, world, characters, etc.)
  with raw JSON fallback in collapsible section
* Word count configuration per chapter
* Pipeline page shows per-step success/error status with partial results
* One-click memory compaction button
* Rule center for managing global/project prompt constraints
* Quick requirement capture with selectable target scope
* Dedicated analysis page for consistency / character / timeline / foreshadowing checks
* Review and analysis result refresh via Streamlit session state synchronization
* Retrieval hit inspection in generation, review, analysis, and pipeline result pages
* Shared rendering helpers for workflow-step status, schema validation, structured payloads, and retrieval evidence
* Pipeline page can now inspect persisted run snapshots, transition logs, and structured workflow errors
* Resource browser with left-side file navigation and right-side editor/detail panel

Business logic should remain minimal.

Current UI design note:

* `app.py` now includes lightweight reusable render helpers so pages consume `WorkflowStepResult` objects consistently instead of hand-formatting each skill result independently

---

## llm.py

Model abstraction layer.

Responsibilities:

* Model connection
* API configuration
* Model switching
* API key validation
* Support for temperature and system message per call
* Provide embedding generation for semantic retrieval

Current model:

* DeepSeek Chat

Current configuration:

* `LLM_API_KEY` or `DEEPSEEK_API_KEY`
* `LLM_BASE_URL` (optional)
* `LLM_MODEL` (optional)

Interface:

`call_llm(prompt, system_message="", temperature=0.7)`

`get_embedding(text)`

* `system_message` — optional system role instruction
* `temperature` — per-call temperature control (default 0.7)
* `get_embedding` — embedding lookup for retrieval indexing and semantic search

Future models:

* GPT
* Claude
* Qwen
* Local LLMs

Only this file should need modification when switching models.

---

## memory.py

Persistence layer.

Responsibilities:

* Project creation
* Loading memory
* Saving memory
* Loading global rules
* Saving global rules
* Loading project rules
* Saving project rules
* Loading outlines
* Saving outlines
* Loading chapter outlines
* Saving chapter outlines
* Loading chapters
* Saving chapters
* Loading reviews
* Saving reviews
* Loading analysis reports
* Saving analysis reports
* Saving pipeline run state snapshots
* Loading historical pipeline runs
* Listing pipeline runs for inspection and future resume/replay flows
* Fetching recent chapter summaries (configurable limit, default 5)
* Counting total written chapters

No LLM logic should exist here.

---

## schemas.py

Pydantic schema layer.

Responsibilities:

* Define machine-readable output contracts for LLM steps
* Define machine-readable output contracts for workflow steps and pipeline state
* Validate review payloads
* Validate memory update payloads
* Define structured analysis result models
* Define structured reference-organization result models for controlled knowledge ingestion
* Define structured discussion result models for outline-level and chapter-level planning conversations
* Define retrieval documents, chunks, hits, and index manifest models
* Convert validated analysis objects into Markdown for UI/storage
* Centralize schema error formatting

Design purpose:

* Move from ad-hoc JSON parsing to schema-first validation
* Provide stable typed data for future retrieval/workflow/evaluation upgrades
* Allow tolerant input normalization where LLMs return object-shaped list items instead of plain strings
* Standardize `WorkflowStepResult` / `WorkflowPipelineResult` so UI and future workflow engines consume the same result contract
* Define explicit chapter workflow state objects before introducing an external workflow runtime

---

## retrieval.py

Retrieval and indexing layer.

Responsibilities:

* Convert project storage into searchable retrieval documents
* Ingest external canon/reference files into project-scoped retrieval storage
* Chunk long documents into retrieval units
* Persist a project retrieval manifest for reuse
* Persist retrieval vectors for semantic search reuse
* Execute scoped retrieval over project/canon/reference knowledge
* Format retrieved context for prompt injection

Current retrieval design notes:

* Current retrieval supports lexical, semantic, and hybrid modes
* Retrieval documents are separated from prompt logic so the indexing contract remains reusable
* Scope priority currently prefers `project`, then `canon`, then `reference`
* Retrieval is already injected into outline, chapter planning, writing, review, memory update, and analysis steps
* Hybrid mode combines explicit term matches with embedding similarity for more robust retrieval
* Chunking is now source-aware: structured records stay atomic, Markdown-like sources split by section and paragraph, and long prose falls back to overlapping windows
* External materials can be ingested through typed templates such as character sheets, location sheets, canon events, and world rules
* Reference ingestion now supports two controlled entry points: pasted raw text and single-page URL fetches, both normalized into structured retrieval entries before persistence
* Imported external source files can now be removed from the retrieval center; deletion is followed by a retrieval asset rebuild so the search index stays consistent
* Retrieval is now observable from generation pages: major steps expose the actual hits used for prompt augmentation
* Review and analysis outputs now append supporting source references derived from retrieval hits
* Retrieval evidence is now grouped by `project`, `canon`, and `reference` scope so source hierarchy is explicit in both UI and outputs
* External sources now carry authority metadata and authority-aware weighting influences retrieval ranking and evidence display
* The system now flags potential conflicts when project-grounded evidence overlaps with canon/reference evidence under the same retrieval terms

---

## prompts.py

Prompt template layer.

Responsibilities:

* Outline generation prompts
* Chapter outline prompts
* Chapter writing prompts (supports configurable word count)
* Chapter review prompts
* Character analysis prompts
* Timeline analysis prompts
* Foreshadowing analysis prompts
* Consistency check prompts
* Memory update prompts
* Memory compaction prompts
* Reference organization prompts for pasted text and fetched pages
* Discussion prompts for outline-level and chapter-level planning
* Formatting layered rule blocks for prompt injection
* Merging retrieved context into generation prompts

Current prompt design notes:

* Chapter review prompt requests strict JSON for later workflow automation
* Analysis prompts request strict JSON, then the schema layer renders validated results into Markdown
* Memory update prompt requests strict JSON for safer persistence
* Chapter writing prompt accepts `word_count` parameter (default 2000-2500)
* Memory compaction prompt compresses old character/world/timeline/foreshadowing entries to control prompt length
* All major generation prompts can receive layered rule text assembled from global and project storage
* Retrieved context is appended after the base prompt so retrieval remains a composable layer

Prompt engineering should be isolated here.

---

## skills.py

Skill execution layer.

Responsibilities:

* Generate outline
* Generate chapter outline
* Write chapter (with configurable word count)
* Review chapter
* Update memory
* Compact memory (compress old entries to control prompt length)
* Merge layered rules into prompts before LLM calls
* Save user requirements into global or project rule storage
* Consistency check
* Character analysis
* Timeline analysis
* Foreshadowing analysis
* Retrieve relevant internal/external context before major LLM calls
* Return normalized workflow step objects for key execution paths
* Organize pasted or fetched reference material into structured retrieval entries before storage
* Produce structured discussion results for outline and chapter planning before generation

Current skill design notes:

* Review results are validated through Pydantic schemas before persistence
* Analysis skills validate JSON through Pydantic schemas, normalize object-shaped list items into strings when needed, then render Markdown reports under the project `analysis/` directory
* Analysis skills now return the same workflow step contract as generation/review/memory-update steps, including validated structured payloads and persisted Markdown reports
* Memory updates are validated through Pydantic schemas before being written into project storage
* All LLM-calling functions check for empty responses and raise explicit errors
* `pipeline_plan_write_review_update` executes steps independently — if one fails,
  remaining steps are skipped and partial results are still returned
* Key workflow steps now return a common structure containing `success`, `status`, `data`, `error`, `warnings`, `retrieval_hits`, `validation`, and `artifacts`
* The same step-result contract now covers outline generation, chapter planning, chapter writing, chapter review, memory update, and the combined pipeline
* The chapter pipeline now maintains an explicit state object with current step, step history, warnings, halt reason, and structured error records
* Pipeline runs are now persisted under project storage so state snapshots can be inspected after execution
* Step failures are now normalized into structured workflow errors with typed categories such as `validation`, `persistence`, `retrieval`, `input`, and `llm`
* Reference ingestion is currently human-in-the-loop: the system organizes material first, shows a structured preview, then imports into retrieval storage only after explicit confirmation
* Rule injection order is: global common rules -> project common rules -> global scoped rules -> project scoped rules
* Retrieval is task-aware: different generation steps query different source types and scopes
* Retrieval traces are now surfaced to the UI so prompt context provenance can be inspected step by step
* Review and analysis reports now include citation-style supporting source sections for better explainability
* Analysis results now expose both `data.analysis` (structured payload) and `data.report_markdown` (rendered report) to the UI
* Outline and chapter planning can now be preceded by structured discussion steps that return machine-readable options, risks, open questions, and recommended directions
* Retrieval evidence is grouped by scope and source type to make trust boundaries and source provenance easier to inspect
* External-source trust metadata is now visible and participates in ranking, making authority boundaries explicit during retrieval review
* Potential conflicts are now surfaced when project evidence and external evidence overlap, giving the user an early warning before trusting a generated diagnosis

---

# Current Workflow

Outline Generation

Discussion-first variant:

User Idea
↓
discuss_outline
↓
structured discussion result
↓
generate_outline

User Idea
 +
Applicable Rules
↓
generate_outline
↓
outline.md

The step now returns a structured result object with:

* `data.outline`
* `retrieval_hits`
* `artifacts.saved_path`

---

Chapter Planning

Discussion-first variant:

Requirement + Outline + Recent Summaries
↓
discuss_chapter
↓
structured discussion result
↓
generate_chapter_outline

Outline

Recent Chapter Summaries
 +
Retrieved Context
 +
Applicable Rules
↓
generate_chapter_outline
↓
chapter_outlines/chapter_xxx.md

The step now returns a structured result object with:

* `data.chapter_outline`
* `retrieval_hits`
* `artifacts.saved_path`

---

Chapter Writing

Chapter Outline
+
Memory
 +
Retrieved Context
 +
Applicable Rules
↓
write_chapter
↓
chapters/chapter_xxx.md

The step now returns a structured result object with:

* `data.chapter`
* `retrieval_hits`
* `artifacts.saved_path`

---

Memory Update

Chapter
 +
Retrieved Context
 +
Applicable Rules
↓
update_memory_from_chapter
↓
memory.json

If JSON validation fails:
↓
return rejected result without modifying memory.json

Validation is performed through `schemas.py`.

The step now returns a structured result object:

* `success` / `status` indicate whether the update completed, failed, or was rejected
* `validation` records schema-pass or schema-fail information
* `artifacts.raw_response` preserves the raw model output when rejection happens
* `retrieval_hits` keeps the exact supporting context used during the update attempt

---

Chapter Review

Chapter Outline
+
Chapter
+
Memory
 +
Retrieved Context
 +
Applicable Rules
↓
review_chapter
↓
structured review status
↓
reviews/chapter_xxx.md
↓
reviews/chapter_xxx.json

Validation is performed through `schemas.py` before save.

The step now returns a structured result object:

* `data.review` contains schema-validated machine-readable review fields
* `data.review_markdown` contains the persisted human-readable report
* `validation` records whether review JSON matched the expected schema
* `warnings` can note fallback behavior when blocked markdown had to be generated from invalid model output

---

Pipeline Result Contract

`pipeline_plan_write_review_update` now returns a pipeline object shaped like:

* `success` — overall pipeline status
* `steps.chapter_outline`
* `steps.write_chapter`
* `steps.review_chapter`
* `steps.memory_update`

Each step uses the shared workflow step schema so the UI can render status, errors, validation state, retrieval evidence, and saved artifacts without special-case parsing.

The pipeline now also returns a chapter workflow state object containing:

* `current_step`
* `next_step`
* `last_successful_step`
* `chapter_outline`
* `chapter`
* `review`
* `review_markdown`
* `memory_update`
* `completed_steps`
* `failed_steps`
* `retry_counts`
* `transition_log`
* `errors`
* `run_id`
* `started_at` / `finished_at`
* `halted` / `halt_reason`
* `resumable`

Current observability note:

* The pipeline UI now shows transition logs, typed workflow errors, and resumable hints derived from persisted chapter run state

---

Analysis Result Contract

Consistency, character, timeline, and foreshadowing analysis steps now return structured workflow step objects with:

* `data.analysis` — schema-validated analysis payload
* `data.report_markdown` — persisted Markdown report with supporting sources / conflict notes
* `validation` — analysis schema validation status
* `retrieval_hits` — exact evidence used during the analysis step

---

Planning Discussion Contract

The system now supports structured planning discussions for:

* full-story outline direction
* chapter direction

These discussion steps return workflow step objects with:

* `data.discussion` — schema-validated discussion payload
* `data.report_markdown` — human-readable planning discussion report
* options with strengths / risks
* open questions and recommended direction
* `approval_ready` — whether the current discussion is ready to move into formal generation

---

# Project Storage Structure

Each novel project owns its own directory.

Example:

data/projects/fanfic_project/

Files:

memory.json

Stores:

* characters
* world settings
* timeline
* foreshadowing
* chapter summaries

rules.json

Stores project-scoped prompt rules by capability:

* all
* outline
* chapter_outline
* write
* review
* memory_update

outline.md

Stores the global story outline.

chapter_outlines/

Stores chapter plans.

chapters/

Stores chapter content.

reviews/

Stores review results.

analysis/

Stores consistency, character, timeline, and foreshadowing analysis reports.

retrieval/

Stores retrieval index artifacts and external knowledge sources.

runs/

Stores persisted chapter pipeline run snapshots for history inspection and future resume/replay flows.

Files:

* `manifest.json` — project-scoped retrieval documents and chunks
* `vectors.json` — chunk embedding vectors for semantic retrieval
* `sources/` — externally added canon/reference materials
* `runs/` stores structured pipeline state snapshots keyed by run id

Note:

* Analysis reports are stored as Markdown for human reading
* Their source LLM outputs are now expected to conform to Pydantic-backed JSON schemas before rendering

global_rules.json

Stored under `data/` and shared across all projects.

---

# Rule Structure

Current rule schema:

{
"all": [],
"outline": [],
"chapter_outline": [],
"write": [],
"review": [],
"memory_update": []
}

Usage notes:

* `all` applies to every generation step
* Other fields apply only to their matching capability
* Global rules are loaded from `data/global_rules.json`
* Project rules are loaded from `data/projects/{project_name}/rules.json`

---

# Memory Structure

Current memory schema:

{
"title": "",
"genre": "",
"world": [],
"characters": [],
"timeline": [],
"foreshadowing": [],
"chapter_summaries": []
}

Future versions may introduce:

* locations
* organizations
* power systems
* relationship graphs

---

# Roadmap And Stage Status

## Current Position

NovelForge should currently be understood as:

* a complete `V1` writing workspace
* an implemented `V1.1` persistence and validation upgrade
* a mostly implemented `V2` retrieval layer
* a `V3` workflow system whose state model and persistence layer already exist, but whose future graph runtime is not yet fully adopted

This section tracks both what has already landed and what remains before each roadmap stage can be considered complete.

## Near-Term Focus

The highest-value next steps are no longer the original V1 items; they are the remaining gaps after the current foundation work:

1. Mature the retrieval backend

Current retrieval works with embeddings, hybrid scoring, reranking, observability, and structured ingestion. The next step is moving beyond file-based vector persistence toward a dedicated vector backend and stronger fact-level conflict handling.

2. Finish workflow runtime adoption

The project already has explicit workflow state, structured step contracts, persisted run snapshots, and transition logs. The next step is to map this into a graph/runtime layer with first-class retry, branching, and resume behavior.

3. Strengthen planning and approval loops

Structured outline discussion and chapter discussion are already implemented. The next step is turning those discussions into clearer approval checkpoints and more reusable planning artifacts.

4. Prepare for evaluation

Structured outputs, retrieval traces, and workflow state now make evaluation feasible. The next step is defining stable metrics and artifact collection so future automated evaluation can measure quality over time.

---

## V1

Core Writing Workspace

Status:

* Implemented

Delivered capabilities:

* Project-based storage
* Streamlit UI
* Outline generation
* Chapter outline generation
* Chapter writing
* Chapter review
* Memory update
* Model abstraction through an OpenAI-compatible interface

Interpretation:

* The original V1 goal is already achieved. NovelForge is already more than a prototype chat wrapper; it is a persistent project-oriented writing workspace.

---

## V1.1

Persistence, Validation, and UX Hardening

Status:

* Implemented

Current implementation status:

* Implemented: auto-save for outline generation
* Implemented: auto-save for chapter outline generation
* Implemented: chapter review persistence
* Implemented: recent chapter summaries as planning context
* Implemented: structured review status normalization
* Implemented: reject invalid memory update payloads before persistence
* Implemented: expose structured review status directly in UI controls
* Implemented: configurable word count target per chapter
* Implemented: memory compaction for long-running projects
* Implemented: per-step error isolation in pipeline
* Implemented: form-based memory editing (non-JSON users)
* Implemented: persistent global/project rule storage
* Implemented: in-app rule center and quick requirement capture
* Implemented: chapter-level consistency / character / timeline / foreshadowing analysis
* Implemented: persistent Markdown analysis reports under project storage
* Implemented: review page result refresh fix for Streamlit session state behavior
* Implemented: `schemas.py` Pydantic schema layer for review, memory update, and analysis outputs
* Implemented: schema-validated JSON-to-Markdown rendering pipeline for analysis results
* Implemented: unified workflow step result contract for outline / chapter outline / writing / review / memory update / pipeline
* Implemented: unified workflow step result contract for consistency / character / timeline / foreshadowing analysis
* Implemented: structured outline discussion before formal outline generation
* Implemented: structured chapter discussion before formal chapter outline generation
* Implemented: multi-turn outline discussion with assistant replies and continuously updated discussion summaries
* Implemented: multi-turn chapter discussion with assistant replies and continuously updated discussion summaries
* Implemented: project overview page and project rename/delete controls
* Implemented: project resource CRUD for outlines, chapters, reviews, analysis reports, run snapshots, and external sources
* Implemented: IDE-style resource browser with unified edit/save/delete flows and batch cleanup controls

Interpretation:

* What was originally a persistence-improvement stage has effectively been completed and expanded into a schema-first, workflow-aware product hardening phase.

---

## V2

RAG Integration

Status:

* Foundation largely implemented
* Backend maturation still pending

Features:

* Embeddings
* Vector storage
* Semantic retrieval
* Hybrid context selection
* Retrieval observability
* Authority-aware and conflict-aware evidence handling

Current implementation status:

* Implemented: retrieval document/chunk/index manifest schemas
* Implemented: project/external source ingestion into retrieval storage
* Implemented: lexical scoped retrieval with prompt injection across major skills
* Implemented: in-app retrieval center for index rebuild, source management, and retrieval preview
* Implemented: project-scoped embedding generation via `llm.py`
* Implemented: embedding-backed `vectors.json` storage for semantic retrieval
* Implemented: lexical / semantic / hybrid retrieval modes with score breakdown in UI
* Implemented: source-aware smart chunking for structured records, Markdown sections, and long prose
* Implemented: typed external source templates for better RAG ingestion quality
* Implemented: per-step retrieval trace display in generation, review, analysis, and pipeline result views
* Implemented: supporting source sections in review and analysis outputs
* Implemented: scope-aware grouped evidence display for retrieval traces and supporting sources
* Implemented: authority-aware metadata capture, ranking, and evidence display for external sources
* Implemented: conflict-aware warnings in retrieval evidence views and diagnostic outputs
* Implemented: structured conflict objects with severity and rationale
* Implemented: lightweight retrieval reranking after initial lexical/semantic scoring
* Implemented: pasted reference organization into structured retrieval-ready entries
* Implemented: single-page URL fetch and organization for controlled canon/reference ingestion
* Pending: dedicated external vector database backend
* Pending: deeper fact-level conflict resolution and recommendation logic

Possible technologies:

* Chroma
* SQLite + embeddings
* FAISS

Interpretation:

* `V2` should no longer be described as future-only. Most user-facing RAG behavior already exists; the main remaining work is backend robustness and deeper retrieval reasoning.

---

## V3

Workflow / LangGraph Preparation

Status:

* Foundation partially implemented
* External graph runtime adoption pending

Features:

* State management
* Workflow execution
* Automatic chapter pipeline
* Resume / replay / retry groundwork

Current implementation status:

* Implemented: one-click chapter pipeline across planning, writing, review, and memory update
* Implemented: per-step error isolation with partial result recovery
* Implemented: explicit `ChapterPipelineState`-style workflow object
* Implemented: structured `WorkflowError` records with typed categories
* Implemented: persisted pipeline run snapshots for later inspection
* Implemented: transition logs and resumable workflow hints in the UI
* Pending: full LangGraph or equivalent workflow runtime adoption
* Pending: first-class branching, retry policy, and resume execution

Workflow:

Plan
↓
Write
↓
Review
↓
Update Memory

Interpretation:

* The project already contains much of the design work that usually comes before LangGraph adoption. What remains is replacing the current manual orchestration with a dedicated workflow runtime when the added complexity becomes worthwhile.

## V4

Multi-Agent Architecture

Agents:

ChiefEditorAgent

PlotAgent

WriterAgent

ReviewAgent

MemoryAgent

ResearchAgent

---

## V5

Evaluation System

Metrics:

* Character consistency
* World consistency
* Timeline consistency
* Writing quality
* Plot progression

---

# Development Rules

1. Do not place complex business logic inside app.py

2. New writing abilities should be added as Skills

3. New prompts belong in prompts.py

4. New persistence logic belongs in memory.py

5. Model changes should happen only in llm.py

6. All generated content should be persistable

6.5. Structured LLM outputs should be defined in `schemas.py` before adding custom parsing logic

7. Maintain backward compatibility with existing project data

8. Chapter planning should use both long-term context and recent progress when available

9. Memory updates should fail closed when structured output validation fails

10. Review results should remain machine-readable before being formatted for human reading

11. Reusable long-term user requirements should be stored as layered rules instead of hardcoded prompt text in the UI

12. Global rules and project rules must remain inspectable and editable from persistent storage

---

# Instructions For Future LLMs

Before modifying the project:

Read files in the following order:

1. project.md

2. app.py

3. skills.py

4. memory.py

5. prompts.py

6. llm.py

When implementing new features:

* Reuse existing architecture
* Avoid breaking storage format
* Keep responsibilities separated
* Preserve project persistence
* Prefer adding Skills over hardcoding logic

This project is intended to evolve into a long-form novel writing platform and an educational Agent Systems project.
