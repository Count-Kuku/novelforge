[中文](./README.md) | [English](./README.en.md)

# NovelForge

Repository version: `v0.7.1`

NovelForge is a local LLM writing workspace for long-form fiction and fan fiction. It keeps projects, stories, source material, structured knowledge, retrieval evidence, and writing history on disk, making it better suited to sustained worldbuilding and chapter development than one-off chat generation.

## Core Capabilities

### Writing And Planning

- Multiple isolated story spaces per project, with shared project sources and knowledge.
- Full outline, volume, arc, chapter outline, drafting, review, and chapter evaluation.
- Iterative free writing with continuation, rewrite candidates, branching, accepted fragments, knowledge extraction, and chapter compilation.
- Story creative profiles for task type, length, workflow depth, reference strength, and source version/worldline.
- Global, project, and story-level generation rules and prompt options.
- Project/story/chapter/run-scoped writing reminders (context directives) and auditable generation-context snapshots.

### Sources And Knowledge

- Pasted sources, manual source cards, and multi-file TXT/Markdown/DOCX/EPUB/text-layer PDF ingestion.
- Recoverable Brave Search research agents with official/wiki/community/fanon planning, parallel discovery, safe fetching, claim extraction, cross-source verification, and human review.
- Structure-aware heading, chapter, scene, paragraph, and sentence splitting with source offsets, fingerprints, and segment checkpoints.
- General, character, relationship, timeline, worldbuilding, style, strict-canon, and fanfic-reference extraction modes.
- Multi-specialist plans, pending review, automatic review policy, conflict/duplicate checks, and batch rollback.
- Category-specific typed fields and immutable revisions for confirmed knowledge.
- Confirmed knowledge, character/setting entity cards, alias groups, and source-package reports.
- A source ledger that traces knowledge back to source revisions, segments, and exact evidence locations.

### RAG

- FTS5/BM25, application lexical ranking, and semantic ranking fused with RRF; full-text retrieval remains available when embeddings fail.
- Precise child chunks are retrieved first and expanded with bounded parent context; feedback binds to content fingerprints.
- Story, source-version/worldline, source-type, and authority filtering or weighting.
- Chinese phrase matching, entity-alias expansion, user feedback, conflict decisions, and result diversification.
- Retrieval health checks, debug views, source-usage reports, and explainable prompt evidence.
- Fixed evaluation cases with Recall@K, MRR, nDCG@K, and zero-recall counts.
- Incremental vector rebuilds normally reuse unchanged vectors; unusable vectors are regenerated per chunk, while model or vector-dimension changes safely switch to a full rebuild.

### Durable Source Tasks

Long-form automatic processing now creates a SQLite-backed task and returns control to the UI immediately:

- Work continues in the application process after a browser page is refreshed or closed.
- Atomic claims, worker leases, and heartbeats prevent duplicate processing across windows or app instances.
- Task creation and batch save/delete operations share an atomic database fence; stale UI snapshots, cross-task writes, and workers without a live lease are rejected.
- After an abnormal exit, a restarted app takes over once the old lease expires.
- Pause, resume, cancel, failed-segment-only retry, and completed-segment skipping are supported.
- The UI estimates model calls, input/output tokens, embedding tokens, and cost before creation.
- Tasks can be filtered, archived, restored, permanently deleted, or cleaned up by archive age.

“Background” does not mean an independent system service. Exiting NovelForge, terminating Python, or shutting down the machine interrupts the current call; the next app launch resumes from SQLite checkpoints.

### Web Research Agent

`资料导入 → 网络检索 → 自动研究 Agent` provides the complete research loop:

1. A bounded Planner creates queries from the topic, objective, and source roles.
2. LangGraph Collectors search official, secondary, community, and fanon branches in parallel.
3. The fetcher rejects local/private addresses, validates each redirect, pins the connection to an approved public IP, and limits content types, bytes, and redirects.
4. The Extractor keeps only candidates whose claim text and exact quotes can be located in the fetched page.
5. The model Verifier only proposes relationships; a deterministic guard isolates evidence by source role, category, and grounded statement, detects same-role conflicts, and scores evidence strength.
6. The user selects claims for pending review; they become formal knowledge only after confirmation.

