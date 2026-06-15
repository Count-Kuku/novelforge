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
- source ingestion page for importing canon/reference/sample text and extracting structured knowledge
- retrieval center for index rebuilds, recall tests, debug inspection, and conflict handling
- project creative profile for task nature, target length, workflow depth, and reference strength, with custom values supported
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
- `Source Ingestion` / `Retrieval Center`: ingestion imports and structures material; retrieval rebuilds indexes, tests recall, inspects debug output, and stores conflict decisions.

Current retrieval capabilities include:

- project knowledge retrieval
- canon and reference retrieval
- document chunk indexing
- semantic embedding retrieval
- hybrid lexical + semantic ranking
- source authority weighting
- scope-grouped evidence display
- conflict warnings when project evidence and external evidence overlap
- persisted conflict resolutions that can be recalled as project knowledge
- optional retrieval debug output for inspecting recall and ranking behavior
- structured knowledge extraction from pasted material with human confirmation before persistence
- confirmed structured knowledge is indexed for later generation, review, analysis, and evaluation

## Creative Profile

Each project can store a creative profile describing the intended generation path:

- task nature: main story, side story, continuation, prequel, transmigration/AU, completion, scene fragment, or a custom value
- target length and optional word count, both customizable
- workflow depth, from direct prose generation to full long-form outline hierarchy
- reference strength: light, medium, strong, strict canon, or style-focused
- reference focus such as characters, worldbuilding, events, abilities, timeline, writing style, dialogue style, techniques, and hard constraints, with custom tags supported

This profile is injected into major generation, discussion, review, and analysis prompts so model behavior can adapt to length, workflow depth, and reference strength.

The in-app `动态生成` page now provides a first executable dynamic path:

- direct prose generation
- short-form structure plus prose
- chapter plan plus prose
- lightweight flows for short stories, side stories, continuations, prequels, transmigration/AU stories, completion pieces, and scene fragments

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
