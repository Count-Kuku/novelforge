# NovelForge

This document is the architecture and implementation reference for NovelForge. It records module boundaries, storage layout, current implementation status, and roadmap notes.

For user-facing feature introductions, setup steps, and workflow guidance, see `README.md`.

For the planned SQLite-first long-term storage architecture, see `storage_architecture.md`.

Current release marker: `v0.5.1`

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
* Setting extraction
* DeepSeek API integration
* Configurable OpenAI-compatible model endpoint
* Structured review status output
* Safer setting-extraction validation
* Streamlit UI
* Modular `ui/` page/component package with `app.py` reduced to a lightweight router and compatibility shell
* Streaming preview controls for major discussion, generation, writing, evaluation, and source-ingestion actions
* Configurable temperature and system message for LLM calls
* Form-based core-setting editing backed by structured knowledge
* Configurable target word count per chapter
* Core-setting knowledge consolidation for long-running projects
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
* Structured pasted-reference organization for canon/reference knowledge; single-page URL ingestion remains implemented but is temporarily hidden from the UI
* Source ingestion ledger for summarizing long-form batches, imported retrieval sources, knowledge-only sources, and processing status
* Long-form source importer for splitting uploaded/pasted novel text by chapter title or length before batch indexing, with strict-canon, fanfic-foundation, and style-reference initialization presets plus UI guidance that separates preview splitting, batch saving, retrieval indexing, and structured knowledge extraction
* One-click long-form source processing for saving batches, indexing source text, extracting structured knowledge, auto-confirming low-risk items, and leaving conflicts or weak-evidence items in the review queue, with visible progress and automatic page-state refresh after completion
* Automatic review run records for low-risk auto-confirm decisions, including decision reasons, pending snapshots, confirmed write targets, and run-level rollback
* Project-level automatic review policy for confidence/evidence thresholds, grade-B handling, and manual-review categories
* Pending-queue automatic-review preview for showing which filtered or selected items would be auto-confirmed before actually saving them
* Pending-queue batch processing plan with low-risk auto-save, low-quality archive, conflict/duplicate manual review box, run-level rollback, and manual-review snapshot restore back into the pending queue
* Long-form source batch manager for whole-txt processing progress, continue actions, failed extraction retries, and completed-segment re-extraction
* Batch processing progress bars for long-form extraction, retry, re-extraction, multi-specialist extraction plans, and source auto-processing
* Long-form source fingerprinting to detect repeated whole-txt uploads and bind them to existing batches
* Story-level creative profile for task nature, target length, workflow depth, and reference strength, with custom values supported
* Consolidated creative profile page for direct profile editing, discussion-assisted recommendations, one-click apply-to-form, and saved-conclusion persistence
* Lightweight quick-generation playground supporting prompt-only or fully-configured execution for testing and experimentation
* Profile-aware content generation page replacing standalone chapter-writing and pipeline pages; adapts between chapter mode and free-form mode based on creative profile, with inline review and setting-extraction chaining
* Content generation chained pipeline: write → review → setting extraction, plus reset-based full pipeline from requirement
* Structured knowledge extraction from source material into characters, items, abilities, world rules, events, relationships, style, and constraints
* Deep source extraction modes for fan-fiction groundwork: general, deep, characters, relationships, timeline, world, style, strict canon, and fanfic reference
* Specialist extraction presets for balanced, character, relationship, timeline, worldbuilding, style, canon-audit, and fanfic-research passes
* Extraction category default strategies for starting from specialist presets, all categories, or no preselected categories
* Advanced custom extraction instructions for users who want to steer specialist extraction without replacing the structured output contract
* Multi-specialist extraction plans for long-form batches, including fanfic foundation, character/relationship, world/timeline, style reference, and strict-canon audit pipelines
* Pasted source extraction can use the same extraction modes as long-form batches
* Knowledge extraction quality metadata: importance, evidence strength, canon status, extraction mode, and source segment trace fields
* Extraction coverage reporting for category coverage, missing/weak categories, quality risk, mode distribution, canon-status distribution, and segment progress
* Re-extraction comparison summaries against existing pending knowledge for the same source segment
* Pending extraction quality checks for same-name duplicates, field conflicts, fact-level conflicts with resolution suggestions, alias candidates, and overlap with confirmed knowledge
* Pending review workspace with category/source/keyword/risk filters and risk/evidence/confidence/importance/recency sorting
* Pending knowledge form editing for correcting extracted items before confirmation without raw JSON editing
* Confirmed knowledge form editing for maintaining persisted project knowledge without raw JSON editing
* Version/worldline metadata on structured knowledge for canon, project-main, AU, branch, and mixed scopes
* Ingestion health overview for imported-but-unextracted material, failed extraction, quality risks, category gaps, entity-card counts, plan-template counts, and worldline distribution
* Project-level extraction plan templates for reusable multi-specialist extraction workflows, including save/delete/raw JSON maintenance
* Entity alias library for turning alias-candidate hints into reusable canonical-name/alias groups that also guide later extraction
* Batch-level extracted-knowledge consolidation for merging scattered pending items into stable character cards, relationship records, timeline facts, style notes, and setting constraints, with five consolidation modes (balanced, character_cards, timeline, strict_canon, style)
* Character entity cards generated from confirmed structured knowledge and indexed as first-class retrieval documents
* Setting entity cards generated from confirmed setting knowledge and indexed as first-class retrieval documents
* Entity alias groups indexed as first-class retrieval documents, used during character-card aggregation, and injected into extraction prompts
* Confirmed structured knowledge persisted under project `knowledge/` storage and indexed for retrieval
* Pending structured-knowledge review queue before extracted items become official project knowledge
* Structured-knowledge organizer for duplicate detection, manual merge, deletion, and raw category editing
* Source package report generated from confirmed structured knowledge and indexed for retrieval
* Discussion-first planning support for full-story outline and chapter direction before formal generation
* Persisted planning conclusions for outline / volume / arc / chapter discussions
* Persisted chapter pipeline state snapshots, transition logs, and resumable workflow hints
* Story-state oriented memory fields for canon mode, AU rules, relationships, and active constraints
* Core setting to structured-knowledge conversion: stable story/project settings can be queued as pending knowledge before becoming project-level reusable knowledge
* Multi-turn planning discussion UI with continuously updated discussion conclusions
* Project management workspace with project overview, rename/delete, and resource CRUD
* Project resources workspace for outlines, chapters, reviews, analysis reports, run snapshots, and external sources
* Project overview metrics can focus the project resources workspace on matching resource groups, including chapters, outlines, reports, sources, structured knowledge, pending knowledge, and long-form batches
* Hierarchical outline support with project outline + volume outlines + arc outlines + chapter assignment to volume / arc
* Lightweight chapter-writing guidance controls for tone, pacing, dialogue density, focus, ending strength, and extra requirements
* In-app LLM configuration with multi-profile endpoint / key management and active-profile switching
* Common provider presets (DeepSeek, OpenAI, Qwen, Ollama, SiliconFlow) for quick endpoint/model fill
* Connection testing for model profiles before saving
* Local launcher and portable-build scripts for desktop-style localhost packaging
* Grouped workspace navigation in the sidebar: 工作台 (overview/config/resources), 资料 (ingestion/settings/retrieval center), 规划 (profile-aware planning), 写作 (quick gen, content generation, evaluation)
* Project-aware workspace header and refreshed card-based UI styling for a more desktop-like writing console
* Project overview page upgraded into a quick-action home screen for quick generation, content generation, ingestion, and project resources
* Story spaces support：one project can hold multiple independent stories, each with its own creative profile, memory overrides, outlines, chapters, reviews, evaluations, analysis reports, pipeline runs, and chapter summaries, while sharing project-level base memory, structured knowledge, source materials, rules, and retrieval index
* Automatic migration of existing single-story projects into the default story space on first access, with the active story persisted in `stories/index.json`
* Story management supports editing story display name/description and copying one story's settings into a newly registered story space
* Creative-profile discussion assist for clarifying ambiguous task intent before saving recommended structured project settings
* Resumable chapter pipeline runs from persisted workflow snapshots
* Arc-level chapter allocation planning with persisted structured plans
* Retrieval debug preview with query terms, filters, candidate counts, and rerank inspection
* Retrieval center RAG health inspection for manifest/current-source consistency, vector coverage, stale chunks, source distribution, and scope distribution
* Task-aware retrieval profiles for creative-profile discussion, outline discussion, volume discussion, arc discussion, chapter discussion, outline generation, chapter planning, drafting, and review/evaluation
* Planning discussions now use retrieval context before formal generation, including creative-profile, outline, volume, arc, and chapter discussions
* Chinese phrase retrieval improved through short ngram tokenization and lightweight stop-token filtering
* Entity-alias query expansion so canonical names, aliases, translated names, and short names can recall the same knowledge group
* Worldline-aware retrieval now supports preference weighting and strict filtering from indexed metadata
* Story creative profiles now persist worldline ID/name and retrieval mode so RAG can automatically follow the active story branch
* Retrieval reranking now includes lightweight result diversification to reduce repeated hits from the same document or source type
* Retrieval reranking now uses saved user feedback to boost useful/priority hits and demote irrelevant/wrong hits
* RAG evaluation workbench for fixed recall test cases, expected terms/chunks/source types, persisted run history, and pass-rate tracking
* Prompt retrieval context now starts with a compact retrieval briefing before detailed evidence chunks
* Generation pages now show a source-usage report summarizing retrieved source distribution, priority references, hard constraints, and conflict resolutions
* Explainable retrieval evidence now carries expanded terms, recall reasons, score breakdowns, and `evidence_meta` into debug views and prompt context
* Persisted retrieval conflict resolutions for project-vs-canon/reference decisions
* Chapter-level evaluation reports with structured scoring and saved Markdown/JSON artifacts
* Story-level rule overrides (rules_overrides.json) with three-level injection: global → project → story
* Unified settings page with tab-based switching between story-level and project-level core settings
* Settings merge engine with conflict detection and per-field resolution for cross-scope copy (story↔project, story↔story)
* Settings copy functions: copy_story_settings, merge_story_to_project_memory, merge_project_to_story_memory, merge_story_rules_to_project, merge_project_rules_to_story
* Full story copy (copy_story) and archive (archive_story) with optional discussion/chapter/summary inclusion
* Creative-profile-driven retrieval: reference_focus and reference_strength now control retrieval source types, top_k, and mode
* Memory field expansion: locations, organizations, power_systems, relationship_graph with retrieval indexing
* Renamed "交互规则" to "生成规则" (generation rules) for clearer intent
* Consolidated creative profile page: removed separate task wizard, discussion auto-fills form values directly

