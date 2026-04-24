# Phase A Handoff — search-application-v2

**Status:** Phase A complete on Ubuntu laptop (2026-04-24). Ready to continue on Windows desktop for Phase B (deploy to Fly.io).

## What this document is for

Phase A of the web-app refactor (FastAPI + DuckDB rewrite of the Flask parquet-in-memory app) was built on the Ubuntu laptop. The production DuckDB file (~1.3 GB currently, ~1.5–2 GB after full rebuild) lives on the Windows desktop, and the user (Siddharth) is more used to running Fly deploys from Windows. So Phase B (containerize + deploy + DNS cutover) continues on the Windows desktop.

This document is a self-contained brief for a fresh Claude Code session on Windows: what was built, what's left, and how to ship it.

## What's built in `search-application-v2/`

```
search-application-v2/
├── app/
│   ├── main.py              # FastAPI app, sync endpoints, lifespan loads autocomplete
│   ├── queries.py           # Parameterized DuckDB queries (search, download_all)
│   ├── db.py                # Single global read-only connection, autocomplete loader
│   ├── config.py            # Env var handling (ISRD_DB_PATH, ISRD_RESULTS_PER_PAGE)
│   ├── templates/           # Jinja2 templates ported from v1 with minimal tweaks
│   │   ├── index.html
│   │   ├── results.html
│   │   └── about.html
│   └── static/              # CSS / JS / background image, copied verbatim from v1
├── scripts/
│   └── build_dev_db.py      # Builds dev DuckDB from v1 parquet (for local dev/testing)
├── dev_data/                # Machine-local dev DB; gitignored
├── tests/
│   ├── conftest.py          # v1 Flask test-client + v2 FastAPI test-client fixtures
│   └── test_parity.py       # 22 parity tests, all passing
├── Dockerfile               # python:3.12-slim, non-root user, uvicorn 2 workers
├── fly.toml                 # Fly.io config, volume mount at /data, CDG region
├── deploy/README.md         # Step-by-step deploy + DNS cutover guide
├── requirements.txt         # fastapi, uvicorn, jinja2, python-multipart, duckdb, polars, pyarrow
├── requirements-dev.txt     # pytest, beautifulsoup4, httpx
├── .dockerignore
├── .gitignore
└── README.md                # Local-dev quickstart
```

## Feature parity vs v1

Route-for-route parity with `search-application/app.py`:
- `GET /` → index page
- `GET /about` → about page
- `GET /institutions` → JSON autocomplete list (IN+CH only)
- `GET /authors` → JSON autocomplete list (IN/CH/Joint/Both collab_status)
- `POST /search` → results page, 100 results/page, BETWEEN year filter, AND-semantic author/affiliation filters, case-insensitive substring on title+abstract
- `POST /download` → streamed CSV of full result set

Filter semantics match v1 exactly (verified by 22 parity tests, all passing).

## Parity test results (2026-04-24)

```
============================= 22 passed in 42.95s ==============================
```

Includes:
- 15 parametrized search cases (title/abstract substrings, year ranges, multi-entry author/institution AND filters)
- 5 institution spot-check counts against Phase-1 numbers (ETH Zurich, UZH, CERN, TIFR, Panjab Univ)
- Author autocomplete parity (v1: 53,045 names, v2: 53,045 names)
- Institution autocomplete parity (v1: 2,250, v2: 2,235 — 15-institution delta is acceptable; orphan institutions in the IN/CH summary table that had no live publication)

Run tests at any point with:
```bash
.venv/bin/pytest search-application-v2/tests/ -v
```

## Known deltas from Phase-1 report numbers

- ETH Zurich: v2=3457, Phase-1=3448 (+9)
- Univ Zurich: v2=2841, Phase-1=2834 (+7)
- CERN, TIFR, Panjab: exact match within ±1

