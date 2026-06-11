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

# Current Version

Version: V1

Current status:

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
* Retrieval document/chunk schema for future RAG workflows
* Searchable project/external knowledge index with scoped retrieval
* Hybrid retrieval with lexical + semantic scoring

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
* Rule injection order is: global common rules -> project common rules -> global scoped rules -> project scoped rules
* Retrieval is task-aware: different generation steps query different source types and scopes
* Retrieval traces are now surfaced to the UI so prompt context provenance can be inspected step by step
* Review and analysis reports now include citation-style supporting source sections for better explainability
* Analysis results now expose both `data.analysis` (structured payload) and `data.report_markdown` (rendered report) to the UI
* Retrieval evidence is grouped by scope and source type to make trust boundaries and source provenance easier to inspect
* External-source trust metadata is now visible and participates in ranking, making authority boundaries explicit during retrieval review
* Potential conflicts are now surfaced when project evidence and external evidence overlap, giving the user an early warning before trusting a generated diagnosis

---

# Current Workflow

Outline Generation

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
* `chapter_outline`
* `chapter`
* `review`
* `review_markdown`
* `memory_update`
* `completed_steps`
* `failed_steps`
* `errors`
* `halted` / `halt_reason`

---

Analysis Result Contract

Consistency, character, timeline, and foreshadowing analysis steps now return structured workflow step objects with:

* `data.analysis` — schema-validated analysis payload
* `data.report_markdown` — persisted Markdown report with supporting sources / conflict notes
* `validation` — analysis schema validation status
* `retrieval_hits` — exact evidence used during the analysis step

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

Files:

* `manifest.json` — project-scoped retrieval documents and chunks
* `vectors.json` — chunk embedding vectors for semantic retrieval
* `sources/` — externally added canon/reference materials

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

# Future Roadmap

## Near-Term Design Improvements

The following design improvements are the most valuable next steps for the current architecture:

1. Stronger chapter planning context

Chapter planning currently combines global outline, memory, and recent chapter summaries — this is already implemented and working.

2. Structured review outputs

Chapter reviews now output structured status fields (pass/revise/blocked) in both Markdown and JSON format. The UI displays status metrics and issue/strength counts.

3. Safer memory updates

Memory update logic validates LLM JSON output strictly and rejects malformed updates. Validation covers field types and array element types.

4. Pipeline automation

The UI now supports a one-click pipeline (Plan → Write → Review → Update Memory) with per-step error isolation. If a step fails, partial results from earlier steps are preserved and displayed.

5. Better model abstraction

The LLM layer remains OpenAI-compatible while supporting configuration-based switching. Per-call temperature and system message are now available.

6. Layered rule management

The UI now supports persistent writing rules at both global and project scope. Rules can be saved by capability and are automatically injected into matching prompts.

7. Schema-first output validation

Core LLM outputs now flow through a dedicated Pydantic schema layer. This reduces ad-hoc parsing logic and prepares the project for typed retrieval, workflow state, and evaluation pipelines.

8. Retrieval-ready knowledge layer

The project now includes a retrieval document/chunk layer, external source ingestion, scoped context retrieval, and semantic vector storage. The system is designed so retrieval backends can evolve without changing prompt/business contracts.

9. Hybrid retrieval

The retrieval layer now combines lexical scoring and embedding similarity. This improves recall for canon/reference materials whose wording may differ from the current draft while preserving precise keyword matches for project-specific facts.

10. Retrieval observability

The system now records and exposes the actual retrieval hits used by major generation steps. This makes RAG behavior inspectable, easier to debug, and much easier to learn from during prompt and retrieval tuning.

11. Citation-aware retrieval outputs

The system now attaches a compact supporting-sources section to review and analysis outputs. This is an explainability layer built on top of retrieval traces and makes it easier to understand why the system reached a specific diagnostic conclusion.

12. Source hierarchy awareness

Retrieval evidence is now grouped by `project`, `canon`, and `reference` scope before presentation. This makes it easier to reason about which conclusions are grounded in current project truth versus original-canon material or lower-priority reference notes.

13. Authority-aware retrieval

The retrieval layer now accepts source authority metadata such as `official`, `curated`, `community`, and `unknown`. Authority participates in retrieval weighting and is surfaced in evidence views so higher-trust sources can be distinguished from lower-trust references.

14. Conflict-aware retrieval

The system now derives lightweight potential-conflict warnings from retrieval hits. When project evidence overlaps on the same retrieval terms with canon or reference evidence, the output can surface this as a possible tension rather than silently blending all sources together.

15. Structured conflict schema and reranking

Potential conflicts are now represented as structured objects with severity and rationale fields. Retrieval results also pass through a lightweight reranking phase that rewards stronger semantic alignment, trusted authorities, and project-grounded evidence before final context selection.

---

## V1.1

Persistence improvements

Features:

* Auto-save generated outlines
* Auto-save generated chapter outlines
* Save and load chapter outlines
* Save and load chapters
* Save and load reviews
* Better memory updates
* Use outline and recent summaries during chapter planning

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
* Implemented: retrieval document/chunk/index manifest schemas
* Implemented: project/external source ingestion into retrieval storage
* Implemented: lexical scoped retrieval with prompt injection across major skills
* Implemented: in-app retrieval center for index rebuild, source management, and retrieval preview
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
* Implemented: unified workflow step result contract for outline / chapter outline / writing / review / memory update / pipeline
* Implemented: unified workflow step result contract for consistency / character / timeline / foreshadowing analysis

---

## V2

RAG Integration

Features:

* Embeddings
* Vector database
* Semantic retrieval
* Context selection

Current implementation status:

* Implemented: project-scoped embedding generation via `llm.py`
* Implemented: semantic vector persistence in `retrieval/vectors.json`
* Implemented: hybrid retrieval over lexical and semantic scores
* Implemented: source-aware chunking and typed external source ingestion
* Implemented: retrieval hit observability across major workflow steps
* Implemented: citation-style supporting sources for review and analysis outputs
* Implemented: grouped source hierarchy display across retrieval evidence views
* Implemented: authority-aware trust model for external-source ranking and inspection
* Implemented: lightweight project-vs-external conflict detection in retrieval evidence
* Implemented: conflict schema with severity/rationale and reranked final retrieval ordering
* Pending: dedicated external vector database backend
* Pending: deeper fact-level conflict resolution and recommendation logic

Possible technologies:

* Chroma
* SQLite + embeddings
* FAISS

---

## V3

LangGraph Workflow

Features:

* State management
* Workflow execution
* Automatic chapter pipeline

Current design direction:

* State-first workflow design before framework adoption
* Explicit `ChapterPipelineState` schema for graph-ready node transitions
* Structured `WorkflowError` records for future retries, branching, and resume behavior

Workflow:

Plan
↓
Write
↓
Review
↓
Update Memory

---

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
