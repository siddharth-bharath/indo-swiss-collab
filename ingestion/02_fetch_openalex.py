"""Fetch publication metadata from OpenAlex for Indo-Swiss collaborations.

Two modes:
- Date range: works with ≥1 IN author AND ≥1 CH author in a time window
- DOI list: fetch specific works by DOI (OR across the list)

This is the strategic core of the pipeline. When WoS+Scopus are retired
(see CLAUDE.md), it runs standalone monthly.

Implementation notes:
- Uses httpx directly rather than pyalex. pyalex's filter builder cannot
  emit the AND-on-same-filter URL that OpenAlex requires for the
  "author in IN AND author in CH" semantics (verified: pyalex produces
  `country_code:in+ch`, which OpenAlex treats as malformed).
- Handles cursor pagination (cursor=*).
- Handles the 100-author truncation by per-work refetch.
- Reconstructs abstracts from abstract_inverted_index.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import httpx
import polars as pl
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM_DIR, OPENALEX_MAILTO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OA_BASE = "https://api.openalex.org"
# Note: not using a `select=` param because OpenAlex currently rejects `grants`
# as a selectable field even though it returns grants data by default.
# Full records cost ~30KB each × ~25K works/year ≈ 750MB per full pull —
# acceptable for an annual (or monthly OA-only) job.
PER_PAGE = 200
DOI_BATCH = 50

_URL_PREFIXES = re.compile(
    r"https://(openalex\.org|ror\.org|doi\.org|orcid\.org)/"
)


# ---------- cleaning helpers ----------

def clean_id(value: str | None) -> str | None:
    if value is None or not isinstance(value, str):
        return value
    return _URL_PREFIXES.sub("", value)


def strip_urls_in_json(obj: Any) -> Any:
    """Recursively strip URL prefixes from string values in a JSON-serializable
    structure. Does NOT rename any keys."""
    if isinstance(obj, dict):
        return {k: strip_urls_in_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_urls_in_json(x) for x in obj]
    if isinstance(obj, str):
        return _URL_PREFIXES.sub("", obj)
    return obj


def normalize_institution_for_affiliations(inst: dict) -> dict:
    """Shape a single OpenAlex institution dict to match R openalexR's
    `affiliations` nested-tibble convention: id → inst_id, strip URL prefixes."""
    out = {
        "inst_id": clean_id(inst.get("id")),
        "display_name": inst.get("display_name"),
        "ror": clean_id(inst.get("ror")),
        "country_code": inst.get("country_code"),
        "type": inst.get("type"),
    }
    lineage = inst.get("lineage")
    if lineage:
        out["lineage"] = [clean_id(x) for x in lineage]
    return out


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    max_pos = max(
        (p for positions in inverted_index.values() for p in positions),
        default=-1,
    )
    if max_pos < 0:
        return None
    tokens = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            if 0 <= pos <= max_pos:
                tokens[pos] = word
    result = " ".join(tokens).strip()
    return result or None


# ---------- normalization ----------

def normalize_work(work: dict) -> dict:
    """Flatten a raw OpenAlex work dict into the step-02 works schema."""
    primary_location = work.get("primary_location") or {}
    source_info = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}

    return {
        "work_id": clean_id(work.get("id")),
        "doi": (clean_id(work.get("doi")) or "").lower() or None,
        "title": work.get("title"),
        "display_name": work.get("display_name"),
        "publication_date": work.get("publication_date"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count", 0),
        "type": (work.get("type") or "").lower() or None,
        "is_oa": open_access.get("is_oa"),
        "is_retracted": work.get("is_retracted", False),
        "source_display_name": source_info.get("display_name"),
        "source_id": clean_id(source_info.get("id")),
        "issn_l": source_info.get("issn_l"),
        "host_organization": clean_id(source_info.get("host_organization")),
        "host_organization_name": source_info.get("host_organization_name"),
        "landing_page_url": primary_location.get("landing_page_url"),
        "pdf_url": primary_location.get("pdf_url"),
        "license": primary_location.get("license"),
        "version": primary_location.get("version"),
        "primary_location": _json(strip_urls_in_json(work.get("primary_location"))),
        "ids": _json(strip_urls_in_json(work.get("ids"))),
        "topics": _json(strip_urls_in_json(work.get("topics"))),
        "keywords": _json(strip_urls_in_json(work.get("keywords"))),
        "grants": _json(strip_urls_in_json(work.get("grants"))),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "countries_distinct_count": work.get("countries_distinct_count", 0),
        "institutions_distinct_count": work.get("institutions_distinct_count", 0),
        "is_authors_truncated": work.get("is_authors_truncated", False),
    }


def _json(obj: Any) -> str | None:
    if obj is None or obj == [] or obj == {}:
        return None
    return json.dumps(obj, default=str, ensure_ascii=False)


def extract_authorships(work: dict) -> list[dict]:
    """One row per (work_id, author). `affiliations` JSON holds the expanded
    institution objects (matches R openalexR convention)."""
    work_id = clean_id(work.get("id"))
    rows = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        institutions = authorship.get("institutions") or []
        affiliations_norm = [normalize_institution_for_affiliations(i) for i in institutions]

        raw_strings = authorship.get("raw_affiliation_strings") or []
        affiliation_raw = "; ".join(s for s in raw_strings if s) or None

        rows.append({
            "work_id": work_id,
            "author_id": clean_id(author.get("id")),
            "display_name": author.get("display_name"),
            "orcid": clean_id(author.get("orcid")),
            "author_position": authorship.get("author_position"),
            "is_corresponding": authorship.get("is_corresponding", False),
            "affiliations": _json(affiliations_norm),
            "affiliation_raw": affiliation_raw,
        })
    return rows


# ---------- HTTP layer ----------

def _oa_get(client: httpx.Client, path: str, params: dict) -> dict:
    """GET with mailto, with retry-on-429 (2 retries, exponential backoff)."""
    params = {**params, "mailto": OPENALEX_MAILTO}
    for attempt in range(3):
        try:
            r = client.get(f"{OA_BASE}{path}", params=params, timeout=60.0)
            if r.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"429 rate limited; sleeping {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning(f"HTTP error {e}; retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _paginate(client: httpx.Client, filter_str: str) -> Iterator[dict]:
    """Cursor-pagination iterator over /works with a filter string."""
    cursor: str | None = "*"
    while cursor:
        data = _oa_get(client, "/works", {
            "filter": filter_str,
            "per-page": PER_PAGE,
            "cursor": cursor,
        })
        for work in data.get("results", []):
            yield work
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            return
        time.sleep(0.1)


def _refetch_authorships(client: httpx.Client, work_id: str) -> list[dict]:
    """Fetch full authorships for a work whose list was truncated at 100."""
    data = _oa_get(client, f"/works/{work_id}", {"select": "id,authorships"})
    return data.get("authorships") or []


def _patch_truncated(client: httpx.Client, works: list[dict]) -> list[dict]:
    to_fix: list[int] = []
    for i, w in enumerate(works):
        auths = w.get("authorships") or []
        if w.get("is_authors_truncated") or len(auths) >= 100:
            to_fix.append(i)
    if not to_fix:
        return works
    logger.info(f"Refetching full authorships for {len(to_fix)} truncated works")
    for i in tqdm(to_fix, desc="Refetch truncated"):
        wid = clean_id(works[i].get("id"))
        if not wid:
            continue
        try:
            works[i]["authorships"] = _refetch_authorships(client, wid)
        except Exception as e:
            logger.warning(f"Refetch failed for {wid}: {e}")
        time.sleep(0.1)
    return works


# ---------- fetch modes ----------

def fetch_by_date_range(start: str, end: str) -> tuple[list[dict], list[dict]]:
    filter_str = (
        f"authorships.institutions.country_code:in,"
        f"authorships.institutions.country_code:ch,"
        f"from_publication_date:{start},"
        f"to_publication_date:{end}"
    )
    logger.info(f"Fetching IN+CH collab works: {start} to {end}")

    with httpx.Client() as client:
        meta = _oa_get(client, "/works", {"filter": filter_str, "per-page": 1})
        total = meta.get("meta", {}).get("count", 0)
        logger.info(f"OpenAlex reports {total} matching works for this window")

        works: list[dict] = []
        with tqdm(total=total, desc="Fetching works", unit="work") as bar:
            for w in _paginate(client, filter_str):
                works.append(w)
                bar.update(1)

        # Checkpoint before the slow per-work refetch: if that phase is killed
        # we still have usable output covering ~90% of works (all except those
        # with >100 authors where the author list is truncated at 100).
        _write_parquets(works, suffix="_prerefetch")

        works = _patch_truncated(client, works)

    works_rows = [normalize_work(w) for w in works]
    auth_rows = [a for w in works for a in extract_authorships(w)]
    return works_rows, auth_rows


def _write_parquets(works: list[dict], suffix: str = "") -> None:
    """Intermediate write used as a checkpoint before the truncation refetch phase."""
    works_rows = [normalize_work(w) for w in works]
    auth_rows = [a for w in works for a in extract_authorships(w)]
    wp = INTERIM_DIR / f"openalex_works{suffix}.parquet"
    ap = INTERIM_DIR / f"openalex_authorships{suffix}.parquet"
    if works_rows:
        pl.DataFrame(works_rows).write_parquet(wp)
        logger.info(f"Checkpoint: wrote {len(works_rows)} works → {wp.name}")
    if auth_rows:
        pl.DataFrame(auth_rows).write_parquet(ap)
        logger.info(f"Checkpoint: wrote {len(auth_rows)} authorships → {ap.name}")


def fetch_by_dois(doi_file: Path) -> tuple[list[dict], list[dict]]:
    with open(doi_file) as f:
        dois = [clean_id(line.strip().lower()) for line in f if line.strip()]
    dois = [d for d in dois if d]
    logger.info(f"Loaded {len(dois)} DOIs")

    batches = [dois[i:i + DOI_BATCH] for i in range(0, len(dois), DOI_BATCH)]
    works: list[dict] = []
    failures: list[str] = []

    with httpx.Client() as client:
        for batch in tqdm(batches, desc="DOI batches"):
            filter_str = "doi:" + "|".join(batch)
            try:
                for w in _paginate(client, filter_str):
                    works.append(w)
            except Exception as e:
                logger.warning(f"Batch failed ({len(batch)} DOIs): {e}")
                failures.extend(batch)
            time.sleep(0.2)

        works = _patch_truncated(client, works)

    if failures:
        fail_file = INTERIM_DIR / "openalex_failures.txt"
        fail_file.write_text("\n".join(failures))
        logger.warning(f"{len(failures)} DOIs failed; logged to {fail_file}")

    works_rows = [normalize_work(w) for w in works]
    auth_rows = [a for w in works for a in extract_authorships(w)]
    return works_rows, auth_rows


# ---------- CLI ----------

def _write_output(works_rows: list[dict], auth_rows: list[dict], append: bool) -> None:
    """Write to interim parquets. In `append` mode, merge with existing files:
    works are deduped by work_id (keep newest); authorships for any work_id we
    refetched are fully replaced with the new authorship rows."""
    works_path = INTERIM_DIR / "openalex_works.parquet"
    auth_path = INTERIM_DIR / "openalex_authorships.parquet"
    new_works = pl.DataFrame(works_rows) if works_rows else None
    new_auths = pl.DataFrame(auth_rows) if auth_rows else None

    if append and works_path.exists() and new_works is not None:
        existing = pl.read_parquet(works_path)
        combined = pl.concat([existing, new_works], how="diagonal_relaxed")
        combined = combined.unique(subset=["work_id"], keep="last")
        combined.write_parquet(works_path)
        logger.info(f"Appended: {new_works.height} new / {combined.height} total works → {works_path}")
    elif new_works is not None:
        new_works.write_parquet(works_path)
        logger.info(f"Wrote {new_works.height} works → {works_path}")
    else:
        logger.warning("No works to write")

    if append and auth_path.exists() and new_auths is not None:
        existing = pl.read_parquet(auth_path)
        refetched_work_ids = set(new_auths["work_id"].to_list())
        kept = existing.filter(~pl.col("work_id").is_in(list(refetched_work_ids)))
        combined = pl.concat([kept, new_auths], how="diagonal_relaxed")
        combined.write_parquet(auth_path)
        logger.info(f"Appended: {new_auths.height} new / {combined.height} total authorships → {auth_path}")
    elif new_auths is not None:
        new_auths.write_parquet(auth_path)
        logger.info(f"Wrote {new_auths.height} authorships → {auth_path}")
    else:
        logger.warning("No authorships to write")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date-range", nargs=2, metavar=("START", "END"),
                       help="YYYY-MM-DD start/end dates")
    group.add_argument("--dois", type=Path, help="File with one DOI per line")
    parser.add_argument("--append", action="store_true",
                        help="Merge with existing interim parquets instead of overwriting")
    args = parser.parse_args()

    if args.date_range:
        works_rows, auth_rows = fetch_by_date_range(*args.date_range)
    else:
        works_rows, auth_rows = fetch_by_dois(args.dois)

    _write_output(works_rows, auth_rows, append=args.append)


if __name__ == "__main__":
    main()
