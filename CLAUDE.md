# indo-swiss-collab — project context for Claude Code

This file is the single source of truth for project context that Claude Code (or a collaborator) needs on entering this repo. It is git-tracked so it syncs across machines. Do not store project context in the machine-local Claude memory directory — put it here instead.

## What this project is

A database and search UI mapping research collaborations between India and Switzerland, built from indexed publication metadata (OpenAlex, Web of Science, Scopus), covering publications from 2000 onward. Deployed at https://www.indoswisscollab.org/.

Phase 1 (2000–2024, complete) produced the trusted baseline:
- **24,979** unique works
- **2,690** unique IN+CH institutions
- **~556,000** unique authors involved in at least one joint IN–CH publication
- Canonical analytical store: `indo_swiss_research.duckdb` (DuckDB, migrated from SQLite in Aug 2025) — **not committed to git; may live only on the Windows desktop. Ubuntu laptop currently lacks this file.**
- Topic hierarchy: `openAlex_topics.sqlite` (4 domains, 29 fields, 151 subfields, ~4.5k topics) — **also not committed. Can be rebuilt by porting `data_assembly/extract_openAlex_topics.r` if missing.**
- Raw deliverable parquets in `Data/` (these ARE on disk — see inventory below)
- Documentation: `Metadata/dataset_v1_metadata_documentation.md`, `Metadata/relational_db_documentation.md`

### Parquets present in `Data/` (available on Ubuntu laptop, verified 2026-04-24)
- `publications_full_dataset_2000-2024.parquet` (88M) — primary deliverable, matches `SCHEMAS.md §03`
- `authors_summary_in_ch.parquet` (3.5M) — IN/CH subset, matches `SCHEMAS.md §04`
- `publication_details_WoS-Scopus.parquet` (135M) — step 01 equivalent baseline
- `publication_combined_2000_2024.parquet` (28M) — cleaned OpenAlex works, step 02 equivalent baseline
- `authorships_combined_2000_2024.parquet` (205M) — step 02 authorships equivalent baseline
- `publications_compiled_2000-2024.parquet` (41M) — older compiled pass, historical
- RData files from raw OpenAlex pulls per period: `OA_2000-01-01_2010-12-31.rdata`, `OA_2011-01-01_2019-12-31.rdata`, `OA_2020-01-01_2024-12-31.rdata`, `openAlex_df_2000-2024.rdata`

### Parquets per `Metadata/dataset_v1_metadata_documentation.md` but NOT on Ubuntu laptop
- `authors_processed_flat.parquet`
- `authors_summary_with_lists.parquet`
- `work_topic_links.parquet`
- `work_institution_links.parquet`
- `institutional_relationships_IN_CH.parquet`

These may exist on the Windows desktop. If they do, copy them over for parity testing; if not, they can be rebuilt by the Python pipeline from the parquets that ARE present.

## People

- **Siddharth Bharath** — sole project owner as of 2026-04-24. Wrote the R data-assembly code in 2024. Comfortable in both R and Python.
- **Pranshu Jaiswal** — former collaborator, authored the original `search-application/` Flask app (visible in git log). No longer active on the project.

## Strategic direction

The long-term goal is to move off WoS + Scopus dependence and run a **monthly OpenAlex-only ingest**. We are not there yet: the metadata-lag-study showed OpenAlex misses some papers that WoS+Scopus catch. Until OA-only coverage matches, we continue annual 3-source ingest.

**Architectural implication:** design the OpenAlex fetch step (`ingestion/02_fetch_openalex.py`) as a fully self-contained module that can produce a usable dataset on its own. When we flip to OA-only monthly, the job becomes "02 + trimmed 03/04/05" — no rewrite.

## Current technical state

