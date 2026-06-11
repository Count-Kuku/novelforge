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

Business logic should remain minimal.

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

Current skill design notes:

* Review results are validated through Pydantic schemas before persistence
* Analysis skills validate JSON through Pydantic schemas, normalize object-shaped list items into strings when needed, then render Markdown reports under the project `analysis/` directory
* Memory updates are validated through Pydantic schemas before being written into project storage
* All LLM-calling functions check for empty responses and raise explicit errors
* `pipeline_plan_write_review_update` executes steps independently — if one fails,
  remaining steps are skipped and partial results are still returned
* Rule injection order is: global common rules -> project common rules -> global scoped rules -> project scoped rules
* Retrieval is task-aware: different generation steps query different source types and scopes

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
* Pending: dedicated external vector database backend
* Pending: reranking and citation-aware response formatting

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
