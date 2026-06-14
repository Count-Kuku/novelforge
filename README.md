# NovelForge

NovelForge is a long-form novel writing workspace built around LLMs, persistent project storage, retrieval, structured workflows, and future multi-agent collaboration.

It is designed for long-running creative projects such as fan fiction and web novels, where consistency, memory, planning, and iterative refinement matter more than one-off chat generation.

## Why NovelForge

Most LLM writing tools are optimized for short conversations and single-pass generation.
NovelForge focuses on a different problem:

- persistent project-based writing
- long-term story memory
- outline to chapter workflow support
- retrieval-augmented context injection
- structured review and validation
- future workflow runtime and agent orchestration

The project is both:

- a practical novel-writing tool
- a learning platform for LLM apps, RAG, workflows, and agent systems

## Current Status

NovelForge is already beyond an early prototype.

Current maturity can be summarized as:

- V1 writing workspace: implemented
- V1.1 persistence, validation, and UX hardening: implemented
- V2 retrieval foundation: largely implemented
- V3 workflow/state foundation: partially implemented
- V4 multi-agent architecture: planned
- V5 evaluation system: planned

## Core Features

- Project-based storage for each story
- Streamlit web UI
- Full-story outline generation
- Chapter outline generation
- Chapter writing
- Chapter review
- Memory update from written chapters
- Structured memory editing forms
- Configurable chapter target word count
- Memory compaction for long-running projects
- Layered prompt rules at global and project scope
- Retrieval center for project and external knowledge
- Lexical, semantic, and hybrid retrieval modes
- Authority-aware and conflict-aware retrieval evidence
- Character, timeline, foreshadowing, and consistency analysis
- Structured planning discussions for outline, volume, arc, and chapter direction
- Approval-based planning artifacts
- One-click chapter pipeline with persisted workflow state and run snapshots
- Volume and arc planning hierarchy
- Lightweight writing-guidance controls for chapter execution
- In-app LLM endpoint and key configuration

## Design Principles

NovelForge follows a few core principles:

1. Persistence before intelligence
2. Workflow before agents
3. Skills before autonomy
4. Project-oriented architecture
5. Model independence through an OpenAI-compatible interface

## Architecture

Current high-level flow:

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
- `prompts.py`: prompt templates and prompt assembly
- `llm.py`: model abstraction and API integration
- `memory.py`: persistent storage and project data management
- `schemas.py`: structured output contracts and validation
- `retrieval.py`: indexing, retrieval, and context formatting

## Typical Workflow

NovelForge supports both direct generation and discussion-first planning.

Typical chapter flow:

1. Discuss story or chapter direction
2. Generate outline or chapter outline
3. Write chapter content
4. Review chapter quality and consistency
5. Update story memory
6. Inspect analysis or retrieval evidence if needed

The system also supports a combined pipeline:

```text
Plan -> Write -> Review -> Update Memory
```

## Retrieval And Knowledge Support

NovelForge includes a project-scoped retrieval layer for both internal story assets and external reference material.

Supported retrieval concepts include:

- project knowledge
- canon/reference knowledge
- chunked document indexing
- semantic embeddings
- hybrid lexical + semantic ranking
- source authority weighting
- evidence grouping by scope
- conflict warnings when project and external evidence overlap

## Project Storage

Each story is stored as a persistent project directory under `data/projects/`.

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

This keeps planning, writing, review, analysis, and retrieval assets attached to the same project instead of scattering them across chat history.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure model access

You can configure model settings in either of these ways:

- edit `.env` manually
- use the in-app `模型配置` page to create and switch between multiple saved profiles

Typical environment values:

```env
LLM_API_KEY=
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_EMBEDDING_MODEL=text-embedding-3-small
```

### 3. Run the app

```bash
streamlit run app.py
```

## Local Windows Portable Build

NovelForge can also be packaged as a local Windows portable app that launches the Streamlit server and opens the browser automatically.

### Release shape

The intended local distribution is:

- `NovelForge.exe` as a small launcher
- bundled `.venv` runtime
- project source files
- local `data/` directory for project storage

When the user launches `NovelForge.exe`, it should:

1. start the local Streamlit server on `127.0.0.1`, preferring `8501`
2. wait until the app is reachable
3. open the browser automatically

### Build steps

1. Create and populate the local virtual environment:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

2. Run the packaging script from PowerShell:

```powershell
.\build_release.ps1 -Version v0.1.0
```

3. The script will:

- install `pyinstaller` into `.venv`
- build `NovelForge.exe` from `launcher.py`
- assemble `release/NovelForge-Portable/`
- create `release/NovelForge-windows-portable-v0.1.0.zip`
- save a local build transcript under `release/`

### Notes

- Extract the portable build into a writable folder such as `D:\Apps\NovelForge\`
- Avoid protected folders such as `C:\Program Files\`
- User data remains in the local `data/` folder and `.env` file next to the app
- The launcher prefers local port `8501` and automatically falls back to nearby ports if needed
- If startup fails, check `launcher.log` in the app directory for diagnostics
- If one candidate port is already occupied by another local app, the launcher will try the next port instead of opening the wrong page
- Build-time packaging logs are written next to the artifacts under `release/build_release-<version>.log`

## Supported Model Strategy

The project is designed around an OpenAI-compatible API layer.

Current default:

- DeepSeek

Planned or compatible direction:

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

- graph/runtime-based orchestration
- first-class retry and resume behavior
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
- plot progression

## Development Notes

The project keeps responsibilities intentionally separated:

- UI logic should stay light in `app.py`
- new writing abilities should be added through `skills.py`
- prompt engineering belongs in `prompts.py`
- persistence logic belongs in `memory.py`
- model changes should stay isolated in `llm.py`
- structured LLM outputs should be defined through `schemas.py`

For deeper implementation and roadmap details, see `project.md`.

## License

No license file is currently included in the repository.