Research tasks reuse SQLite `workflow_runs/workflow_steps` and support background execution, stage checkpoints, pause, resume, cancel, failed-stage retry, and archive. Official authority is assessed from the final HTTPS URL after redirects and the user-owned whitelist; official, community, and fanon evidence cannot promote one another. Each task owns separate page snapshots. Raw pages are quarantined from writing retrieval by default and enter RAG as explicitly marked untrusted external data only after user activation. The smaller manual search/select/import path remains available.

### Token And Cost Observability

- Chat, streaming, and embedding calls share one ledger for input, cached input, cache write, output, reasoning, and embedding tokens.
- OpenAI-compatible providers such as DeepSeek can use user-configured per-million-token rates in CNY or USD. The DeepSeek quick-fill preset uses its official CNY prices; OpenRouter can prefer provider-reported cost, and token-only mode is also supported.
- Every event stores its price snapshot and project/story/task/operation/agent attribution, so later price edits do not rewrite history.
- CNY is the default primary display currency. The sidebar shows today/month summaries, each UI action reports its own usage, and project/model pages provide CNY/USD daily tables, breakdowns, recent events, and CSV export. The USD ledger remains the cross-provider compatibility baseline.
- Events are retained in `data/global.db` by default and contain metering metadata rather than prompt or response bodies. Missing provider usage is marked estimated; missing prices remain unpriced instead of becoming a false zero.
- Long-source ingestion, automatic web research, and free writing show low/expected/high ranges for input, output, embedding, total tokens, and cost before execution. Research estimates are split across Planner, Extractor, and Verifier stages, while non-token services such as search APIs are explicitly excluded from the LLM amount. Fetched source pages remain quarantined until human activation, so activation-time embedding cost is not included in the task-creation estimate.
- Once the same model profile, operation, and agent role has at least five exact calls, preflight estimates are calibrated with historical P50/P90 usage. Model Settings provides token/cost warning thresholds and an optional explicit confirmation gate for estimates above the configured limits.

## Navigation

- `工作台` (Workbench): project overview and project resources.
- `资料` (Sources): source ingestion, core state, and retrieval center.
- `规划` (Planning): creative profile and the outline/volume/arc/chapter planning pages enabled by the active story.
- `写作` (Writing): free writing, content generation, and chapter evaluation.
- `配置` (Configuration): model settings, generation rules, and prompt options.

The source-ingestion page contains workspaces for durable tasks, source ledger, pending review, processing records, long-form batches, knowledge organization, and source packages. In normal use, follow the workbench's recommended next action instead of working from internal storage concepts.

## Recommended Workflow

### First Run

1. Add an OpenAI-compatible endpoint, API key, chat model, and optional embedding model under model settings.
2. Test the connection and save the profile.
3. Create a project and story, then set task type, target length, and reference strength in the creative profile.
4. If the story depends on canon or reference material, ingest sources before writing.

### Source Processing

1. Upload one or more TXT/Markdown/DOCX/EPUB/PDF files, or paste text. The free-writing source tray can explicitly run local PDF OCR when Tesseract is ready; other ingestion surfaces still require scanned PDFs to be OCRed first. Network search can create an automatic research task or import selected public pages.
2. Select indexing, knowledge extraction, and optional automatic-review behavior.
3. Review segment, call, token, and cost estimates.
4. Create the background task and monitor it in `资料任务` (Source Tasks); the browser page may be closed.
5. Resolve `待审核设定` (Pending Knowledge), inspect retrieval health, and run fixed evaluation cases.

### Chapter Writing

1. Discuss and save the outline or chapter direction.
2. Generate a chapter outline and prose, or iterate directly in free writing.
3. Review the token/cost range, then open the context preview before generation to inspect rules, core state, retrieved evidence, and budget omissions.
4. Review or evaluate the chapter, then extract stable new facts into pending knowledge.
5. Confirm knowledge so later chapters can retrieve it.

## Setup And Run

NovelForge requires Python 3 and the packages in `requirements.txt`.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Editing `.env` is optional; model profiles can also be configured and tested in the application.

Common non-secret environment values, plus legacy one-time key imports:

