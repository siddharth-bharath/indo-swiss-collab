# Annual ingestion pipeline

Python port of the R `data_assembly/` pipeline. Produces the parquet deliverables and `indo_swiss_research.duckdb` expected by the search app and the Metadata documentation.

## Scripts

| # | Script | Inputs | Outputs |
|---|---|---|---|
| 01 | `01_ingest_wos_scopus.py` | raw XLS/CSV in `$ISRD_SOURCE_DATA` | `interim/wos.parquet`, `interim/scopus.parquet` |
| 02 | `02_fetch_openalex.py` | date range or DOI list | `interim/openalex_works.parquet`, `interim/openalex_authorships.parquet` |
| 03 | `03_harmonise.py` | outputs of 01, 02 | `output/publications_full_dataset_<label>.parquet`, `output/work_topic_links.parquet` |
| 04 | `04_process_authors.py` | 02 authorships + 03 works | `output/authors_processed_flat.parquet`, `output/authors_summary_with_lists.parquet`, `output/work_institution_links.parquet`, `output/institutional_relationships_IN_CH.parquet`, `output/authors_summary_in_ch.parquet` |
| 05 | `05_build_duckdb.py` | all output parquets + `openAlex_topics.sqlite` | `output/indo_swiss_research.duckdb` |
| — | `ingest.py` | CLI orchestrator | runs 01→05 with a period label |

Step 02 is also the entry point for the future monthly OpenAlex-only run (see `CLAUDE.md`).

## Setup

```bash
cd /home/siddharth/Documents/Swissnex/ISRD/indo-swiss-collab
python3 -m venv .venv
source .venv/bin/activate      # Ubuntu / macOS
# .venv\Scripts\activate       # Windows
pip install -r ingestion/requirements.txt
```

## Running

```bash
source .venv/bin/activate
python ingestion/ingest.py --period 2025 --mode full
```

Or run individual scripts for debugging:
```bash
python ingestion/01_ingest_wos_scopus.py
python ingestion/02_fetch_openalex.py --start 2025-01-01 --end 2025-12-31
```

## Raw data location

- Ubuntu: `~/Data/ISRD/source_data/`
- Windows: `D:\Data\ISRD\source_data\`
- Override via env var: `ISRD_SOURCE_DATA=/custom/path`

Filename conventions:
- `wos*.xls` or `wos*.xlsx` for Web of Science exports
- `scopus*.csv` for Scopus exports
- Period is inferred from filename (e.g. `_2024_`, `06-2025`) — see `config.py` and the R reference.

## Parity testing

Before swapping out the R pipeline, run `tests/test_parity.py` to diff new outputs against the Phase 1 baseline in `Data/` and `indo_swiss_research.duckdb`. Row counts must match; spot queries (ETH Zurich → 3,448 publications) must agree.