In short: the project already has a working V1 product, substantial V2 groundwork and implementation, and meaningful V3 preparation.

Current direction update:

* NovelForge is now moving toward configurable fan-fiction generation rather than one fixed long-form pipeline.
* This direction is now implemented through story creative profiles, quick generation, profile-aware content generation, source ingestion, multi-specialist extraction plans, automatic review, and RAG evaluation/feedback.
* True autonomous multi-agent orchestration is still deferred; the current ingestion implementation uses modular specialist workflows that can later be wrapped as agents.

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

```text
User
|
Streamlit Entrypoint / Router
(app.py)
|
UI Page and Component Layer
(ui/*)
|
Creative Profile Workflow Layer
(creative_profile_workflows.py)
|
Source Workflow Layer
(source_workflows.py)
|
Resource Browser Data Layer
(resource_browser.py)
|
Knowledge Workflow Layer
(knowledge_workflows.py)
|
Knowledge Quality Layer
(knowledge_quality.py)
|
Knowledge Entity Layer
(knowledge_entities.py)
|
Skill Layer
(skills.py)
|
Prompt Layer
(prompts.py)
|
LLM Interface
(llm.py)
|
OpenAI-compatible API endpoint
|
Memory Layer
(memory.py)
|
Project Storage
|
Prompt Rules
(global + project scoped)
|
Retrieval Layer
(retrieval.py)
```

---

# Directory Structure

```text
novelforge/
|-- app.py
|-- ui/
|   |-- app_shell.py
|   |-- navigation.py
|   |-- layout.py
|   |-- common.py
|   |-- labels.py
|   |-- streaming.py
|   |-- step_views.py
|   |-- discussion.py
|   |-- retrieval_views.py
|   |-- *_page.py
|   `-- resource_browser_state.py
|-- llm.py
|-- memory.py
|-- retrieval.py
|-- merge.py
|-- schemas.py
|-- setting_knowledge.py
|-- prompts.py
|-- prompt_options.py
|-- discussion_assets.py
|-- asset_guardrails.py
|-- skills.py
|-- knowledge_workflows.py
|-- knowledge_quality.py
|-- knowledge_entities.py
|-- source_workflows.py
|-- resource_browser.py
|-- extraction_presets.py
|-- creative_profile_workflows.py
|-- retrieval_eval.py
|-- docs/
|   `-- app_decomposition_plan.md
|-- requirements.txt
|-- .env
|-- .env.example
|-- README.md
|-- README.en.md
|-- project.md
|-- VERSION
|-- launcher.py
|-- NovelForge.spec
|-- build_release.ps1
|-- data/
|   |-- global.db
|   |-- llm_profiles.json
|   |-- global_rules.json
|   |-- prompt_options.json
|   |-- deleted_projects/      # soft-deleted project archives
|   `-- projects/
|       |-- index.json          # UI state / active project metadata; not the project source of truth
|       `-- {project_name}/
        |-- memory.json          # project metadata only (title, genre)
        |-- rules.json           # shared project rules
        |-- prompt_options.json  # shared project prompt option overrides
        |-- knowledge/           # shared structured knowledge
        |   `-- entities/        # generated entity cards such as character profiles
        |-- analysis/            # project-level analysis, e.g. source_package.md
        `-- stories/
            |-- index.json       # story list and active ID
            `-- {story_id}/
                |-- creative_profile.json
                |-- memory_overrides.json
                |-- rules_overrides.json
                |-- prompt_options.json
                |-- outline.md
                |-- volumes/
                |-- arcs/
                |-- chapter_outlines/
                |-- chapters/
                |-- reviews/
                |-- analysis/
                |-- evaluation/
                |-- runs/
                `-- retrieval/
```