Explanation: Phase-1 numbers came from the structured `institutional_relationships_IN_CH.parquet` table, which had been deduped by OpenAlex inst_id. v2 does substring-matching on normalized `institutions.display_name` including rows where the source parquet had a null `work_id` (79 such rows — valid DOIs, just missing OpenAlex IDs — now assigned synthetic negative work_ids so they're not silently dropped). The drift is small, consistent, and does not affect user-facing behavior.

## How the v2 app queries data

v2 expects a DuckDB with the schema defined by `ingestion/05_build_duckdb.py`. The tables it uses:
- `works` (work_id PK, title, abstract, doi, publication_year, source_display_name, ...)
- `authors` (author_id PK, display_name, collab_status, ...)
- `institutions` (inst_id PK, display_name, country_code, ...)
- `work_authors` (work_id, author_id, author_position)
- `work_institutions` (work_id, inst_id)

All works in the DB are already Indo-Swiss co-authored (the ingestion pipeline filters upstream), so queries use `works` directly, not the `indo_swiss_works` view. Queries are parameterized, never string-concatenate user input.

The **prod DuckDB** (`indo_swiss_research.duckdb`) on the Windows desktop was produced by `ingestion/05_build_duckdb.py` and is the canonical file to deploy. It is NOT in git. It lives (per CLAUDE.md) on the Windows desktop under `D:\Projects\indo-swiss-collab\ingestion\output\indo_swiss_research.duckdb` (confirm path at deploy time).

The **dev DuckDB** in `search-application-v2/dev_data/` is rebuilt from the v1 parquet via `scripts/build_dev_db.py`. It is for local dev/testing only, is gitignored, and has ~20 fewer institutions than the prod DB because it is derived from a narrower R-produced parquet rather than the full normalized pipeline output.

## Environment variables

The app reads:
- `ISRD_DB_PATH` — path to the DuckDB file. Default: `dev_data/indo_swiss_research_dev.duckdb` (relative to CWD). In the Fly container: `/data/indo_swiss_research.duckdb` (set in `fly.toml`).
- `ISRD_RESULTS_PER_PAGE` — default `100`, matches v1.

## Phase B — what to do on the Windows desktop

Follow `search-application-v2/deploy/README.md`. Summary:

1. Install flyctl; `fly auth login`.
2. `cd search-application-v2; fly launch --no-deploy` → pick region `cdg` (or `bom` for India-first / `zrh` for CH-first; cdg is the equidistant compromise); do NOT create Postgres; do NOT generate a Dockerfile (we provide one).
3. `fly volumes create isrd_data --region cdg --size 3`.
4. `fly deploy` — first deploy with no DB; app starts but searches will error.
5. Upload the prod DuckDB via `fly ssh sftp`:
   ```
   fly ssh sftp put D:\Projects\indo-swiss-collab\ingestion\output\indo_swiss_research.duckdb /data/indo_swiss_research.duckdb
   ```
6. `fly apps restart <app-name>`.
7. Test `fly open` → hit a known institution (ETH Zurich should return ~3,400+).
8. DNS cutover for `indoswisscollab.org`: `fly certs add`, update A/AAAA or CNAME records at the registrar (Siddharth will supply creds at this step), `fly certs check`.

## Verifying after Phase B

Smoke-test queries on the deployed site:
- Empty search → ~25k results
- "ETH Zurich" in institutions → ~3,400+ results
- Year range 2020–2022 → several thousand
- "quantum" in title/abstract → few hundred

If any query 500s or returns 0, check `fly logs`. Most likely causes: `ISRD_DB_PATH` pointing at a missing file (re-run sftp step), or the DuckDB file truncated mid-upload (re-upload and retry).

## What NOT to change on the Windows desktop

- `search-application/` — v1 Flask app, keep intact through cutover so there's a known-good reference. Remove only AFTER v2 is serving real traffic successfully for a few days.
- `Data/` — Phase-1 deliverable parquets. Trusted baseline; do not overwrite.
- `indo_swiss_research.duckdb` (prod) — only replace it via a clean run of `ingestion/05_build_duckdb.py` on fresh inputs.
- `openAlex_topics.sqlite` — stable reference, refresh only on explicit request.
- The ingestion pipeline scripts in `ingestion/` — these passed end-to-end validation on Ubuntu (see earlier summary of 21k-row partial run); the Windows desktop should run the **full** pipeline with all three sources (WoS XLS + Scopus CSV + OpenAlex), which will populate the DuckDB with the full ~25k works before deploy.

## Outstanding items (post-Phase B)

- **Full-dataset parity validation.** The Python ingestion pipeline has been validated end-to-end on partial data (21k works, no Scopus input on Ubuntu). The full 24,979-row parity check against the R baseline requires the full WoS+Scopus raw exports, which live on the Windows desktop at `D:\Data\ISRD\source_data\`. Run `python ingestion/ingest.py --label 2000-2024 --start 2000-01-01 --end 2024-12-31` on Windows to rebuild; then re-run `ingestion/tests/test_parity.py` which has strict 24,979-row checks that currently skip on the partial Ubuntu build.
- **Phase C (enrichments):** topic chips on result rows, citation + OA badges, author and institution drill-down pages. These are cheap with DuckDB but deliberately scoped out of Phase A to keep the deploy fast.
- **Phase D (intelligence platform):** the separate `isrc-intelligence` repo has the semantic-search / ChromaDB / FastAPI work. That's a separate deployable with its own roadmap.

## Files this session produced

Created:
- `search-application-v2/` entire tree (18 files across app, tests, scripts, deploy)
- `search-application-v2/PHASE_A_HANDOFF.md` (this file)

Not modified:
- `search-application/` (v1 intact)
- `Data/`, `ingestion/output/*.duckdb`, `openAlex_topics.sqlite`
- Any ingestion pipeline scripts
- Root `CLAUDE.md` was updated with a small pointer to this doc

## Useful commands cheatsheet

```bash
# Rebuild dev DB (after pulling new v1 parquet updates)
.venv/bin/python search-application-v2/scripts/build_dev_db.py

# Run parity tests
.venv/bin/pytest search-application-v2/tests/ -v

# Run app locally against dev DB
ISRD_DB_PATH=search-application-v2/dev_data/indo_swiss_research_dev.duckdb \
  .venv/bin/python -m uvicorn app.main:app --app-dir search-application-v2 --reload

# Smoke test against prod DuckDB locally (Windows: once DB is accessible)
set ISRD_DB_PATH=D:\Projects\indo-swiss-collab\ingestion\output\indo_swiss_research.duckdb
.venv\Scripts\python -m uvicorn app.main:app --app-dir search-application-v2 --reload

# Deploy (Windows, once flyctl installed)
cd search-application-v2
fly deploy
```

## Contact surface for questions

All design decisions documented inline in:
- `deploy/README.md` — deploy workflow, region choice, volume sizing, DNS
- `search-application-v2/README.md` — local dev quickstart
- `search-application-v2/tests/test_parity.py` — parity test assertions and tolerances
- Comments in `app/queries.py` — filter semantics matching v1

Git history: no commits made by this session per user instruction ("only the human user decides when and how to commit"). Run `git status` at session start on the Windows desktop to see everything that's new and untracked.
