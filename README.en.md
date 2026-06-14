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
- V3 workflow and state foundation: partially implemented
- V4 multi-agent architecture: planned
- V5 evaluation system: planned

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
- retrieval center for project and external knowledge
- lexical, semantic, and hybrid retrieval
- authority-aware and conflict-aware evidence presentation
- character, timeline, foreshadowing, and consistency analysis
- structured planning discussions for outline, volume, arc, and chapter direction
- approval-based planning artifacts
- one-click chapter pipeline with run snapshots
- volume and arc planning hierarchy
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

The system also supports a combined pipeline:

```text
Plan -> Write -> Review -> Update Memory
```

## Retrieval And Knowledge Support

NovelForge includes a project-scoped retrieval layer that works across both internal writing assets and external reference material.

Current retrieval capabilities include:

- project knowledge retrieval
- canon and reference retrieval
- document chunk indexing
- semantic embedding retrieval
- hybrid lexical + semantic ranking
- source authority weighting
- scope-grouped evidence display
- conflict warnings when project evidence and external evidence overlap

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
      outline.md
      volumes/
      arcs/
      chapter_outlines/
      chapters/
      reviews/
      analysis/
      retrieval/
      runs/
```

This keeps planning, draft chapters, reviews, analysis, and retrieval artifacts attached to the same project instead of scattering them across chat history.

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
- deeper fact-level conflict handling
- stronger retrieval robustness

### V3 workflow runtime adoption

- graph or runtime-based workflow orchestration
- first-class retry and resume support
- branching workflow execution

### V4 multi-agent architecture

Planned roles include:

- ChiefEditorAgent
- PlotAgent
- WriterAgent
- ReviewAgent
- MemoryAgent
- ResearchAgent

### V5 evaluation system

Planned evaluation dimensions include:

- character consistency
- world consistency
- timeline consistency
- writing quality
- plot progression quality

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