---

# File Responsibilities

## app.py

Streamlit entrypoint and page router.

Responsibilities:

* Configure Streamlit page metadata and global styling
* Initialize project and active story state through `ui.app_shell`
* Build the lightweight compatibility context needed by legacy page calls
* Route the selected sidebar page to the corresponding `ui/` page module
* Keep only small compatibility shims such as `render_memory_page()` and `render_retrieval_page()` while page rendering lives outside the entrypoint

Design purpose:

* Keep `app.py` small and predictable so it behaves like an application shell rather than a monolithic UI file
* Prevent page-specific Streamlit state, form handling, and generation/retrieval display logic from accumulating in the entrypoint
* Make new pages discoverable by adding or updating a dedicated `ui/*` module plus a route in `app.py`

Current status after the UI split:

* `app.py` is roughly a routing shell and imports page renderers from `ui/`
* Major page families now live under `ui/`: app shell/navigation, layout, labels, common widgets, step views, discussion helpers, planning pages, creative profile, chapter/content generation, quick generation, evaluation, retrieval center, retrieval ingestion, long-reference import/batch management, knowledge review/organization, settings, resource management, rules, prompt options, and project overview
* Streamlit widget keys were preserved where practical during extraction to avoid avoidable session-state churn
* Non-UI workflow decisions remain in existing workflow/domain modules such as `knowledge_workflows.py`, `knowledge_quality.py`, `knowledge_entities.py`, `source_workflows.py`, `resource_browser.py`, `creative_profile_workflows.py`, `setting_knowledge.py`, and `retrieval_eval.py`

---

## ui/

Streamlit page and component layer.

Responsibilities:

* Own page-level rendering and Streamlit session/widget orchestration
* Provide shared UI helpers for labels, layout, status blocks, retrieval displays, discussion widgets, prompt-option controls, and resource-browser state
* Keep page modules scoped by domain: planning, writing, retrieval, ingestion, settings, rules, prompt options, resources, project overview, and knowledge review
* Delegate persistence, retrieval, extraction, quality checks, and generation workflows to non-UI modules instead of duplicating business rules in page code

Design purpose:

* Keep UI composition modular while preserving the existing Streamlit user flow
* Make individual pages importable and reviewable without loading one giant `app.py`
* Support continued incremental refactoring through the plan in `docs/app_decomposition_plan.md`

Current split highlights:

* `ui.app_shell` owns project initialization, project/story switching, new-project/new-story controls, grouped sidebar navigation, and project summary captions
* `ui.layout`, `ui.common`, `ui.labels`, `ui.step_views`, and `ui.retrieval_views` provide shared display infrastructure
* `ui.outline_page`, `ui.volume_outline_page`, `ui.arc_outline_page`, and `ui.chapter_outline_page` own planning pages
* `ui.creative_profile_page`, `ui.dynamic_generation`, `ui.chapter_page`, and `ui.evaluation` own profile, quick-generation, content-generation, and evaluation surfaces
* `ui.retrieval_ingestion_page`, `ui.retrieval_center_page`, `ui.long_reference_importer`, `ui.long_reference_batch`, `ui.knowledge_management`, and `ui.retrieval_eval_panel` own source/RAG/knowledge-review workspaces
* `ui.resource_management`, `ui.settings_page`, `ui.rules_page`, `ui.prompt_options_page`, and `ui.project_overview` own operational workbench pages

---

## knowledge_workflows.py

Pending structured-knowledge workflow logic.

Responsibilities:

* Normalize confidence/evidence scores used by knowledge review flows
* Summarize evidence snippets for pending knowledge items
* Convert quality issues into user-facing risk labels
* Evaluate automatic-review decisions from item quality, policy, evidence, and quality-issue maps
* Build automatic-review previews for pending-queue UI display
* Save edited pending items and move/delete confirmed knowledge items without UI code manipulating category files directly
* Filter and sort pending-queue indices from UI-selected category/source/worldline/risk/keyword values
* Build pending-queue batch processing plans that route entries into auto-save, archive, or manual-review snapshots
* Execute pending-queue batch processing plans by coordinating confirmed knowledge writes, pending queue removal, processing records, and retrieval index rebuilds

Design purpose:

* Keep non-UI pending-knowledge decision logic out of `app.py`
* Make future tests for auto-review policy, filter/sort behavior, item save/move behavior, clear-plan routing, and rollback/restore behavior easier to add

---

## knowledge_quality.py

Structured-knowledge quality and matching logic.

Responsibilities:

* Normalize entity names and knowledge item match keys
* Merge text/list values used by entity cards, alias groups, and knowledge consolidation
* Detect duplicate pending knowledge, same-name field conflicts, fact-level conflicts, confirmed-knowledge overlap, and alias candidates
* Build pending-issue maps consumed by pending-review filters and auto-review decisions
* Maintain entity alias groups without requiring UI code to manipulate alias storage directly

Design purpose:

* Keep knowledge-quality rules, matching heuristics, and alias-upsert behavior outside `app.py`
* Provide a reusable place for future fact-conflict tests and entity normalization improvements

---

## knowledge_entities.py

Structured-knowledge entity-card aggregation.

Responsibilities:

* Merge confirmed structured knowledge items into stable character and setting entity cards
* Collect related relationship, ability, item, dialogue-style, constraint, and timeline entries for character cards
* Use entity alias groups to connect canonical names, aliases, translated names, and short names during aggregation
* Build setting cards from world rules, locations, organizations, abilities, items, and constraints
* Provide shared merge helpers used by pending-quality merge actions and entity-card generation

