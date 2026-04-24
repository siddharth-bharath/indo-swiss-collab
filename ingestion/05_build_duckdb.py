"""Build DuckDB analytical database from parquet deliverables and topic hierarchy.

Inputs:
  - output/publications_full_dataset_<label>.parquet (step 03)
  - output/work_topic_links.parquet (step 03)
  - output/authors_processed_flat.parquet (step 04)
  - output/authors_summary_with_lists.parquet (step 04)
  - output/work_institution_links.parquet (step 04)
  - openAlex_topics.sqlite (optional; may not exist yet)
  - interim/openalex_authorships.parquet (step 02; for author_position strings)

Outputs:
  - output/indo_swiss_research.duckdb

Per SCHEMAS.md §05 and Metadata/relational_db_documentation.md.
Replicates data_assembly/create_DuckDB.R schema exactly.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM_DIR, OUTPUT_DIR, TOPICS_SQLITE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def strip_id_prefix(value: str, prefix: str) -> int | None:
    """Strip OpenAlex ID prefix (e.g. 'W123' -> 123) and convert to int.

    Args:
        value: ID string, possibly with 'https://openalex.org/' prefix
        prefix: Letter prefix to strip (e.g. 'W', 'A', 'I', 'T', 'F', 'S', 'D')

    Returns:
        Integer ID or None if invalid
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    # Remove URL prefix if present
    if value.startswith("https://openalex.org/"):
        value = value[len("https://openalex.org/"):]

    # Remove letter prefix
    if value.startswith(prefix):
        value = value[len(prefix):]

    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables matching create_DuckDB.R §2."""
    log.info("Creating database schema...")

    # Drop tables in reverse dependency order
    tables_to_drop = [
        "update_log", "work_topics", "work_institutions", "work_author_institutions",
        "work_authors", "author_countries", "author_institutions",
        "funding", "institutions", "works", "authors",
        "topics", "subfields", "fields", "domains"
    ]
    for tbl in tables_to_drop:
        try:
            con.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass

    # Create tables without FK constraints first, then add them via ALTER
    con.execute("""CREATE TABLE domains (
        domain_id BIGINT PRIMARY KEY,
        display_name VARCHAR NOT NULL,
        description VARCHAR,
        works_count INTEGER DEFAULT 0,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE fields (
        field_id BIGINT PRIMARY KEY,
        display_name VARCHAR NOT NULL,
        description VARCHAR,
        works_count INTEGER DEFAULT 0,
        domain_id BIGINT,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE subfields (
        subfield_id BIGINT PRIMARY KEY,
        display_name VARCHAR NOT NULL,
        description VARCHAR,
        works_count INTEGER DEFAULT 0,
        field_id BIGINT,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE topics (
        topic_id BIGINT PRIMARY KEY,
        display_name VARCHAR NOT NULL,
        description VARCHAR,
        works_count INTEGER DEFAULT 0,
        subfield_id BIGINT,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE works (
        work_id BIGINT PRIMARY KEY,
        doi VARCHAR,
        title VARCHAR,
        publication_date VARCHAR,
        publication_year INTEGER,
        document_type VARCHAR,
        cited_by_count INTEGER DEFAULT 0,
        is_oa INTEGER DEFAULT 0,
        source_display_name VARCHAR,
        abstract VARCHAR,
        language VARCHAR,
        volume VARCHAR,
        issue VARCHAR,
        first_page VARCHAR,
        last_page VARCHAR,
        pdf_url VARCHAR,
        landing_page_url VARCHAR,
        author_keywords VARCHAR,
        keywords VARCHAR,
        index_keywords_scopus VARCHAR,
        keywords_plus_wos VARCHAR,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE authors (
        author_id BIGINT PRIMARY KEY,
        display_name VARCHAR NOT NULL,
        orcid VARCHAR,
        works_count INTEGER DEFAULT 0,
        cited_by_count INTEGER DEFAULT 0,
        h_index INTEGER,
        i10_index INTEGER,
        collab_status VARCHAR,
        total_institutions INTEGER DEFAULT 0,
        total_countries INTEGER DEFAULT 0,
        n_corresponding_works INTEGER DEFAULT 0,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE institutions (
        inst_id BIGINT PRIMARY KEY,
        ror VARCHAR,
        display_name VARCHAR NOT NULL,
        country_code VARCHAR,
        type VARCHAR,
        homepage_url VARCHAR,
        image_url VARCHAR,
        thumbnail_url VARCHAR,
        latitude DOUBLE,
        longitude DOUBLE,
        city VARCHAR,
        region VARCHAR,
        works_count INTEGER DEFAULT 0,
        cited_by_count INTEGER DEFAULT 0,
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    con.execute("""CREATE TABLE work_authors (
        work_id BIGINT,
        author_id BIGINT,
        author_position VARCHAR,
        is_corresponding INTEGER DEFAULT 0,
        raw_affiliation_string VARCHAR,
        PRIMARY KEY (work_id, author_id, author_position)
    )""")

    con.execute("""CREATE TABLE work_author_institutions (
        work_id BIGINT,
        author_id BIGINT,
        inst_id BIGINT,
        PRIMARY KEY (work_id, author_id, inst_id)
    )""")

    con.execute("""CREATE TABLE author_institutions (
        author_id BIGINT,
        inst_id BIGINT,
        n_works INTEGER DEFAULT 0,
        PRIMARY KEY (author_id, inst_id)
    )""")

    con.execute("""CREATE TABLE author_countries (
        author_id BIGINT,
        country_code VARCHAR,
        n_works INTEGER DEFAULT 0,
        PRIMARY KEY (author_id, country_code)
    )""")

    con.execute("""CREATE TABLE work_topics (
        work_id BIGINT,
        topic_id BIGINT,
        score DOUBLE,
        is_primary INTEGER DEFAULT 0,
        PRIMARY KEY (work_id, topic_id)
    )""")

    con.execute("""CREATE TABLE work_institutions (
        work_id BIGINT,
        inst_id BIGINT,
        PRIMARY KEY (work_id, inst_id)
    )""")

    con.execute("""CREATE TABLE funding (
        funding_id BIGINT PRIMARY KEY,
        work_id BIGINT,
        funder_name VARCHAR,
        funder_id VARCHAR,
        award_id VARCHAR,
        funding_text VARCHAR
    )""")

    con.execute("""CREATE TABLE update_log (
        update_id BIGINT PRIMARY KEY,
        update_type VARCHAR,
        start_date TIMESTAMP,
        end_date TIMESTAMP,
        records_added INTEGER DEFAULT 0,
        update_source VARCHAR,
        notes VARCHAR
    )""")

    log.info("Schema created successfully")


def load_topic_hierarchy(
    con: duckdb.DuckDBPyConnection, sqlite_path: Path
) -> bool:
    """Load topic hierarchy from openAlex_topics.sqlite if it exists.

    Returns True if loaded, False if file doesn't exist.
    """
    if not sqlite_path.exists():
        log.warning(
            f"Topic hierarchy not found at {sqlite_path}. "
            "Topic tables will be empty. Re-run step 05 once "
            "ingestion/00_build_topic_hierarchy.py completes."
        )
        return False

    log.info(f"Loading topic hierarchy from {sqlite_path}...")

    # Load data using DuckDB's sqlite connector
    try:
        # Load domains
        domains = con.execute(
            f"SELECT * FROM sqlite_scan('{sqlite_path}', 'domains')"
        ).pl()

        if len(domains) > 0:
            domains = domains.with_columns([
                pl.col("domain_id").map_elements(
                    lambda x: strip_id_prefix(x, "D"), return_dtype=pl.Int64
                ).alias("domain_id")
            ])
            con.register("domains_tmp", domains)
            con.execute("INSERT INTO domains SELECT * FROM domains_tmp")
            log.info(f"Loaded {len(domains)} domains")

        # Load fields
        fields = con.execute(
            f"SELECT * FROM sqlite_scan('{sqlite_path}', 'fields')"
        ).pl()

        if len(fields) > 0:
            fields = fields.with_columns([
                pl.col("field_id").map_elements(
                    lambda x: strip_id_prefix(x, "F"), return_dtype=pl.Int64
                ).alias("field_id"),
                pl.col("domain_id").map_elements(
                    lambda x: strip_id_prefix(x, "D"), return_dtype=pl.Int64
                ).alias("domain_id")
            ])
            con.register("fields_tmp", fields)
            con.execute("INSERT INTO fields SELECT * FROM fields_tmp")
            log.info(f"Loaded {len(fields)} fields")

        # Load subfields
        subfields = con.execute(
            f"SELECT * FROM sqlite_scan('{sqlite_path}', 'subfields')"
        ).pl()

        if len(subfields) > 0:
            subfields = subfields.with_columns([
                pl.col("subfield_id").map_elements(
                    lambda x: strip_id_prefix(x, "S"), return_dtype=pl.Int64
                ).alias("subfield_id"),
                pl.col("field_id").map_elements(
                    lambda x: strip_id_prefix(x, "F"), return_dtype=pl.Int64
                ).alias("field_id")
            ])
            con.register("subfields_tmp", subfields)
            con.execute("INSERT INTO subfields SELECT * FROM subfields_tmp")
            log.info(f"Loaded {len(subfields)} subfields")

        # Load topics
        topics = con.execute(
            f"SELECT * FROM sqlite_scan('{sqlite_path}', 'topics')"
        ).pl()

        if len(topics) > 0:
            # Drop cited_by_count if present
            if "cited_by_count" in topics.columns:
                topics = topics.drop("cited_by_count")

            topics = topics.with_columns([
                pl.col("topic_id").map_elements(
                    lambda x: strip_id_prefix(x, "T"), return_dtype=pl.Int64
                ).alias("topic_id"),
                pl.col("subfield_id").map_elements(
                    lambda x: strip_id_prefix(x, "S"), return_dtype=pl.Int64
                ).alias("subfield_id")
            ])
            con.register("topics_tmp", topics)
            con.execute("INSERT INTO topics SELECT * FROM topics_tmp")
            log.info(f"Loaded {len(topics)} topics")

        return True
    except Exception as e:
        log.warning(f"Failed to load topic hierarchy: {e}")
        return False


def load_works(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """Load works from publications_full_dataset parquet. Per create_DuckDB.R §4."""
    log.info(f"Loading works from {parquet_path}...")

    works = pl.read_parquet(parquet_path)
    log.info(f"Read {len(works)} works from parquet")

    # Convert work_id (strip W prefix)
    works = works.with_columns([
        pl.col("work_id").map_elements(
            lambda x: strip_id_prefix(x, "W"), return_dtype=pl.Int64
        ).alias("work_id")
    ])

    # Rename 'document type' to 'document_type'
    if "document type" in works.columns:
        works = works.rename({"document type": "document_type"})

    # Select and order columns per schema (excluding created_date, updated_date which default)
    cols = [
        pl.col("work_id"),
        pl.col("doi"),
        pl.col("title"),
        pl.col("publication_date").cast(pl.Utf8),
        pl.col("publication_year"),
        pl.col("document_type"),
        pl.col("cited_by_count").cast(pl.Int32),
        pl.when(pl.col("is_oa") == True).then(1).otherwise(0).cast(pl.Int32).alias("is_oa"),
        pl.col("source_display_name"),
        pl.col("abstract"),
        pl.lit(None, dtype=pl.Utf8).alias("language"),
        pl.lit(None, dtype=pl.Utf8).alias("volume"),
        pl.lit(None, dtype=pl.Utf8).alias("issue"),
        pl.lit(None, dtype=pl.Utf8).alias("first_page"),
        pl.lit(None, dtype=pl.Utf8).alias("last_page"),
        pl.lit(None, dtype=pl.Utf8).alias("pdf_url"),
        pl.lit(None, dtype=pl.Utf8).alias("landing_page_url"),
    ]

    if "author_keywords" in works.columns:
        cols.append(pl.col("author_keywords"))
    else:
        cols.append(pl.lit(None, dtype=pl.Utf8).alias("author_keywords"))

    if "keywords" in works.columns:
        cols.append(pl.col("keywords"))
    else:
        cols.append(pl.lit(None, dtype=pl.Utf8).alias("keywords"))

    if "index_keywords_scopus" in works.columns:
        cols.append(pl.col("index_keywords_scopus"))
    else:
        cols.append(pl.lit(None, dtype=pl.Utf8).alias("index_keywords_scopus"))

    if "keywords_plus_wos" in works.columns:
        cols.append(pl.col("keywords_plus_wos"))
    else:
        cols.append(pl.lit(None, dtype=pl.Utf8).alias("keywords_plus_wos"))

    works = works.select(cols)

    # Filter out rows with null work_id and dedupe on PK (safety net)
    works = works.filter(pl.col("work_id").is_not_null())
    before = works.height
    works = works.unique(subset=["work_id"], keep="first")
    if works.height < before:
        log.warning(f"Dropped {before - works.height} duplicate work_id rows before insert")

    con.register("works_insert", works)
    con.execute("""INSERT INTO works
    (work_id, doi, title, publication_date, publication_year, document_type,
     cited_by_count, is_oa, source_display_name, abstract, language, volume,
     issue, first_page, last_page, pdf_url, landing_page_url, author_keywords,
     keywords, index_keywords_scopus, keywords_plus_wos)
    SELECT * FROM works_insert""")

    log.info(f"Inserted {len(works)} works")
    return len(works)


def load_authors(
    con: duckdb.DuckDBPyConnection,
    flat_parquet: Path,
    summary_parquet: Path,
) -> int:
    """Load authors from flat + summary parquets. Per create_DuckDB.R §5."""
    log.info(f"Loading authors from {flat_parquet} and {summary_parquet}...")

    # Load flat parquet for minimal author data
    flat = pl.read_parquet(flat_parquet)
    flat = flat.with_columns([
        pl.col("author_id").map_elements(
            lambda x: strip_id_prefix(x, "A"), return_dtype=pl.Int64
        ).alias("author_id")
    ])

    # Dedupe and get minimal author info
    authors = flat.select(["author_id", "display_name"]).unique(subset=["author_id"])

    # Load summary parquet for enrichment
    if summary_parquet.exists():
        summary = pl.read_parquet(summary_parquet)
        summary = summary.with_columns([
            pl.col("author_id").map_elements(
                lambda x: strip_id_prefix(x, "A"), return_dtype=pl.Int64
            ).alias("author_id")
        ])

        # Merge with summary data
        authors = authors.join(
            summary.select([
                "author_id",
                pl.col("orcid"),
                pl.col("nWorks").cast(pl.Int32).alias("works_count"),
                pl.col("collab_status"),
                pl.col("total_institutions").cast(pl.Int32),
                pl.col("total_countries").cast(pl.Int32),
                pl.col("n_corresponding_works").cast(pl.Int32),
            ]),
            on="author_id",
            how="left"
        )
    else:
        log.warning(f"Summary parquet not found at {summary_parquet}; using minimal author data")
        authors = authors.with_columns([
            pl.lit(None, dtype=pl.Utf8).alias("orcid"),
            pl.lit(0, dtype=pl.Int32).alias("works_count"),
            pl.lit(None, dtype=pl.Utf8).alias("collab_status"),
            pl.lit(0, dtype=pl.Int32).alias("total_institutions"),
            pl.lit(0, dtype=pl.Int32).alias("total_countries"),
            pl.lit(0, dtype=pl.Int32).alias("n_corresponding_works"),
        ])

    # Add remaining columns
    authors = authors.with_columns([
        pl.lit(0, dtype=pl.Int32).alias("cited_by_count"),
        pl.lit(None, dtype=pl.Int32).alias("h_index"),
        pl.lit(None, dtype=pl.Int32).alias("i10_index"),
    ])

    # Select and order columns
    authors = authors.select([
        "author_id",
        "display_name",
        "orcid",
        "works_count",
        "cited_by_count",
        "h_index",
        "i10_index",
        "collab_status",
        "total_institutions",
        "total_countries",
        "n_corresponding_works",
    ])

    # Filter out null author_id
    authors = authors.filter(pl.col("author_id").is_not_null())

    con.register("authors_insert", authors)
    con.execute("""INSERT INTO authors
    (author_id, display_name, orcid, works_count, cited_by_count, h_index, i10_index,
     collab_status, total_institutions, total_countries, n_corresponding_works)
    SELECT * FROM authors_insert""")

    log.info(f"Inserted {len(authors)} authors")
    return len(authors)


def load_work_authors(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """Load work_authors from openalex_authorships.parquet (step 02 interim).

    Per create_DuckDB.R §5: uses author_position as first/middle/last strings.
    """
    log.info(f"Loading work_authors from {parquet_path}...")

    if not parquet_path.exists():
        log.warning(f"openalex_authorships.parquet not found; skipping work_authors")
        return 0

    auth = pl.read_parquet(parquet_path)
    auth = auth.with_columns([
        pl.col("work_id").map_elements(
            lambda x: strip_id_prefix(x, "W"), return_dtype=pl.Int64
        ).alias("work_id"),
        pl.col("author_id").map_elements(
            lambda x: strip_id_prefix(x, "A"), return_dtype=pl.Int64
        ).alias("author_id"),
    ])

    # Convert is_corresponding to int
    auth = auth.with_columns([
        pl.when(pl.col("is_corresponding") == True).then(1).otherwise(0).cast(pl.Int32).alias("is_corresponding")
    ])

    # Select columns
    auth = auth.select([
        "work_id",
        "author_id",
        "author_position",
        "is_corresponding",
        pl.col("affiliation_raw").alias("raw_affiliation_string"),
    ])

    # Filter nulls
    auth = auth.filter(
        (pl.col("work_id").is_not_null()) &
        (pl.col("author_id").is_not_null()) &
        (pl.col("author_position").is_not_null())
    )

    # Dedupe by PK
    auth = auth.unique(subset=["work_id", "author_id", "author_position"])

    if len(auth) > 0:
        con.register("work_authors_insert", auth)
        con.execute("INSERT INTO work_authors SELECT * FROM work_authors_insert")
        log.info(f"Inserted {len(auth)} work-author relationships")

    return len(auth)


def load_institutions_and_links(
    con: duckdb.DuckDBPyConnection, wil_parquet: Path
) -> tuple[int, int]:
    """Load institutions and work_institutions from work_institution_links.

    Per create_DuckDB.R §6a.
    Returns (n_institutions, n_work_institutions).
    """
    log.info(f"Loading institutions from {wil_parquet}...")

    if not wil_parquet.exists():
        log.warning(f"work_institution_links.parquet not found")
        return 0, 0

    wil = pl.read_parquet(wil_parquet)
    wil = wil.with_columns([
        pl.col("work_id").map_elements(
            lambda x: strip_id_prefix(x, "W"), return_dtype=pl.Int64
        ).alias("work_id"),
        pl.col("inst_id").map_elements(
            lambda x: strip_id_prefix(x, "I"), return_dtype=pl.Int64
        ).alias("inst_id"),
    ])

    # Aggregate institutions per inst_id (take first non-null of each field)
    insts = wil.filter(pl.col("inst_id").is_not_null()).group_by("inst_id").agg([
        pl.col("ror").first().alias("ror"),
        pl.col("institution_name").first().alias("display_name"),
        pl.col("country_code").first().alias("country_code"),
    ]).select([
        "inst_id",
        "ror",
        "display_name",
        "country_code",
    ])

    n_insts = len(insts)
    if n_insts > 0:
        con.register("institutions_insert", insts)
        con.execute("""INSERT INTO institutions
        (inst_id, ror, display_name, country_code)
        SELECT inst_id, ror, display_name, country_code FROM institutions_insert""")
        log.info(f"Inserted {n_insts} institutions")

    # Load work_institutions
    work_insts = wil.select([
        "work_id",
        "inst_id",
    ]).unique()

    n_wi = len(work_insts)
    if n_wi > 0:
        con.register("work_institutions_insert", work_insts)
        con.execute("INSERT INTO work_institutions SELECT * FROM work_institutions_insert")
        log.info(f"Inserted {n_wi} work-institution relationships")

    return n_insts, n_wi


def load_work_topics(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> int:
    """Load work_topics from work_topic_links.parquet. Per create_DuckDB.R §7."""
    log.info(f"Loading work_topics from {parquet_path}...")

    if not parquet_path.exists():
        log.warning(f"work_topic_links.parquet not found")
        return 0

    wt = pl.read_parquet(parquet_path)
    wt = wt.with_columns([
        pl.col("work_id").map_elements(
            lambda x: strip_id_prefix(x, "W"), return_dtype=pl.Int64
        ).alias("work_id"),
        pl.col("topic_id").map_elements(
            lambda x: strip_id_prefix(x, "T"), return_dtype=pl.Int64
        ).alias("topic_id"),
    ])

    # Standardize column names
    if "topic_score" in wt.columns:
        wt = wt.rename({"topic_score": "score"})

    wt = wt.select([
        "work_id",
        "topic_id",
        pl.col("score").cast(pl.Float64),
        pl.lit(0, dtype=pl.Int32).alias("is_primary"),
    ])

    # Filter nulls
    wt = wt.filter(
        (pl.col("work_id").is_not_null()) &
        (pl.col("topic_id").is_not_null())
    )

    if len(wt) > 0:
        con.register("work_topics_insert", wt)
        con.execute("INSERT INTO work_topics SELECT * FROM work_topics_insert")
        log.info(f"Inserted {len(wt)} work-topic relationships")

    return len(wt)


def create_indexes(con: duckdb.DuckDBPyConnection) -> None:
    """Create indexes per create_DuckDB.R §8."""
    log.info("Creating indexes...")

    indexes = [
        "CREATE INDEX idx_work_year ON works(publication_year)",
        "CREATE INDEX idx_work_doi ON works(doi)",
        "CREATE INDEX idx_work_cited ON works(cited_by_count)",
        "CREATE INDEX idx_work_author_keywords ON works(author_keywords)",
        "CREATE INDEX idx_work_keywords ON works(keywords)",
        "CREATE INDEX idx_work_index_keywords_scopus ON works(index_keywords_scopus)",
        "CREATE INDEX idx_work_keywords_plus_wos ON works(keywords_plus_wos)",
        "CREATE INDEX idx_author_name ON authors(display_name)",
        "CREATE INDEX idx_author_collab ON authors(collab_status)",
        "CREATE INDEX idx_ai_author ON author_institutions(author_id)",
        "CREATE INDEX idx_ai_inst ON author_institutions(inst_id)",
        "CREATE INDEX idx_ac_author ON author_countries(author_id)",
        "CREATE INDEX idx_ac_country ON author_countries(country_code)",
        "CREATE INDEX idx_inst_country ON institutions(country_code)",
        "CREATE INDEX idx_inst_name ON institutions(display_name)",
        "CREATE INDEX idx_inst_ror ON institutions(ror)",
        "CREATE INDEX idx_wa_work ON work_authors(work_id)",
        "CREATE INDEX idx_wa_author ON work_authors(author_id)",
        "CREATE INDEX idx_wai_work ON work_author_institutions(work_id)",
        "CREATE INDEX idx_wai_author ON work_author_institutions(author_id)",
        "CREATE INDEX idx_wai_inst ON work_author_institutions(inst_id)",
        "CREATE INDEX idx_wi_work ON work_institutions(work_id)",
        "CREATE INDEX idx_wi_inst ON work_institutions(inst_id)",
        "CREATE INDEX idx_wt_work ON work_topics(work_id)",
        "CREATE INDEX idx_wt_topic ON work_topics(topic_id)",
    ]

    for idx in indexes:
        try:
            con.execute(idx)
        except Exception as e:
            log.debug(f"Index creation note: {e}")

    log.info("Indexes created")


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    """Create views per create_DuckDB.R §9."""
    log.info("Creating analytical views...")

    con.execute("DROP VIEW IF EXISTS indo_swiss_works")
    con.execute("""
    CREATE VIEW indo_swiss_works AS
    SELECT DISTINCT w.*
    FROM works w
    JOIN work_institutions wi ON w.work_id = wi.work_id
    JOIN institutions i ON wi.inst_id = i.inst_id
    WHERE EXISTS (
        SELECT 1 FROM work_institutions wi2
        JOIN institutions i2 ON wi2.inst_id = i2.inst_id
        WHERE wi2.work_id = w.work_id AND i2.country_code = 'IN'
    )
    AND EXISTS (
        SELECT 1 FROM work_institutions wi3
        JOIN institutions i3 ON wi3.inst_id = i3.inst_id
        WHERE wi3.work_id = w.work_id AND i3.country_code = 'CH'
    )
    """)

    con.execute("DROP VIEW IF EXISTS topic_hierarchy")
    con.execute("""
    CREATE VIEW topic_hierarchy AS
    SELECT
        t.topic_id,
        t.display_name as topic_name,
        t.works_count as topic_works_count,
        s.subfield_id,
        s.display_name as subfield_name,
        s.works_count as subfield_works_count,
        f.field_id,
        f.display_name as field_name,
        f.works_count as field_works_count,
        d.domain_id,
        d.display_name as domain_name,
        d.works_count as domain_works_count
    FROM topics t
    JOIN subfields s ON t.subfield_id = s.subfield_id
    JOIN fields f ON s.field_id = f.field_id
    JOIN domains d ON f.domain_id = d.domain_id
    """)

    con.execute("DROP VIEW IF EXISTS work_with_topics")
    con.execute("""
    CREATE VIEW work_with_topics AS
    SELECT w.work_id, w.title, wt.topic_id, t.display_name AS topic_name, wt.score
    FROM works w
    JOIN work_topics wt ON w.work_id = wt.work_id
    JOIN topics t ON wt.topic_id = t.topic_id
    """)

    log.info("Views created")


def log_update(con: duckdb.DuckDBPyConnection, works_count: int) -> None:
    """Log the build to update_log. Per create_DuckDB.R §10."""
    start_date = datetime.now()

    con.execute("""
    INSERT INTO update_log
    (update_id, update_type, start_date, end_date, records_added, update_source, notes)
    VALUES (1, 'initial_load', ?, ?, ?, 'parquet_ingestion_pipeline_python',
            'Full rebuild from Python ingestion pipeline')
    """, [start_date, start_date, works_count])

    log.info("Update log entry created")


def _explode_affiliations(flat_path: Path) -> pl.DataFrame:
    """Explode authors_processed_flat.affiliations into one row per (work, author, inst)."""
    import json as _json
    df = pl.read_parquet(flat_path)
    records: list[dict] = []
    for row in df.select(["work_id", "author_id", "affiliations"]).iter_rows(named=True):
        aff_json = row["affiliations"]
        if not aff_json:
            continue
        try:
            affs = _json.loads(aff_json)
        except (TypeError, ValueError):
            continue
        for aff in affs:
            if not isinstance(aff, dict):
                continue
            inst_id = aff.get("inst_id")
            if not inst_id:
                continue
            records.append({
                "work_id": row["work_id"],
                "author_id": row["author_id"],
                "inst_id": inst_id,
                "country_code": aff.get("country_code"),
            })
    if not records:
        return pl.DataFrame({
            "work_id": pl.Series(dtype=pl.Int64),
            "author_id": pl.Series(dtype=pl.Int64),
            "inst_id": pl.Series(dtype=pl.Int64),
            "country_code": pl.Series(dtype=pl.String),
        })
    return pl.DataFrame(records).with_columns([
        pl.col("work_id").map_elements(lambda x: strip_id_prefix(x, "W"), return_dtype=pl.Int64),
        pl.col("author_id").map_elements(lambda x: strip_id_prefix(x, "A"), return_dtype=pl.Int64),
        pl.col("inst_id").map_elements(lambda x: strip_id_prefix(x, "I"), return_dtype=pl.Int64),
    ]).filter(
        pl.col("work_id").is_not_null()
        & pl.col("author_id").is_not_null()
        & pl.col("inst_id").is_not_null()
    )


def load_author_inst_aggregates(con: duckdb.DuckDBPyConnection, flat_parquet: Path) -> None:
    """Populate work_author_institutions, author_institutions, author_countries.
    Per create_DuckDB.R §6b. All derived from the exploded authorship affiliations."""
    if not flat_parquet.exists():
        log.warning(f"Flat authorships parquet not found: {flat_parquet}; skipping author aggregates")
        return
    log.info("Building author-institution aggregates from authors_processed_flat...")
    exp = _explode_affiliations(flat_parquet)
    if exp.height == 0:
        log.warning("No author-institution records after explosion; tables left empty")
        return

    con.register("exp_aff", exp)

    # Restrict to FK-valid rows
    con.execute("""
        CREATE OR REPLACE TEMP TABLE exp_valid AS
        SELECT e.* FROM exp_aff e
        WHERE e.work_id IN (SELECT work_id FROM works)
          AND e.author_id IN (SELECT author_id FROM authors)
          AND e.inst_id IN (SELECT inst_id FROM institutions)
    """)

    wai = con.execute("""
        INSERT INTO work_author_institutions (work_id, author_id, inst_id)
        SELECT DISTINCT work_id, author_id, inst_id FROM exp_valid
        RETURNING *
    """).fetchall()
    log.info(f"Inserted {len(wai)} work_author_institutions rows")

    ai = con.execute("""
        INSERT INTO author_institutions (author_id, inst_id, n_works)
        SELECT author_id, inst_id, COUNT(DISTINCT work_id)
        FROM exp_valid
        GROUP BY author_id, inst_id
        RETURNING *
    """).fetchall()
    log.info(f"Inserted {len(ai)} author_institutions rows")

    ac = con.execute("""
        INSERT INTO author_countries (author_id, country_code, n_works)
        SELECT author_id, country_code, COUNT(DISTINCT work_id)
        FROM exp_valid
        WHERE country_code IS NOT NULL AND country_code <> ''
        GROUP BY author_id, country_code
        RETURNING *
    """).fetchall()
    log.info(f"Inserted {len(ac)} author_countries rows")


def load_funding(con: duckdb.DuckDBPyConnection, publications_parquet: Path) -> None:
    """Populate funding table from the grants JSON column in publications_full_dataset.
    One row per (work, grant). Per create_DuckDB.R schema."""
    import json as _json
    log.info(f"Extracting funding records from grants JSON in {publications_parquet.name}...")
    df = pl.read_parquet(publications_parquet)
    records: list[dict] = []
    fid = 1
    for row in df.select(["work_id", "grants"]).iter_rows(named=True):
        grants_json = row["grants"]
        if not grants_json:
            continue
        try:
            grants = _json.loads(grants_json)
        except (TypeError, ValueError):
            continue
        wid = strip_id_prefix(row["work_id"], "W")
        if wid is None:
            continue
        for g in grants:
            if not isinstance(g, dict):
                continue
            records.append({
                "funding_id": fid,
                "work_id": wid,
                "funder_name": g.get("funder_display_name") or g.get("funder"),
                "funder_id": g.get("funder"),
                "award_id": g.get("award_id"),
                "funding_text": None,
            })
            fid += 1
    if not records:
        log.info("No grant records to insert")
        return

    f_df = pl.DataFrame(records)
    # Filter to FK-valid work_ids
    con.register("f_df", f_df)
    con.execute("""
        INSERT INTO funding (funding_id, work_id, funder_name, funder_id, award_id, funding_text)
        SELECT funding_id, work_id, funder_name, funder_id, award_id, funding_text
        FROM f_df
        WHERE work_id IN (SELECT work_id FROM works)
    """)
    log.info(f"Inserted {len(records)} funding rows")


def find_latest_publications(output_dir: Path) -> Path:
    """Find most recent publications_full_dataset_*.parquet in output_dir."""
    pattern = "publications_full_dataset_*.parquet"
    matches = list(output_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No {pattern} found in {output_dir}")

    latest = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    log.info(f"Found latest publications file: {latest.name}")
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build DuckDB analytical database from parquet deliverables"
    )
    parser.add_argument(
        "--publications",
        type=Path,
        help="Path to publications_full_dataset parquet (default: auto-detect most recent)",
    )
    parser.add_argument(
        "--topics-db",
        type=Path,
        default=TOPICS_SQLITE,
        help="Path to openAlex_topics.sqlite (default: from config)",
    )
    args = parser.parse_args()

    # Determine publications file
    if args.publications:
        publications_parquet = args.publications
    else:
        publications_parquet = find_latest_publications(OUTPUT_DIR)

    if not publications_parquet.exists():
        log.error(f"Publications parquet not found: {publications_parquet}")
        sys.exit(1)

    log.info("=" * 60)
    log.info("Building indo_swiss_research.duckdb")
    log.info("=" * 60)

    # Open DuckDB connection
    db_path = OUTPUT_DIR / "indo_swiss_research.duckdb"
    log.info(f"Database path: {db_path}")

    con = duckdb.connect(str(db_path))

    try:
        # 1. Create schema
        create_schema(con)

        # 2. Load topic hierarchy (if available)
        load_topic_hierarchy(con, args.topics_db)

        # 3. Load works
        works_count = load_works(con, publications_parquet)

        # 4. Load authors
        load_authors(con, OUTPUT_DIR / "authors_processed_flat.parquet",
                     OUTPUT_DIR / "authors_summary_with_lists.parquet")

        # 5. Load work_authors (use step 02 interim openalex_authorships)
        load_work_authors(con, INTERIM_DIR / "openalex_authorships.parquet")

        # 6. Load institutions and work_institutions
        load_institutions_and_links(con, OUTPUT_DIR / "work_institution_links.parquet")

        # 7. Load work_topics
        load_work_topics(con, OUTPUT_DIR / "work_topic_links.parquet")

        # 7b. Load author-institution/country aggregates + funding
        load_author_inst_aggregates(con, OUTPUT_DIR / "authors_processed_flat.parquet")
        load_funding(con, publications_parquet)

        # 8. Create indexes
        create_indexes(con)

        # 9. Create views
        create_views(con)

        # 10. Log update
        log_update(con, works_count)

        con.close()

        log.info("=" * 60)
        log.info(f"Database build complete: {db_path}")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"Error during database build: {e}", exc_info=True)
        con.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