- **Annual ingestion pipeline is being refactored from R to Python.** In-progress work lives in `ingestion/`. The original R scripts in `data_assembly/` remain as the reference implementation until the Python pipeline passes parity testing against the 24,979-row baseline; only then do they move to `_legacy_r/`. End-to-end validated on Ubuntu with partial data (no Scopus input) — 21k works. Full parity run against 24,979-row baseline pending full WoS+Scopus inputs on Windows desktop.
- **Known missing prerequisite for step 05:** `openAlex_topics.sqlite` is not on the Ubuntu laptop. Before step 05 can run, we need to either (a) sync it from the Windows desktop, or (b) port `data_assembly/extract_openAlex_topics.r` to `ingestion/00_build_topic_hierarchy.py` (it's a one-time pull from the OpenAlex `/topics` endpoint, ~420 lines of R but mostly boilerplate — maybe 150 lines of Python).
- **Web app v1 (`search-application/`)** — original Flask app, Python, parquet-in-memory. Kept intact through Fly cutover as the known-good reference.
- **Web app v2 (`search-application-v2/`)** — FastAPI + DuckDB rewrite, Phase A complete as of 2026-04-24. 22/22 parity tests passing against v1 on the same data. Deploy target: Fly.io with a volume-mounted DuckDB. See `search-application-v2/PHASE_A_HANDOFF.md` for full handoff notes; `search-application-v2/deploy/README.md` for step-by-step deploy instructions. Phase B (deploy + DNS cutover to indoswisscollab.org) is the next step, to run from the Windows desktop where the prod DuckDB lives.
- **Analysis notebooks** (`analysis_1.Rmd`, `analysis_2.Rmd`, `analysis_2a.Rmd`) stay in R — already rendered to HTML, treated as one-off report outputs. New analysis questions get fresh Python notebooks, not Rmd ports.
- **Intelligence layer** — the separate `isrc-intelligence` repo (private, on GitHub) houses Siddharth's Phase 2 semantic-search / ChromaDB / planned FastAPI work. That's a separate deployable with its own roadmap and is not part of the public search app rewrite.

## File-path conventions

Raw WoS/Scopus XLS+CSV exports live at:
- **Ubuntu laptop:** `~/Data/ISRD/source_data/`
- **Windows desktop:** `D:\Data\ISRD\source_data\`

Code must not hardcode either. Use `ingestion/config.py::raw_data_dir()`, which auto-detects platform and honors an `ISRD_SOURCE_DATA` env var override.

Interim parquets (machine-local, not git-tracked) go under `ingestion/interim/`. Final output parquets that should match existing `Data/` schema go under `ingestion/output/` during parity testing, then get promoted to `Data/` once validated.

## Python stack

- **Environment:** project-local venv at `.venv/` (create with `python3 -m venv .venv`). Not the genwise global venv — this project has distinct deps.
- **Dependencies:** see `ingestion/requirements.txt`. Stack is `polars` + `pyarrow` for dataframes, `duckdb` for SQL/joins/DB build, `pyalex` for OpenAlex API, `pandas` for compatibility with existing Flask app, `tqdm` for progress, `pytest` for parity tests.
- **OpenAlex polite pool:** always pass `mailto=siddharth.bharath@protonmail.com` to get the faster rate-limit tier.

## How to collaborate with Claude Code on this repo

**Orchestrator pattern:** For non-trivial refactor work, Claude acts as architect/orchestrator and delegates implementation tasks to Sonnet/Opus subagents (`Agent` tool with `subagent_type=general-purpose`). The orchestrator reviews each subagent's output against the R reference implementation before moving on.

**Subagents must not commit to git.** Only the human user decides when and how to commit. Subagent prompts must include an explicit "do not run `git commit`, `git add`, `git push`, or any other git state-modifying command" line. The same rule applies to the orchestrator: never commit without an explicit request from the user.

**Parity-test gate:** No Python script is considered "done" until its output parquet has been diff'd against the R-produced parquet for the same inputs. Row counts must match exactly; schemas must match. Spot-check known values (ETH Zurich → 3,448 publications; TIFR → 2,553; European Org for Nuclear Research → 2,802).

**Do not touch without discussion:**
- Existing parquets in `Data/` — they are the trusted baseline.
- `indo_swiss_research.duckdb` — same reason.
- `openAlex_topics.sqlite` — stable, reused as-is; refresh only on explicit request.
- Analysis Rmds — already rendered; porting to Python requires a fresh analysis question, not a 1:1 translation.

## Related repositories and resources

- `/home/siddharth/Documents/Swissnex/ISRD/metadata-lag-study/assembly/` (Ubuntu) — cleaned 3-script R template from late-2025 that shaped the `ingestion/` layout.
- `malleswaram-corporator-election-2026` — prior Flask-app collaboration Siddharth and Claude Code worked on; reference for UI patterns when the search-app rewrite happens.
- OpenAlex API docs: https://docs.openalex.org/

## Dates

Per-session environment provides today's date. When writing git-tracked notes or process logs, always use absolute dates (e.g. "2026-04-24"), never "today" or "last week", so they remain interpretable when synced.