Design purpose:

* Keep entity-card construction and related matching rules outside `app.py`
* Make future tests for character-card aggregation, setting-card aggregation, and alias-guided matching easier to add

---

## source_workflows.py

Source ingestion and long-reference processing logic.

Responsibilities:

* Decode uploaded text, split long sources into resumable segments, and detect duplicate batches by content fingerprint
* Summarize long-form batch resume state so UI can explain what remains to import, extract, retry, or review
* Import long-reference segments into retrieval sources without duplicating already imported segments, and preserve the actual saved source path on the segment
* Save organized references and manual source cards with non-overwriting retrieval-source filenames
* Extract structured knowledge from source segments into the pending queue, including evidence-context capture and re-extraction comparison
* Build extraction coverage reports, ingestion health reports, source ledgers, and source package reports
* Run batch automatic processing, multi-expert extraction plans, batch-level consolidation, and low-risk auto-confirm flows

Design purpose:

* Keep source ingestion decisions, batch mutation, and multi-step processing out of `app.py`
* Make interruption/retry behavior testable without loading Streamlit UI state

---

## resource_browser.py

Resource browser data and persistence support.

Responsibilities:

* Build resource-browser item lists for outlines, planning artifacts, chapters, reviews, reports, runs, retrieval sources, structured knowledge, pending knowledge, and long-reference batches
* Save edited browser resources back through the correct persistence function
* Delete supported browser resources and rebuild retrieval assets when needed
* Provide stable browser item identities and read-only JSON payloads for structured resources

Design purpose:

* Keep resource listing and file mutation rules outside the Streamlit detail panel
* Make project overview metric navigation and resource-browser behavior easier to maintain

---

## extraction_presets.py

Source extraction presets.

Responsibilities:

* Define extraction mode labels and user-facing help text
* Define expert extraction presets, multi-step extraction plans, and consolidation mode labels
* Provide default category selection logic shared by source-ingestion UI and source workflow execution

Design purpose:

* Keep extraction presets as reusable configuration instead of duplicating them inside `app.py`
* Make future source-processing presets easy to extend without editing UI rendering code

---

## prompt_options.py

User-editable prompt option engine.

Responsibilities:

* Define built-in prompt option presets for writing style, planning method, review rubric, and setting-extraction policy
* Normalize user-created prompt options into a fixed schema before persistence
* Merge built-in, global, project, and story-level prompt options with deterministic override order
* Filter active options by capability such as `outline`, `chapter_outline`, `write`, `review`, and `setting_extraction`
* Render active prompt options as bounded prompt blocks that cannot replace structured output contracts
* Extract candidate prompt options from approved or in-progress planning discussions, requiring explicit user confirmation before saving them to story storage

Design purpose:

* Keep data/storage formats strict while allowing advanced users to customize selectable generation behavior
* Avoid letting free-form user prompt text override JSON schemas, persistence format, workflow result contracts, or other hard system requirements
* Provide a reusable layer between the existing rule system and task-specific prompt templates

---

## creative_profile_workflows.py

Creative-profile configuration rules.

Responsibilities:

* Keep story-mode workflow recommendations outside Streamlit page code
* Normalize creative-profile form payloads, including reference-focus presets and custom focus items
* Build creative-profile dictionaries from direct form values and legacy task-wizard inputs
* Preserve shared creative-profile defaults such as custom-option labels and default worldline values

Design purpose:

* Keep creative-profile configuration decisions outside `app.py`
* Make future tests for profile defaults, recommendation paths, and form payload normalization possible without loading Streamlit

---

## setting_knowledge.py

Unified core-setting knowledge helpers.

Responsibilities:

* Migrate legacy project/story memory settings into confirmed structured knowledge items
* Keep core-setting item metadata normalized, including scope, story ID, setting role, and injection policy
* Provide editing helpers for core-setting views without duplicating storage rules in `app.py`
* Copy project/story core-setting knowledge items between scopes with stable IDs and duplicate protection
* Build generation-time memory dictionaries from unified setting knowledge while preserving legacy fallback behavior

Design purpose:

* Make structured knowledge the formal storage layer for stable settings
* Keep the core-setting page as a lightweight view over knowledge items instead of a parallel storage path

---

## discussion_assets.py

Discussion-to-asset candidate builder.

Responsibilities:

* Convert structured discussion results into confirmable core-setting candidates
* Convert discussion constraints and risks into story-level rule candidates
* Reuse prompt-option candidate generation so discussion pages can expose all reusable assets together
* Keep candidate generation deterministic and side-effect free; UI code applies candidates only after user confirmation

Design purpose:

* Let discussions become durable project assets without allowing free-form conversation to bypass storage schemas or structured output contracts
* Keep discussion asset extraction separate from Streamlit rendering and persistence functions

---

## asset_guardrails.py

Reusable candidate safety checks for discussion-derived assets.

Responsibilities:

* Normalize text for duplicate and near-duplicate checks across settings, prompt options, and rules
* Compare discussion-derived candidates with existing project/story assets before the UI saves them
* Return side-effect-free warning records so Streamlit can ask the user whether to add, overwrite, or skip

Design purpose:

* Keep confirmation safeguards separate from asset extraction and persistence
* Reduce accidental duplicate Prompt options, repeated rules, and conflicting core settings without blocking deliberate user overrides

---

## retrieval_eval.py

Retrieval evaluation execution logic.

Responsibilities:

* Run fixed retrieval evaluation cases through the active retrieval stack
* Compare hits against expected terms, chunk IDs, source types, and minimum-match thresholds
* Persist evaluation runs with pass/fail summaries and detailed hit payloads
* Build source-usage report data for workflow result panels without coupling report calculations to Streamlit widgets
* Parse multiline/comma-separated evaluation fields and provide retrieval-profile labels shared by evaluation controls

Design purpose:

* Keep RAG evaluation scoring, run persistence, report data construction, and form parsing outside the workbench UI
* Make retrieval quality checks easier to test and evolve independently from page layout

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
* Treat the Streamlit shell as a valid readiness signal after launching the app, because the initial HTML may not contain app-specific text
* Normalize duplicated `Path` / `PATH` environment keys before spawning the Streamlit process on Windows
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
* Copy the runtime, entrypoint, split workflow modules, `ui/` page package, `storage/` package, verification/maintenance tools, development docs, `VERSION`, Chinese/English README files, and baseline data structure into the release bundle
* Copy optional `.streamlit` runtime configuration when present
* Save a build transcript under `release/` for local diagnostics
* Produce a zip archive suitable for GitHub Releases

Design purpose:

* Provide a repeatable local packaging flow before any future installer or remote deployment work

Related packaging note:

