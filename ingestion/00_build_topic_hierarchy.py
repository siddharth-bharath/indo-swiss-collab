"""Build the OpenAlex topics hierarchy SQLite DB.

Port of data_assembly/extract_openAlex_topics.r. Queries the OpenAlex /topics
endpoint for all ~4,500 topics and derives the domains/fields/subfields
hierarchy from their nested metadata. One-time / occasional refresh — topics
change slowly.

Output: openAlex_topics.sqlite at repo root (4 tables: domains, fields,
subfields, topics).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OPENALEX_MAILTO, TOPICS_SQLITE

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OA_BASE = "https://api.openalex.org"
PER_PAGE = 200


def _strip(s: str | None) -> str | None:
    if not s:
        return s
    for prefix in ("https://openalex.org/domains/", "https://openalex.org/fields/",
                   "https://openalex.org/subfields/", "https://openalex.org/topics/",
                   "https://openalex.org/"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def fetch_all_topics(client: httpx.Client) -> list[dict]:
    """Cursor-paginate through the /topics endpoint."""
    meta = client.get(f"{OA_BASE}/topics", params={
        "per-page": 1, "mailto": OPENALEX_MAILTO
    }, timeout=30).json()
    total = meta.get("meta", {}).get("count", 0)
    logger.info(f"OpenAlex reports {total} topics")

    results: list[dict] = []
    cursor = "*"
    with tqdm(total=total, desc="Fetching topics") as bar:
        while cursor:
            r = client.get(f"{OA_BASE}/topics", params={
                "per-page": PER_PAGE,
                "cursor": cursor,
                "mailto": OPENALEX_MAILTO,
                "sort": "works_count:desc",
            }, timeout=60)
            r.raise_for_status()
            data = r.json()
            batch = data.get("results", [])
            results.extend(batch)
            bar.update(len(batch))
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor or not batch:
                break
            time.sleep(0.1)
    return results


def extract_hierarchy(topics: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Derive unique domains/fields/subfields from topics' nested metadata."""
    domains: dict[str, dict] = {}
    fields: dict[str, dict] = {}
    subfields: dict[str, dict] = {}
    topic_rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for t in topics:
        d = t.get("domain") or {}
        f = t.get("field") or {}
        s = t.get("subfield") or {}

        d_id = _strip(d.get("id"))
        f_id = _strip(f.get("id"))
        s_id = _strip(s.get("id"))
        t_id = _strip(t.get("id"))

        if d_id and d_id not in domains:
            domains[d_id] = {
                "domain_id": d_id,
                "display_name": d.get("display_name"),
                "description": d.get("description"),
                "works_count": d.get("works_count", 0) or 0,
                "created_date": now,
                "updated_date": now,
            }
        if f_id and f_id not in fields:
            fields[f_id] = {
                "field_id": f_id,
                "display_name": f.get("display_name"),
                "description": f.get("description"),
                "works_count": f.get("works_count", 0) or 0,
                "domain_id": d_id,
                "created_date": now,
                "updated_date": now,
            }
        if s_id and s_id not in subfields:
            subfields[s_id] = {
                "subfield_id": s_id,
                "display_name": s.get("display_name"),
                "description": s.get("description"),
                "works_count": s.get("works_count", 0) or 0,
                "field_id": f_id,
                "created_date": now,
                "updated_date": now,
            }
        if t_id:
            topic_rows.append({
                "topic_id": t_id,
                "display_name": t.get("display_name"),
                "description": t.get("description"),
                "works_count": t.get("works_count", 0) or 0,
                "cited_by_count": t.get("cited_by_count", 0) or 0,
                "subfield_id": s_id,
                "created_date": now,
                "updated_date": now,
            })

    return list(domains.values()), list(fields.values()), list(subfields.values()), topic_rows


def build_sqlite(domains, fields, subfields, topics, db_path: Path) -> None:
    """Create the 4-table topic hierarchy DB. Matches the R schema."""
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE domains (
      domain_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      works_count INTEGER DEFAULT 0,
      created_date TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_date TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE fields (
      field_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      works_count INTEGER DEFAULT 0,
      domain_id TEXT,
      created_date TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_date TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (domain_id) REFERENCES domains(domain_id)
    );
    CREATE TABLE subfields (
      subfield_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      works_count INTEGER DEFAULT 0,
      field_id TEXT,
      created_date TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_date TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (field_id) REFERENCES fields(field_id)
    );
    CREATE TABLE topics (
      topic_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      description TEXT,
      works_count INTEGER DEFAULT 0,
      cited_by_count INTEGER DEFAULT 0,
      subfield_id TEXT,
      created_date TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_date TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (subfield_id) REFERENCES subfields(subfield_id)
    );
    """)

    def _insert_many(table: str, rows: list[dict]) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(cols))
        q = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        cur.executemany(q, [tuple(r[c] for c in cols) for r in rows])

    _insert_many("domains", domains)
    _insert_many("fields", fields)
    _insert_many("subfields", subfields)
    _insert_many("topics", topics)

    con.commit()
    con.close()
    logger.info(
        f"Wrote {db_path}: "
        f"{len(domains)} domains, {len(fields)} fields, "
        f"{len(subfields)} subfields, {len(topics)} topics"
    )


def main() -> None:
    with httpx.Client() as client:
        raw_topics = fetch_all_topics(client)
    domains, fields, subfields, topics = extract_hierarchy(raw_topics)
    build_sqlite(domains, fields, subfields, topics, TOPICS_SQLITE)


if __name__ == "__main__":
    main()
