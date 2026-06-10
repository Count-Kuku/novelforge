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
* Memory update
* DeepSeek API integration
* Streamlit UI

Future versions will introduce:

* RAG
* LangGraph workflow
* Multi-Agent architecture
* Evaluation system
* Consistency checking

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
DeepSeek API
↓
Memory Layer
(memory.py)
↓
Project Storage

---

# Directory Structure

novelforge/

├── app.py

├── llm.py

├── memory.py

├── prompts.py

├── skills.py

├── requirements.txt

├── .env

├── PROJECT.md

└── data/

```
└── projects/

    └── {project_name}/

        ├── memory.json

        ├── outline.md

        ├── chapter_outlines/

        ├── chapters/

        └── reviews/
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

Business logic should remain minimal.

---

## llm.py

Model abstraction layer.

Responsibilities:

* Model connection
* API configuration
* Model switching

Current model:

* DeepSeek Chat

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
* Loading outlines
* Saving outlines
* Loading chapter outlines
* Saving chapter outlines
* Loading chapters
* Saving chapters

No LLM logic should exist here.

---

## prompts.py

Prompt template layer.

Responsibilities:

* Outline generation prompts
* Chapter outline prompts
* Chapter writing prompts
* Memory update prompts

Prompt engineering should be isolated here.

---

## skills.py

Skill execution layer.

Responsibilities:

* Generate outline
* Generate chapter outline
* Write chapter
* Update memory

Future skills:

* Review chapter
* Consistency check
* Character analysis
* Timeline analysis
* Foreshadowing analysis

---

# Current Workflow

Outline Generation

User Idea
↓
generate_outline
↓
outline.md

---

Chapter Planning

Outline
↓
generate_chapter_outline
↓
chapter_outlines/chapter_xxx.md

---

Chapter Writing

Chapter Outline
+
Memory
↓
write_chapter
↓
chapters/chapter_xxx.md

---

Memory Update

Chapter
↓
update_memory_from_chapter
↓
memory.json

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

outline.md

Stores the global story outline.

chapter_outlines/

Stores chapter plans.

chapters/

Stores chapter content.

reviews/

Stores review results.

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

## V1.1

Persistence improvements

Features:

* Save chapter outlines
* Load chapter outlines
* Save chapters
* Load chapters
* Better memory updates

---

## V2

RAG Integration

Features:

* Embeddings
* Vector database
* Semantic retrieval
* Context selection

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

7. Maintain backward compatibility with existing project data

---

# Instructions For Future LLMs

Before modifying the project:

Read files in the following order:

1. PROJECT.md

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