* `NovelForge.spec` now provides a checked-in PyInstaller spec for building the desktop-style launcher executable from `launcher.py`

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
* Loading compatibility memory dictionaries for older workflow helpers
* Saving slim project metadata to `memory.json`
* Loading global rules from `global.db` first, with JSON compatibility fallback
* Saving global rules to `global.db` plus JSON compatibility mirror
* Loading project rules
* Saving project rules
* Loading saved LLM configuration profiles
* Saving saved LLM configuration profiles
* Switching the active LLM configuration profile and syncing it back into `.env`
* Loading, creating, renaming, copying, archiving, and deleting story-space metadata
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
* Loading and saving structured knowledge, pending knowledge, auto-review policy, and processing run records
* Upserting pending knowledge by internal `pending_id` so deterministic re-extraction updates existing candidates instead of duplicating same-ID records
* Rolling back processing runs and restoring manual-review snapshots back into the pending queue
* Fetching recent chapter summaries (configurable limit, default 5)
* Counting total written chapters

Current storage note:

* `memory.json` is no longer the primary storage layer for stable settings. It is intentionally slimmed to project metadata such as title and genre.
* Stable settings are managed as structured knowledge through `setting_knowledge.py`, with legacy memory-shaped dictionaries assembled only as compatibility views for prompt builders.
* Structured data is SQLite-first as of schema version 5: project-local data is read from `project.db` first, including stories, story profiles, project/story rules, prompt options, structured knowledge, pending knowledge, aliases, source batches, retrieval source registry, retrieval manifest/chunks/vectors, retrieval feedback/evals, conflict resolutions, workflow run snapshots, project-manager run/inventory listings, RAG rebuild inputs for review/evaluation/discussion payloads, volume/arc/chapter metadata discovery, DB-only deletion for small JSON artifacts, and small JSON artifacts in `asset_payloads`; global data is read from `global.db` first, including LLM profiles, global rules, global prompt options, and global rule conflict resolutions. Schema version 5 adds active asset uniqueness indexes for both project-level and story-level assets. Legacy JSON files are compatibility mirrors and backfill sources.
* Structured JSON compatibility mirrors are disabled by default. Set `NOVELFORGE_WRITE_JSON_MIRRORS=1` before launching the app or tools only when temporary legacy JSON mirror output is needed. SQLite remains authoritative; old JSON can still be read as fallback/backfill until the corresponding structured resource is saved again, at which point that stale mirror is removed. Markdown/TXT long-text assets remain file-backed.
* In the default no-JSON-mirror mode, SQLite is required rather than best-effort: database read/write/delete failures raise errors so structured data is not silently lost.

No LLM logic should exist here.

---

## merge.py

Settings merge engine.

Responsibilities:

* Compare two settings dictionaries and build a merge plan listing per-field conflicts
* Resolve conflicts with per-field granularity (source / target / merged)
* Support scalar and list field types with dedup-aware merge logic

Design purpose:

* Provide a reusable conflict-detection layer for cross-scope settings copy operations (story ↔ project, story ↔ story)
* Keep merge logic separate from UI and persistence layers

Current merge usage:

* `build_merge_plan()` is called from `memory.py` and `app.py` for settings copy/import workflows
* The merge plan is rendered as an interactive preview in the settings UI, allowing per-field resolution before applying
* `merge_story_to_project_memory()` and `merge_project_to_story_memory()` both use `build_merge_plan` for consistent conflict detection, with dedup-aware list merging via `_merge_list_values()`

---

## schemas.py

Pydantic schema layer.

Responsibilities:

* Define machine-readable output contracts for LLM steps
* Define machine-readable output contracts for workflow steps and pipeline state
* Validate review payloads
* Validate setting-extraction payloads
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
* The retrieval center exposes keyword-only rebuild and full index rebuild separately, so projects can keep lexical RAG usable even when embeddings are unavailable
* `inspect_retrieval_health` reports manifest/current-source consistency, vector coverage, stale vector/chunk counts, source-type distribution, scope distribution, semantic availability, active embedding model, and embedding-model mismatch warnings
* `retrieve_context` and `debug_retrieve_context` support task-aware retrieval profiles for discussion, planning, drafting, and review/evaluation workflows
* Chinese lexical retrieval uses short ngrams for continuous CJK text, with lightweight stop-token filtering to reduce generic false positives
* Query planning expands entity aliases from `knowledge/entities/aliases.json` before lexical and semantic retrieval, improving recall for canonical names, aliases, translations, and short names
* A shared internal retrieval runner powers both `retrieve_context` and `debug_retrieve_context`, reducing drift between production retrieval and diagnostics
* Worldline metadata from confirmed knowledge and entity cards participates in retrieval scoring; strict mode keeps global/unlabeled material while excluding explicit mismatched worldlines
* Story creative-profile worldline fields are automatically passed into retrieval-aware discussions, planning, drafting, and review through the shared retrieval context builder
* Retrieval hits include `expanded_terms`, `match_reasons`, and `score_breakdown`; formatted prompt context adds `evidence_meta` with authority, matched terms, and top recall reasons
* Retrieval results are diversified after reranking to reduce repeated hits from the same document or source type
* Retrieval feedback from `retrieval/feedback.json` participates in reranking and records its effect in `score_breakdown.feedback`
* RAG evaluation cases and run history live under `retrieval/eval_cases.json` and `retrieval/eval_runs.json`
* Formatted retrieval context includes a compact briefing for source distribution, priority references, constraints/settings, and conflict resolutions before full chunks
* Retrieval documents are separated from prompt logic so the indexing contract remains reusable
* Scope priority currently prefers `project`, then `canon`, then `reference`
* Retrieval is already injected into outline, chapter planning, writing, review, setting extraction, and analysis steps
* Project volume outlines and arc outlines are now indexed as first-class retrieval documents so chapter planning can use story-level, volume-level, and arc-level context together
* Approved creative-profile / outline / volume / arc / chapter discussion artifacts are now indexed as first-class retrieval documents so configuration and planning approvals remain visible to retrieval-aware workflows
* Story-level content (outlines, chapters, reviews, evaluations, pipeline runs) is now stored under `stories/{story_id}` and indexed separately per story
* Planning metadata saves now trigger retrieval asset refresh so hierarchy changes stay visible to later retrieval-augmented planning steps
* Hybrid mode combines explicit term matches with embedding similarity for more robust retrieval
* Chunking is now source-aware: structured records stay atomic, Markdown-like sources split by section and paragraph, and long prose falls back to overlapping windows
* External materials can be ingested through typed templates such as character sheets, location sheets, canon events, and world rules
* Reference ingestion currently exposes pasted raw text as the controlled UI entry point; single-page URL fetches remain implemented but are hidden behind an internal flag until the workflow is more reliable
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
* Reference organization prompts for pasted text, with fetched-page support retained for the temporarily hidden URL ingestion path
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
* Organize pasted reference material into structured retrieval entries before storage; fetched reference material is retained for the hidden URL ingestion path
* Produce structured discussion results for outline and chapter planning before generation

