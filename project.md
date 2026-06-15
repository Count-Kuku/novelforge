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
* `V5` evaluation system: initial chapter-level foundation implemented

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
* Clear UI separation between project resources, core story state, source ingestion, and retrieval testing/debugging
* Hybrid retrieval with lexical + semantic scoring
* Retrieval evidence grouping, authority weighting, conflict warnings, and reranking
* Structured pasted-reference organization and single-page URL reference ingestion for canon/reference knowledge
* Project-level creative profile for task nature, target length, workflow depth, and reference strength, with custom values supported
* First dynamic generation entry that can execute direct prose, short-form structure + prose, or chapter-plan + prose based on the creative profile
* Structured knowledge extraction from source material into characters, items, abilities, world rules, events, relationships, style, and constraints
* Confirmed structured knowledge persisted under project `knowledge/` storage and indexed for retrieval
* Discussion-first planning support for full-story outline and chapter direction before formal generation
* Approval-based planning artifacts for outline / volume / arc / chapter discussions
* Persisted chapter pipeline state snapshots, transition logs, and resumable workflow hints
* Story-state oriented memory fields for canon mode, AU rules, relationships, and active constraints
* Multi-turn planning discussion UI with continuously updated discussion conclusions
* Project management workspace with project overview, rename/delete, and resource CRUD
* IDE-style resource browser for outlines, chapters, reviews, analysis reports, run snapshots, and external sources
* Hierarchical outline support with project outline + volume outlines + arc outlines + chapter assignment to volume / arc
* Lightweight chapter-writing guidance controls for tone, pacing, dialogue density, focus, ending strength, and extra requirements
* In-app LLM configuration with multi-profile endpoint / key management and active-profile switching
* Local launcher and portable-build scripts for desktop-style localhost packaging
* Resumable chapter pipeline runs from persisted workflow snapshots
* Arc-level chapter allocation planning with persisted structured plans
* Retrieval debug preview with query terms, filters, candidate counts, and rerank inspection
* Persisted retrieval conflict resolutions for project-vs-canon/reference decisions
* Chapter-level evaluation reports with structured scoring and saved Markdown/JSON artifacts

In short: the project already has a working V1 product, substantial V2 groundwork and implementation, and meaningful V3 preparation.

Recent direction update:

* NovelForge is now moving toward configurable fan-fiction generation rather than one fixed long-form pipeline.
* The first implementation step is a creative profile, a lightweight dynamic generation entry, and structured knowledge ingestion.
* True multi-agent ingestion is still deferred; the current implementation uses a modular extractor workflow that can later be wrapped as specialist agents.

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

├── README.md

├── project.md

├── launcher.py

├── build_release.ps1