```env
LLM_API_KEY=
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_EMBEDDING_MODEL=
LLM_PROVIDER_TYPE=auto
LLM_COST_TRACKING_MODE=auto
LLM_PRICING_CURRENCY=USD
LLM_DISPLAY_CURRENCY=CNY
LLM_USD_TO_CNY_RATE=7.142857

# Legacy import: migrated to the system credential manager and scrubbed
BRAVE_SEARCH_API_KEY=

# Optional local cost estimation, per 1M tokens in LLM_PRICING_CURRENCY
LLM_INPUT_PRICE_PER_MILLION=0
LLM_CACHED_INPUT_PRICE_PER_MILLION=0
LLM_CACHE_WRITE_PRICE_PER_MILLION=0
LLM_OUTPUT_PRICE_PER_MILLION=0
LLM_EMBEDDING_PRICE_PER_MILLION=0
```

When prices are empty or `0`, NovelForge still records tokens but does not guess a cost. If the provider does not return cost directly, local amounts are estimates from the event's price snapshot rather than provider invoices. Model Settings separately controls the price-entry currency, primary display currency, and USD-to-CNY factor. The DeepSeek preset factor aligns its official Chinese and English price tables; it is not a live foreign-exchange quote. Update values, verification dates, and sources when either pricing or conversion policy changes.

Model, embedding, and Brave Search keys are configured in the UI and stored in Windows Credential Manager or the system keyring. SQLite and configuration mirrors retain only the credential reference, SHA-256 fingerprint, and last four characters. Legacy `.env` keys are one-time migration sources and are scrubbed after successful migration. `BRAVE_SEARCH_API_KEY` is sent only to Brave Search.

`.env` only bootstraps non-secret model parameters and migrates legacy keys on first launch. After model profiles have been written to `data/global.db`, the database is authoritative; update models and rates in `模型配置` (Model Settings), because editing `.env` alone does not override a saved profile.

## Data And Backups

- Global structured settings and the LLM usage ledger are stored in `data/global.db`.
- Each project's structured data is stored in `data/projects/{project_name}/project.db`.
- Long-form outlines, chapters, reviews, analyses, and imported sources remain Markdown/TXT assets registered in the database.
- Structured JSON mirrors are disabled by default; legacy files are compatibility import sources only.

Back up the entire `data/` directory regularly. Stop NovelForge before copying it for the most consistent snapshot. `.env` contains secrets and should be backed up securely without committing it. See [storage_architecture.md](./storage_architecture.md) for the complete storage contract.

## Windows Portable Build

The portable package contains a lightweight `NovelForge.exe` launcher, a self-contained `.runtime` Python distribution, project source, and a local `data/` directory. It starts Streamlit on `127.0.0.1`, prefers port `8501`, and opens the browser.

After preparing a self-contained Windows Python runtime without `pyvenv.cfg`, run:

```powershell
.\build_release.ps1 -Version v0.7.1 -RuntimeRoot D:\Runtimes\python-standalone
```

`-Version` must match `VERSION`. The build produces a ZIP, SHA-256 checksum, and local log. Extract it to a writable directory such as `D:\Apps\NovelForge\`, not `C:\Program Files\`.

## Current Limits And Priorities

- Structure-aware splitting, parent/child context, and FTS/lexical/semantic RRF fusion are complete; quota-controlled query routing for characters, relationships, timelines, and hard constraints is the next RAG priority.
- Stable ingestion supports pasted text, TXT, Markdown, DOCX, EPUB, text-layer PDF, and public static web pages. The free-writing source tray additionally supports explicit local OCR with per-page confidence; scanned-PDF OCR in long-form ingestion, dynamically rendered pages, and recursive folder ingestion are not yet provided.
- Durable source tasks depend on the NovelForge application process; they are not a resident service or distributed queue.
- A dedicated vector database and GraphRAG will be evaluated only after the current local SQLite/retrieval path shows a measured scale bottleneck.
- Web research now includes durable tasks, claim extraction, cross-source verification, evaluation, and human review. LangGraph only coordinates parallel dispatch inside one search step; SQLite `workflow_runs/workflow_steps` remains authoritative.

## Development Documentation

- [project.md](./project.md): current architecture, module responsibilities, development boundaries, technical debt, and priorities.
- [storage_architecture.md](./storage_architecture.md): DB-first authority, schema v15, migrations, task leases, and recovery.
- [docs/releases](./docs/releases): immutable release history.

Completed one-off plans are not kept as permanent documentation. Their lasting results belong in the fact documents above so the repository has one current source of truth.

## License

The repository currently does not include a license file.