Current skill design notes:

* Review results are validated through Pydantic schemas before persistence
* Analysis skills validate JSON through Pydantic schemas, normalize object-shaped list items into strings when needed, then render Markdown reports under the project `analysis/` directory
* Analysis skills now return the same workflow step contract as generation/review/setting-extraction steps, including validated structured payloads and persisted Markdown reports
* Setting extraction payloads are validated through Pydantic schemas before being queued for confirmation
* All LLM-calling functions check for empty responses and raise explicit errors
* `pipeline_plan_write_review_update` executes steps independently — if one fails,
  remaining steps are skipped and partial results are still returned
* Key workflow steps now return a common structure containing `success`, `status`, `data`, `error`, `warnings`, `retrieval_hits`, `validation`, and `artifacts`
* The same step-result contract now covers outline generation, chapter planning, chapter writing, chapter review, setting extraction, and the combined pipeline
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

Setting Extraction

Chapter
 +
Retrieved Context
 +
Applicable Rules
↓
extract_setting_candidates_from_chapter
↓
pending knowledge queue + chapter summary

If JSON validation fails:
↓
return rejected result without modifying confirmed knowledge

Validation is performed through `schemas.py`.

The step now returns a structured result object:

* `success` / `status` indicate whether the extraction completed, failed, or was rejected
* `validation` records schema-pass or schema-fail information
* `artifacts.raw_response` preserves the raw model output when rejection happens
* `retrieval_hits` keeps the exact supporting context used during the extraction attempt

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
* `steps.setting_extraction`

Each step uses the shared workflow step schema so the UI can render status, errors, validation state, retrieval evidence, and saved artifacts without special-case parsing.

The pipeline now also returns a chapter workflow state object containing:

* `current_step`
* `next_step`
* `last_successful_step`
* `chapter_outline`
* `chapter`
* `review`
* `review_markdown`
* `setting_extraction`
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

Each novel project owns its own directory. The project directory is the source of truth: the application lists directories under `data/projects/` that contain recognizable project markers such as `stories/`, `memory.json`, `rules.json`, `prompt_options.json`, `retrieval/`, or a non-empty `project.db`. Project names are not filtered by local test or verification naming conventions; if a directory is placed under `data/projects/` and looks like project data, it is shown as a project. `data/projects/index.json` is auxiliary UI state for the active project and compatibility metadata; it must not decide whether a project exists. User-facing project deletion moves the project directory under `data/deleted_projects/` for manual recovery.

Example:

data/projects/fanfic_project/

Files:

memory.json

Stores:

* project title
* project genre

Stable settings, timelines, relationships, and constraints are stored under `knowledge/` as structured knowledge items. Chapter summaries are story-level files under `stories/{story_id}/chapter_summaries.json`.

rules.json

Stores project-scoped prompt rules by capability:

* all
* outline
* chapter_outline
* write
* review
* setting_extraction

creative_profile.json

Stores story-level creative intent and generation preferences:

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

Stores consistency, character, timeline, and foreshadowing analysis reports. Also stores `source_package.md`, a project-level source package report generated from confirmed structured knowledge.

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

`knowledge/pending.json` stores extracted knowledge items waiting for user confirmation. Confirmed items are moved into the category files above and then indexed for retrieval.
Pending knowledge can come from source extraction, batch-level consolidation, or direct conversion from story/project core settings.
`knowledge/auto_review_policy.json` stores project-level automatic review thresholds and manual-review category rules.
`knowledge/auto_review_runs.json` stores automatic review and pending-queue processing runs, including confirmed record targets, archived snapshots, manual-review snapshots, restored snapshot IDs, single-item returns, and rollback status.
The source ingestion ledger is generated from existing storage rather than a separate file: `long_reference_batches/`, `retrieval/sources/`, `knowledge/pending.json`, and confirmed `knowledge/*.json`.

`knowledge/entities/characters.json` stores generated character entity cards built from confirmed character, relationship, ability, dialogue, timeline, and constraint knowledge. These cards are indexed as `entity_character_card` retrieval documents.

`knowledge/entities/aliases.json` stores canonical entity names and aliases. Alias groups are indexed as `entity_alias_group` retrieval documents and are used when generating character entity cards.

Knowledge extraction items may include quality and trace metadata:

* `confidence`: model confidence for the extracted item
* `importance`: long-term writing value for fan-fiction reuse
* `evidence_strength`: strength of textual evidence
* `canon_status`: `canon`, `inferred`, `ambiguous`, `fanon`, `user_override`, or `unknown`
* `extraction_mode`: strategy used for extraction, such as `strict_canon` or `relationships`
* `source_segment_id`, `source_segment_index`, `source_segment_title`: long-form source segment trace fields
* `source_segment_ids`, `source_segment_titles`, `merged_from_pending_ids`: multi-source trace fields produced by batch-level consolidation

long_reference_batches/

Stores whole-source processing batches for uploaded or pasted long-form material. Each batch records segment content, import state, extraction state, queued knowledge count, source metadata, last extraction mode, consolidation-ready pending knowledge links, and retry errors.
Batch metadata also stores source file name, content fingerprint, total character count, and segment count to identify repeated uploads.

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

global.db / global_rules.json

`data/global.db` is the authoritative global structured store. Legacy JSON mirrors such as `data/global_rules.json`, `data/prompt_options.json`, `data/llm_profiles.json`, and `data/global_rule_conflict_resolutions.json` remain as compatibility and backfill files.

---

# Rule Structure

Current rule schema:

{
"all": [],
"outline": [],
"chapter_outline": [],
"write": [],
"review": [],
"setting_extraction": []
}

Usage notes:

* `all` applies to every generation step
* Other fields apply only to their matching capability
* Global rules are loaded from `data/global.db` first, then `data/global_rules.json` as compatibility fallback
* Project rules are loaded from `data/projects/{project_name}/project.db` first, then `data/projects/{project_name}/rules.json` as compatibility fallback

---

# Prompt Option Structure

Prompt options are user-editable prompt fragments with fixed metadata.

Current prompt option schema:

{
"id": "",
"name": "",
"scope": "story",
"capability": "write",
"category": "custom",
"slot": "custom",
"content": "",
"enabled": true,
"built_in": false,
"priority": 50,
"source": "manual",
"source_kind": "",
"source_ref": "",
"tags": [],
"created_at": "",
"updated_at": ""
}

