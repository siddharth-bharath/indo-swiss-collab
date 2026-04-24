"""CLI orchestrator for the indo-swiss-collab ingestion pipeline.

Chains steps 01 → 05. Each step is callable standalone if you want
finer control; this is the convenience entry point.

Usage:
    # Full 3-source annual rebuild (2025 example):
    python ingestion/ingest.py --label 2025 --start 2025-01-01 --end 2025-12-31

    # OpenAlex-only monthly (future-state, no WoS/Scopus needed):
    python ingestion/ingest.py --label 2026-01 \\
        --start 2026-01-01 --end 2026-01-31 \\
        --oa-only

    # Rebuild the Phase-1 baseline (2000–2024):
    python ingestion/ingest.py --label 2000-2024 \\
        --start 2000-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INGESTION_DIR, INTERIM_DIR, OUTPUT_DIR

PY = sys.executable


def _run(cmd: list[str], step_name: str) -> None:
    print(f"\n{'=' * 60}\n>>> {step_name}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(INGESTION_DIR.parent))
    if result.returncode != 0:
        sys.exit(f"Step failed: {step_name}")


def gap_fill_pass() -> None:
    """Compute WoS/Scopus DOIs missing from the OA date-range fetch and refetch
    them via DOI-list mode. Silently skips when there's no WoS/Scopus data
    (the 'OA-only' future-state case).

    Rationale: OpenAlex's country-code search indexes only the first 100
    authors on a work, so multi-country collaborations where the IN/CH author
    is listed deep in the author list get missed. WoS/Scopus use different
    indexing and catch these. Phase 1 went from ~15k works → ~24.9k works
    via this gap-fill.
    """
    oa_path = INTERIM_DIR / "openalex_works.parquet"
    if not oa_path.exists():
        print("[gap-fill] No OA works parquet yet — skipping")
        return

    ws_dois: set[str] = set()
    for name in ("wos.parquet", "scopus.parquet"):
        p = INTERIM_DIR / name
        if not p.exists():
            continue
        df = pl.read_parquet(p)
        if "doi" not in df.columns or df.height == 0:
            continue
        for d in df.select(pl.col("doi").str.to_lowercase()).to_series().drop_nulls().to_list():
            d = d.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            if d:
                ws_dois.add(d)

    if not ws_dois:
        print("[gap-fill] No WoS/Scopus DOIs available — skipping")
        return

    oa_dois = set(
        pl.read_parquet(oa_path).select("doi").to_series().drop_nulls().to_list()
    )
    missing = sorted(ws_dois - oa_dois)
    print(f"[gap-fill] WoS/Scopus DOIs: {len(ws_dois)}; already in OA: {len(ws_dois & oa_dois)}; missing: {len(missing)}")
    if not missing:
        return

    missing_file = INTERIM_DIR / "gap_fill_dois.txt"
    missing_file.write_text("\n".join(missing))

    _run(
        [PY, str(INGESTION_DIR / "02_fetch_openalex.py"),
         "--dois", str(missing_file), "--append"],
        f"Step 02b: gap-fill {len(missing)} DOIs from WoS/Scopus",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="Period label (e.g. 2025)")
    parser.add_argument("--start", required=True, help="Fetch start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Fetch end date YYYY-MM-DD")
    parser.add_argument("--oa-only", action="store_true",
                        help="Skip WoS/Scopus ingest; run OpenAlex-only monthly pattern")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Use interim/openalex_*.parquet already on disk (dev mode)")
    args = parser.parse_args()

    if not args.oa_only:
        _run([PY, str(INGESTION_DIR / "01_ingest_wos_scopus.py")],
             "Step 01: ingest WoS + Scopus")

    if not args.skip_fetch:
        _run([PY, str(INGESTION_DIR / "02_fetch_openalex.py"),
              "--date-range", args.start, args.end],
             f"Step 02: fetch OpenAlex {args.start} → {args.end}")

    if not args.oa_only:
        gap_fill_pass()

    _run([PY, str(INGESTION_DIR / "03_harmonise.py"), "--label", args.label],
         f"Step 03: harmonise (label={args.label})")

    _run([PY, str(INGESTION_DIR / "04_process_authors.py")],
         "Step 04: process authors")

    pubs = OUTPUT_DIR / f"publications_full_dataset_{args.label}.parquet"
    _run([PY, str(INGESTION_DIR / "05_build_duckdb.py"),
          "--publications", str(pubs)],
         "Step 05: build DuckDB")

    print(f"\nPipeline complete. DB: {OUTPUT_DIR / 'indo_swiss_research.duckdb'}")


if __name__ == "__main__":
    main()