```
├── llm_profiles.json

├── global_rules.json

└── projects/

    └── {project_name}/

        ├── memory.json

        ├── rules.json

        ├── outline.md

        ├── volumes/

        ├── arcs/

        ├── chapter_outlines/

        ├── chapters/

        ├── reviews/

        ├── analysis/

        ├── evaluation/

        └── retrieval/

            ├── manifest.json

            ├── vectors.json

            └── sources/

        Note:

        * `outline.discussion.json` stores approved full-story discussion artifacts when available
        * `volumes/volume_xxx.md` stores per-volume outline content
        * `volumes/volume_xxx.meta.json` stores per-volume metadata such as title / summary / status
        * `volumes/volume_xxx.discussion.json` stores approved per-volume discussion artifacts when available
        * `arcs/arc_xxx.md` stores per-arc outline content
        * `arcs/arc_xxx.meta.json` stores per-arc metadata such as `volume_no`, title, summary, status, and planning estimates
        * `arcs/arc_xxx.discussion.json` stores approved per-arc discussion artifacts when available
        * `arcs/arc_xxx.chapter_plan.json` stores arc-level chapter allocation plans when available
        * `chapter_outlines/chapter_xxx.meta.json` stores lightweight chapter outline metadata such as `volume_no` and `arc_no`
        * `chapter_outlines/chapter_xxx.discussion.json` stores approved chapter-planning discussion artifacts when available
        * `evaluation/chapter_xxx.md` and `evaluation/chapter_xxx.json` store chapter-level evaluation reports and structured scores
        * `retrieval/conflict_resolutions.json` stores user-approved retrieval conflict decisions
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
* Managing source ingestion, retrieval sources, index rebuilds, and retrieval preview
* Exposing retrieval mode and score breakdown for debugging/learning
* Organizing pasted reference text and URL pages into structured retrieval-ready entries before ingestion
* Discussing outline and chapter direction in structured form before committing to formal generation steps
* Listing and deleting imported external source files from the retrieval center, with automatic index rebuild after removal
* Separating project resource browsing, core story state editing, source ingestion, and retrieval testing into distinct UI pages
* Providing a project overview page with project-level statistics, rename, and delete operations
* Managing project resources through an IDE-style browser with unified preview/edit/save/delete behavior
* Supporting direct CRUD for outlines, chapter files, review artifacts, analysis artifacts, run snapshots, and external sources from the UI
* Supporting batch cleanup for chapter bundles, run snapshots, and external sources
* Managing volume outlines, arc outlines, and assigning chapter outlines to parent volume / arc nodes
* Managing approval / clearing of persisted planning discussion artifacts for outline, volume, arc, and chapter layers
* Managing multiple saved LLM endpoint / API-key profiles and syncing the active profile back into `.env`
* Managing arc-level chapter allocation plans, chapter evaluation reports, retrieval debug output, conflict resolutions, and resumable pipeline actions

UI features:

* Core story state editing via structured form (title, genre, world, characters, etc.)
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
* Resource browser with left-side file navigation, right-side editor/detail panel, and lightweight volume / arc filtering
* Dedicated volume outline page for editing per-volume title / summary / status / outline body
* Dedicated arc outline page for editing per-arc parent volume, title, summary, status, estimated chapter count, target word count range, outline body, and linked chapter visibility
* Chapter discussion and chapter-outline generation now both consume the currently selected volume / arc planning context so discussion and formal generation stay aligned
* Planning pages can now approve and clear persisted discussion artifacts, and chapter-outline generation can optionally require approved chapter / volume / arc planning discussions
* Chapter writing page now includes lightweight writing-guidance controls instead of a heavier second discussion layer
* Dedicated model configuration page for saving multiple endpoint/key/model profiles and switching the active runtime profile from the UI

Business logic should remain minimal.

Current UI design note:

* `app.py` now includes lightweight reusable render helpers so pages consume `WorkflowStepResult` objects consistently instead of hand-formatting each skill result independently

---

## launcher.py

Local desktop-style launcher.

Responsibilities:

* Resolve the bundled Python runtime from `.venv`
* Start the Streamlit app on local host
* Wait for the local server to become reachable
* Open the browser automatically for local packaged usage
* Reuse an already-running localhost instance only when it is confirmed to be NovelForge
* Fall back across a small local port range when the default port is unavailable
* Write launcher diagnostics to `launcher.log` and surface blocking startup errors to the user

Design purpose:

* Provide a release-friendly local entrypoint so end users do not need to manually open a terminal and run `streamlit run app.py`

---

## build_release.ps1

Windows portable build script.

Responsibilities:

* Install `pyinstaller` into the local `.venv`
* Build `NovelForge.exe` from `launcher.py`
* Assemble a portable release directory
* Copy the runtime, source files, and baseline data structure into the release bundle
* Copy optional `.streamlit` runtime configuration when present
* Save a build transcript under `release/` for local diagnostics
* Produce a zip archive suitable for GitHub Releases

Design purpose:

* Provide a repeatable local packaging flow before any future installer or remote deployment work

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
* Read active model settings from profile-backed persistent configuration

Current model:

* DeepSeek Chat

Current configuration:

* `LLM_API_KEY` or `DEEPSEEK_API_KEY`
* `LLM_BASE_URL` (optional)
* `LLM_MODEL` (optional)
* `LLM_EMBEDDING_MODEL` (optional)

Current configuration note:

* The active runtime configuration is still mirrored into `.env` for compatibility, but the app can now manage multiple saved profiles through `data/llm_profiles.json` and switch the active one from the UI

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
* Loading saved LLM configuration profiles
* Saving saved LLM configuration profiles
* Switching the active LLM configuration profile and syncing it back into `.env`
* Loading outlines
* Saving outlines
* Loading volume outlines
* Saving volume outlines
* Loading volume metadata
* Saving volume metadata
* Loading persisted full-story discussion artifacts
* Saving persisted full-story discussion artifacts
* Loading persisted volume discussion artifacts
* Saving persisted volume discussion artifacts
* Loading arc outlines
* Saving arc outlines
* Loading arc metadata
* Saving arc metadata
* Loading persisted arc discussion artifacts
* Saving persisted arc discussion artifacts
* Loading arc chapter allocation plans
* Saving arc chapter allocation plans
* Loading chapter outlines
* Saving chapter outlines
* Loading chapter-outline metadata such as volume / arc assignment
* Saving chapter-outline metadata such as volume / arc assignment
* Loading persisted chapter discussion artifacts
* Saving persisted chapter discussion artifacts
* Keeping downstream chapter metadata consistent when parent volume / arc planning nodes are deleted
* Loading chapters
* Saving chapters
* Loading reviews
* Saving reviews
* Loading analysis reports
* Saving analysis reports
* Loading chapter evaluation reports
* Saving chapter evaluation reports
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
* Define structured discussion result models for outline-level, volume-level, arc-level, and chapter-level planning conversations
* Define structured metadata models for volume outlines, arc outlines, and chapter assignment to parent planning nodes
* Define structured writing-guidance model for lightweight chapter execution control
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
* Convert volume outlines, arc outlines, and chapter planning assignments into searchable retrieval documents / metadata
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
* Project volume outlines and arc outlines are now indexed as first-class retrieval documents so chapter planning can use story-level, volume-level, and arc-level context together
* Approved outline / volume / arc / chapter discussion artifacts are now indexed as first-class retrieval documents so planning approvals remain visible to retrieval-aware workflows
* Planning metadata saves now trigger retrieval asset refresh so hierarchy changes stay visible to later retrieval-augmented planning steps
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
* Volume-aware and arc-aware chapter outline prompts
* Chapter writing prompts (supports configurable word count)
* Chapter review prompts
* Character analysis prompts
* Timeline analysis prompts
* Foreshadowing analysis prompts
* Consistency check prompts
* Memory update prompts
* Memory compaction prompts
* Reference organization prompts for pasted text and fetched pages
* Discussion prompts for outline-level, volume-level, arc-level, and chapter-level planning
* Formatting layered rule blocks for prompt injection
* Merging retrieved context into generation prompts
* Injecting current volume outline and arc outline context into chapter-planning prompts when available
* Injecting approved planning-discussion artifacts into outline, volume, arc, and chapter generation prompts when available

Current prompt design notes:

* Chapter review prompt requests strict JSON for later workflow automation
* Analysis prompts request strict JSON, then the schema layer renders validated results into Markdown
* Memory update prompt requests strict JSON for safer persistence
* Chapter writing prompt accepts `word_count` parameter (default 2000-2500)
* Memory compaction prompt compresses old character/world/timeline/foreshadowing entries to control prompt length
* All major generation prompts can receive layered rule text assembled from global and project storage
* Retrieved context is appended after the base prompt so retrieval remains a composable layer
* Chapter writing prompt now accepts lightweight writing-guidance controls for style and execution emphasis

Prompt engineering should be isolated here.

---

## skills.py

Skill execution layer.

Responsibilities:

* Generate outline
* Generate chapter outline
* Generate chapter outline with optional parent-volume and parent-arc context
* Write chapter (with configurable word count)
* Review chapter
* Update memory
* Compact memory (compress old entries to control prompt length)
* Merge layered rules into prompts before LLM calls
* Save user requirements into global or project rule storage
* Approve and clear persisted planning discussion artifacts for outline, volume, arc, and chapter levels
* Consistency check
* Character analysis
* Timeline analysis
* Foreshadowing analysis
* Retrieve relevant internal/external context before major LLM calls
* Persist lightweight chapter-to-volume / arc assignment metadata alongside chapter outlines
* Keep chapter discussion context aligned with the currently selected parent volume / arc planning nodes
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
* Approved planning discussions can now be persisted as reusable artifacts and fed back into later generation steps or approval gates
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

Relevant Volume Outline (optional)

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
* `parent_run_id` for resumed runs
* `started_at` / `finished_at`
* `halted` / `halt_reason`
* `resumable`

Current observability note:

* The pipeline UI now shows transition logs, typed workflow errors, and resumable hints derived from persisted chapter run state
* Resumable failed runs can be continued from the last successful step, producing a new child run instead of overwriting the original run snapshot

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
* volume direction
* arc direction
* chapter direction

These discussion steps return workflow step objects with:

* `data.discussion` — schema-validated discussion payload
* `data.report_markdown` — human-readable planning discussion report
* options with strengths / risks
* open questions and recommended direction
* `approval_ready` — whether the current discussion is ready to move into formal generation

When the user explicitly approves a planning discussion from the UI, the discussion can also be persisted as a reusable artifact under project storage so later generation steps can consume the approved direction rather than relying only on transient session state.

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

creative_profile.json

Stores project-level creative intent and generation preferences:

* task nature
* target length / word count
* workflow depth
* reference strength
* reference focus
* canon-deviation and conflict policy

outline.md

Stores the global story outline.

outline.discussion.json

Stores approved full-story planning discussion artifact when available.

chapter_outlines/

Stores chapter plans.

Each chapter outline can also carry lightweight metadata such as parent `volume_no` and `arc_no`.

Each chapter may also carry an approved chapter-discussion artifact used to stabilize later chapter-outline generation.

volumes/

Stores per-volume outlines and metadata used for mid-level story planning.

Per-volume discussion artifacts can also be stored here when the user approves a volume planning discussion.

arcs/

Stores per-arc outlines and metadata used for sequence-level story planning under a volume.

Per-arc discussion artifacts can also be stored here when the user approves an arc planning discussion.

Arc chapter allocation plans can also be stored here as `arc_xxx.chapter_plan.json` when generated.

chapters/

Stores chapter content.

reviews/

Stores review results.

analysis/

Stores consistency, character, timeline, and foreshadowing analysis reports.

evaluation/

Stores chapter quality evaluation reports and structured score JSON files.

knowledge/

Stores confirmed structured knowledge extracted from source material. Current category files include:

* `characters.json`
* `items.json`
* `abilities.json`
* `world_rules.json`
* `locations.json`
* `organizations.json`
* `timeline_events.json`
* `relationships.json`
* `writing_style.json`
* `dialogue_style.json`
* `narrative_techniques.json`
* `constraints.json`

retrieval/

Stores retrieval index artifacts and external knowledge sources.
Also stores persisted conflict decisions in `conflict_resolutions.json`.

runs/

Stores persisted chapter pipeline run snapshots for history inspection and future resume/replay flows.

Files:

* `manifest.json` — project-scoped retrieval documents and chunks
* `vectors.json` — chunk embedding vectors for semantic retrieval
* `sources/` — externally added canon/reference materials
* `knowledge/` records are indexed as project/canon/reference retrieval documents according to their saved scope
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

Current retrieval works with embeddings, hybrid scoring, reranking, observability, structured ingestion, debug inspection, and persisted conflict resolutions. The next step is moving beyond file-based vector persistence toward a dedicated vector backend and stronger fact-level conflict recommendation logic.

2. Finish workflow runtime adoption

The project already has explicit workflow state, structured step contracts, persisted run snapshots, transition logs, and a first resumable-run implementation. The next step is to map this into a graph/runtime layer with first-class branching, retry policy, and richer resume behavior.

3. Strengthen planning and approval loops

Structured outline, volume, arc, and chapter discussions are already implemented. The next step is making these approval checkpoints stricter where appropriate and improving how approved artifacts propagate into downstream execution and evaluation.

This now also includes continuing the new hierarchy work from story outline into volume-level planning and arc-level planning, then later into chapter-allocation and word-budget planning.

4. Prepare for evaluation

Structured outputs, retrieval traces, workflow state, and chapter-level evaluation reports now make evaluation feasible. The next step is defining stable cross-run metrics and artifact collection so future automated evaluation can measure quality over time.

5. Prepare local desktop-style packaging

The app now has in-UI model profile management, which reduces manual setup friction. The next step is packaging the Streamlit workspace into a local-launchable Windows distribution so users can start the localhost app without opening a terminal.

Current implementation status:

* Implemented: `launcher.py` local browser-launching entrypoint for packaged localhost usage
* Implemented: `build_release.ps1` portable Windows build script using `PyInstaller`
* Pending: installer-grade packaging flow
* Pending: update flow for portable desktop releases

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
* Implemented: volume discussion and arc discussion before formal mid-level planning generation
* Implemented: approval and clearing workflow for persisted outline / volume / arc / chapter discussion artifacts
* Implemented: chapter-outline approval gate option requiring approved chapter / volume / arc discussions before generation
* Implemented: lightweight chapter-writing guidance controls for tone / pacing / dialogue density / focus / ending strength / extra requirements
* Implemented: project overview page and project rename/delete controls
* Implemented: project resource CRUD for outlines, chapters, reviews, analysis reports, run snapshots, and external sources
* Implemented: IDE-style resource browser with unified edit/save/delete flows and batch cleanup controls
* Implemented: project-level volume outline storage, editing UI, and chapter-to-volume assignment metadata
* Implemented: project-level arc outline storage, editing UI, and chapter-to-arc assignment metadata
* Implemented: in-app LLM endpoint / API-key profile management with active-profile switching and `.env` sync

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
* Implemented: in-app source ingestion page for importing and structuring external material
* Implemented: in-app retrieval center for index rebuild, source management, retrieval preview, debug inspection, and conflict handling
* Implemented: project-scoped embedding generation via `llm.py`
* Implemented: embedding-backed `vectors.json` storage for semantic retrieval
* Implemented: lexical / semantic / hybrid retrieval modes with score breakdown in UI
* Implemented: source-aware smart chunking for structured records, Markdown sections, and long prose
* Implemented: typed external source templates for better RAG ingestion quality
* Implemented: per-step retrieval trace display in generation, review, analysis, and pipeline result views
* Implemented: volume-outline and arc-outline retrieval indexing and prompt injection for chapter planning
* Implemented: retrieval indexing for approved outline / volume / arc / chapter discussion artifacts
* Implemented: supporting source sections in review and analysis outputs
* Implemented: scope-aware grouped evidence display for retrieval traces and supporting sources
* Implemented: authority-aware metadata capture, ranking, and evidence display for external sources
* Implemented: conflict-aware warnings in retrieval evidence views and diagnostic outputs
* Implemented: structured conflict objects with severity and rationale
* Implemented: lightweight retrieval reranking after initial lexical/semantic scoring
* Implemented: retrieval debug preview for query terms, filters, candidates, and reranked hits
* Implemented: persisted conflict resolutions for recurring evidence disagreements
* Implemented: pasted reference organization into structured retrieval-ready entries
* Implemented: single-page URL fetch and organization for controlled canon/reference ingestion
* Implemented: structured knowledge extraction from pasted material into typed categories
* Implemented: human-confirmed knowledge persistence under project `knowledge/`
* Implemented: retrieval indexing for confirmed structured knowledge
* Pending: dedicated external vector database backend
* Pending: deeper fact-level conflict recommendation logic

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
* Implemented: project-level creative profile for task nature, target length, workflow depth, and reference strength, including custom values
* Implemented: first dynamic generation page for direct prose, short-form structure + prose, and chapter-plan + prose tasks
* Implemented: per-step error isolation with partial result recovery
* Implemented: explicit `ChapterPipelineState`-style workflow object
* Implemented: structured `WorkflowError` records with typed categories
* Implemented: persisted pipeline run snapshots for later inspection
* Implemented: transition logs and resumable workflow hints in the UI
* Implemented: resumable failed chapter runs from the last successful step
* Pending: full LangGraph or equivalent workflow runtime adoption
* Pending: full long-form dynamic orchestration that can automatically branch across outline, volume, arc, chapter plan, writing, review, and memory update
* Pending: first-class branching, retry policy, and richer resume execution

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

Current implementation note:

* True multi-agent orchestration is not implemented yet.
* The structured knowledge extractor is the first practical pre-agent step: it separates source ingestion into typed knowledge categories that can later become specialist extraction agents.
* Planned specialist ingestion agents include character, item/ability, world, timeline/event, style, and audit agents.

---

## V5

Evaluation System

Status:

* Initial foundation implemented

Current implementation status:

* Implemented: chapter-level quality evaluation prompt
* Implemented: schema-validated evaluation score payload
* Implemented: persisted evaluation Markdown and JSON artifacts
* Implemented: evaluation reports in project overview, file preview, and resource management

Pending:

* Cross-run metric tracking
* Version comparison for regenerated chapters
* Automated evaluation suites for model/prompt changes

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