Usage notes:

* Prompt options are stored at three editable levels: `data/prompt_options.json`, `data/projects/{project_name}/prompt_options.json`, and `data/projects/{project_name}/stories/{story_id}/prompt_options.json`
* Built-in options are defined in `prompt_options.py`; they are visible in the UI but disabled by default until copied or explicitly selected
* Merge order is built-in → global → project → story, with later layers overriding earlier entries by `id`
* Active options are injected after layered rules and creative-profile context, but before fixed output-format requirements in the concrete prompt templates
* Discussion pages can derive candidate prompt options from the structured discussion result; candidates only become active after the user saves them
* Prompt options may influence style, planning, review criteria, setting-extraction policy, extraction focus, and similar user-configurable behavior, but must not change storage schemas or structured LLM output contracts

---

# Project Metadata And Setting Storage

Current `memory.json` storage is intentionally small:

{
"title": "",
"genre": ""
}

Compatibility views returned by `load_memory()` / `load_story_memory()` still include legacy fields such as `world`, `characters`, `timeline`, and `active_constraints` so older prompt builders and migration helpers do not break. New stable settings should be written as structured knowledge items through `setting_knowledge.py`.

Structured core settings use a strict scope contract:

* `setting_scope` is normalized to either `project` or `story`
* project settings are shared by every story
* story settings must include `story_id` and are only injected or retrieved for that story
* deleting a story removes its story-scoped setting knowledge from the shared knowledge store
* copying a story copies creative profile, rules, prompt options, approved discussion artifacts, legacy memory overrides, and story-scoped core settings

Story IDs are filesystem and retrieval-key identifiers, not display labels. They are generated as ASCII slugs when possible, and fall back to stable `story_<hash>` IDs for names that do not produce a useful ASCII slug. The UI should continue showing the story `name` to the user.

Story-scoped retrieval documents must include `story_id` in both document IDs and metadata. This includes outlines, volume outlines, arc outlines, chapter plans, chapter outlines, chapter content, approved discussion artifacts, review outputs, analysis outputs, evaluation outputs, and story chapter summaries. `load_retrieval_index()` rebuilds the keyword manifest when it detects an older story-scoped manifest without `story_id`; semantic vectors remain opt-in through the full index rebuild action.

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
* Implemented: reject invalid setting-extraction payloads before queuing
* Implemented: expose structured review status directly in UI controls
* Implemented: configurable word count target per chapter
* Implemented: unified core-setting knowledge management for long-running projects
* Implemented: per-step error isolation in pipeline
* Implemented: form-based core-setting editing backed by structured knowledge
* Implemented: persistent global/project rule storage
* Implemented: in-app rule center and quick requirement capture
* Implemented: chapter-level consistency / character / timeline / foreshadowing analysis
* Implemented: persistent Markdown analysis reports under project storage
* Implemented: review page result refresh fix for Streamlit session state behavior
* Implemented: `schemas.py` Pydantic schema layer for review, setting extraction, and analysis outputs
* Implemented: schema-validated JSON-to-Markdown rendering pipeline for analysis results
* Implemented: unified workflow step result contract for outline / chapter outline / writing / review / setting extraction / pipeline
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
* Implemented: IDE-style project resources workspace with unified edit/save/delete flows and batch cleanup controls
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
* Implemented: keyword-only and full-index rebuild controls in the retrieval center
* Implemented: RAG health panel for index consistency, vector coverage, stale chunks, source distribution, and scope distribution
* Implemented: task-aware retrieval profiles for discussion, outline generation, chapter planning, drafting, and review/evaluation
* Implemented: RAG-backed planning discussions for creative profile, outline, volume, arc, and chapter discussion turns
* Implemented: Chinese phrase ngram tokenization and lightweight stop-token filtering for better lexical recall
* Implemented: alias-aware query expansion and debug display of matched alias groups
* Implemented: shared retrieval execution path for production and debug retrieval
* Implemented: worldline-aware retrieval preference/strict modes and retrieval-center controls
* Implemented: story creative-profile worldline fields and automatic RAG worldline propagation
* Implemented: explainable retrieval hits with expanded terms, recall reasons, score breakdown, and `evidence_meta` prompt injection
* Implemented: embedding-model consistency warnings in RAG health checks
* Implemented: lightweight retrieval result diversification after reranking
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
* Implemented but temporarily hidden in the UI: single-page URL fetch and organization for controlled canon/reference ingestion
* Implemented: long-form source importer with chapter-title splitting, length fallback splitting, guided automatic processing, conservative auto-confirm, guided batch saving, batch source indexing, mode help, extraction category default strategies, custom extraction instructions, and limited batch extraction
* Implemented: automatic review records and rollback for low-risk auto-confirmed extracted knowledge
* Implemented: pending-queue batch processing plan with auto-save/archive/manual-review routing, batch records, rollback, and manual-review snapshot restore
* Implemented: project-level auto-review policy configuration and single confirmed-item return to pending review
* Implemented: long-form source batch manager with progress tracking, visible batch progress bars, continue import/extraction actions, failed extraction retry, completed-segment re-extraction, and completion reruns
* Implemented: repeated-upload detection using long-form source fingerprints and similarity hints
* Implemented: source ingestion ledger with long-form batch, retrieval-source, and knowledge-only provenance summaries
* Implemented: segment-level source inspection from the ledger, including original text and linked pending/confirmed knowledge
* Implemented: structured knowledge extraction from pasted material into typed categories
* Implemented: extraction-mode selection for pasted structured-knowledge extraction
* Implemented: specialist extraction presets that select coherent category groups and extraction modes for common ingestion passes
* Implemented: multi-specialist extraction plans for selected long-form source segments, with plan history stored on the batch and optional post-plan consolidation
* Implemented: extraction coverage report for pending knowledge and long-form batches
* Implemented: re-extraction comparison details for long-form source segments, including added/missing/changed item snapshots
* Implemented: pending extraction quality panel for duplicates, field conflicts, fact-level conflicts with resolution suggestions, alias candidates, confirmed-knowledge overlap, and same-name pending merge
* Implemented: pending review filters and sorting for category, source, keyword, quality risk, evidence strength, confidence, importance, recency, and category/name
* Implemented: pending knowledge form editor with save-to-pending and save-and-confirm actions
* Implemented: confirmed knowledge form editor with save, category move, delete, and retrieval index rebuild actions
* Implemented: version/worldline metadata fields for pending and confirmed structured knowledge
* Implemented: worldline filters for pending review and confirmed-knowledge organization
* Implemented: ingestion health overview for source and extraction quality governance, including entity-card and template counts
* Implemented: extraction plan template save/reuse/delete/raw-edit flow for long-form batch multi-specialist plans
* Implemented: setting entity cards saved under `knowledge/entities/settings.json` and indexed for retrieval
* Implemented: re-extraction diff actions for accepting the new pass or keeping the old pass
* Implemented: evidence paragraph/character-position context capture and form editing for long-form extraction
* Implemented: entity alias library with alias-candidate save action, manual alias-group management, retrieval indexing, character-card alias matching, and extraction prompt alias context
* Implemented: extraction-mode-aware long-form source extraction for general, deep, character, relationship, timeline, world, style, strict-canon, and fanfic-reference passes
* Implemented: extraction quality metadata and source-segment trace fields for pending and confirmed structured knowledge
* Implemented: batch-level pending-knowledge consolidation with balanced, character-card, timeline, strict-canon, and style-focused modes
* Implemented: core setting conversion into pending structured knowledge for project-level reuse and retrieval
* Implemented: character entity cards generated from confirmed structured knowledge and indexed for retrieval
* Implemented: pending structured-knowledge queue with batch confirmation/discard and raw-data editing
* Implemented: human-confirmed knowledge persistence under project `knowledge/`
* Implemented: structured-knowledge organizer with duplicate detection, manual merge, deletion, and raw category editing
* Implemented: retrieval indexing for confirmed structured knowledge
* Implemented: source package report generation from confirmed structured knowledge, saved under `analysis/source_package.md`
* Pending: dedicated external vector database backend
* Pending: richer worldline management UI for defining, listing, and merging project branches

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

* Implemented: one-click chapter pipeline across planning, writing, review, and setting extraction
* Implemented: story-level creative profile for task nature, target length, workflow depth, and reference strength, including custom values
* Implemented: consolidated creative profile page that maps plain Chinese discussion and direct form choices into the current story creative profile
* Implemented: quick-generation playground for direct prose, short-form structure + prose, and chapter-plan + prose tasks
* Implemented: modular Streamlit UI split under `ui/`, with `app.py` reduced to route setup and compatibility helpers
* Implemented: streaming preview controls for major discussion, generation, writing, evaluation, and source-ingestion actions
* Implemented: per-step error isolation with partial result recovery
* Implemented: explicit `ChapterPipelineState`-style workflow object
* Implemented: structured `WorkflowError` records with typed categories
* Implemented: persisted pipeline run snapshots for later inspection
* Implemented: transition logs and resumable workflow hints in the UI
* Implemented: resumable failed chapter runs from the last successful step
* Pending: full LangGraph or equivalent workflow runtime adoption
* Pending: full long-form dynamic orchestration that can automatically branch across outline, volume, arc, chapter plan, writing, review, and setting extraction
* Pending: first-class branching, retry policy, and richer resume execution

Workflow:

Plan
↓
Write
↓
Review
↓
Extract Settings

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

13. Ensure all LLM-calling functions validate for empty responses and raise explicit errors before parsing structured output

14. Do not silently swallow exceptions without at least a log warning — bare `except Exception: pass` makes bugs invisible

15. Path-constructing functions (especially those accepting user-provided names) must validate against path traversal; prefer raising `ValueError` early

16. Retrieval index assets (manifest + vectors) must stay consistent: every save/delete that modifies retrieval-relevant data must call `sync_project_retrieval_assets` (or document why it shouldn't)

17. On Windows, project Python commands should use the local virtual environment interpreter `.\.venv\Scripts\python.exe` instead of bare `python`, because bare `python` may resolve to Anaconda or another global interpreter without the project dependencies.

18. Quick generation chapter number `0` is preview-only. Preview-mode structure, outline, and chapter outputs must not be persisted as chapter files, chapter outlines, discussion artifacts, or retrieval-indexed assets.

19. Project- or story-specific Streamlit state must use scoped widget/session keys, such as `scoped_widget_key` or `scoped_session_key`, so switching projects or stories cannot leak prompts, discussion messages, generation results, or editor state across contexts.

---

# Known Technical Debt

The following items are acknowledged departures from the design philosophy and are tracked for future cleanup:

1. **Some UI modules still contain repeated page-composition patterns.** `app.py` has been reduced to an application shell and router, but several `ui/` pages still repeat discussion layout, form parsing, and save/delete action patterns. These should continue moving into shared UI helpers when the abstraction is clearer than the local page code.

2. **Duplicate code patterns exist across discussion/render functions.** Outline, volume, arc, and chapter discussion pages share ~70% of their structure. A shared discussion render helper would reduce maintenance cost.

3. **Legacy creative-task-wizard compatibility UI remains available from `ui.creative_profile_page`.** The separate user-facing wizard has been superseded by the consolidated creative profile page. The payload builder lives in `creative_profile_workflows.py`, but the compatibility renderer should eventually be removed or folded fully into the current discussion-assisted profile flow.

4. **Entity save functions in memory.py are structurally identical** (`save_character_entities`, `save_setting_entities`, `save_entity_aliases`, `save_extraction_plan_templates`). A parametrized `_save_entity_list(path, items)` helper would eliminate the duplication.

5. **launcher.py currently has limited cross-platform support.** The Python executable resolution defaults to Windows paths; Linux/macOS fall back to `sys.executable`. A proper multi-platform venv resolution is pending.

6. **No dedicated external vector database backend.** Vectors are now persisted into project SQLite for the local DB-first path, while `vectors.json` remains a compatibility mirror. Migration to Chroma/SQLite+FAISS is still planned only if project scale requires a specialized vector index.

---

# Instructions For Future LLMs

Before modifying the project:

Use the local project virtual environment for Python commands:

`.\.venv\Scripts\python.exe`

Do not assume bare `python` points to the project environment.

Read files in the following order:

1. project.md

2. app.py

3. ui/app_shell.py

4. ui/layout.py

5. ui/common.py

6. ui/step_views.py

7. ui/discussion.py

8. The specific `ui/*` page module relevant to the change

9. knowledge_workflows.py

10. knowledge_quality.py

11. knowledge_entities.py

12. source_workflows.py

13. resource_browser.py

14. extraction_presets.py

15. creative_profile_workflows.py

16. setting_knowledge.py

17. retrieval_eval.py

18. skills.py

19. memory.py

20. prompts.py

21. prompt_options.py

22. asset_guardrails.py

23. llm.py


When implementing new features:

* Reuse existing architecture
* Avoid breaking storage format
* Keep responsibilities separated
* Preserve project persistence
* Prefer adding Skills over hardcoding logic

This project is intended to evolve into a long-form novel writing platform and an educational Agent Systems project.
