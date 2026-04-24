"""Build DuckDB dev database from v1 parquets for testing.

Inputs:
  - search-application/data/publications_full_dataset_2000-2024.parquet
  - search-application/data/institutional_relationships_IN_CH.parquet (for country_code)
  - search-application/data/authors_summary_in_ch.parquet (for collab_status)

Outputs:
  - search-application-v2/dev_data/indo_swiss_research_dev.duckdb
"""

import sys
from pathlib import Path

import duckdb
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEARCH_APP_DATA = PROJECT_ROOT / "search-application" / "data"
DEV_DB_PATH = Path(__file__).resolve().parent.parent / "dev_data" / "indo_swiss_research_dev.duckdb"


def strip_id_prefix(value, prefix):
    """Strip OpenAlex ID prefix (e.g. 'W123' -> 123) and return as int."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if value.startswith("https://openalex.org/"):
        value = value[len("https://openalex.org/"):]
    if value.startswith(prefix):
        value = value[len(prefix):]
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def create_schema(con):
    """Create the DuckDB schema."""
    print("Creating database schema...")

    tables_to_drop = [
        "work_institutions", "work_authors",
        "institutions", "authors", "works"
    ]
    for tbl in tables_to_drop:
        try:
            con.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass

    con.execute("""CREATE TABLE works (
        work_id BIGINT PRIMARY KEY, doi VARCHAR, title VARCHAR,
        publication_date VARCHAR, publication_year INTEGER,
        document_type VARCHAR, cited_by_count INTEGER DEFAULT 0,
        is_oa INTEGER DEFAULT 0, source_display_name VARCHAR,
        abstract VARCHAR, language VARCHAR, volume VARCHAR, issue VARCHAR,
        first_page VARCHAR, last_page VARCHAR, pdf_url VARCHAR,
        landing_page_url VARCHAR, author_keywords VARCHAR, keywords VARCHAR,
        index_keywords_scopus VARCHAR, keywords_plus_wos VARCHAR,
        created_date TIMESTAMP, updated_date TIMESTAMP
    )""")

    con.execute("""CREATE TABLE authors (
        author_id BIGINT PRIMARY KEY, display_name VARCHAR NOT NULL,
        orcid VARCHAR, works_count INTEGER, cited_by_count INTEGER,
        h_index INTEGER, i10_index INTEGER, collab_status VARCHAR,
        total_institutions INTEGER, total_countries INTEGER,
        n_corresponding_works INTEGER, created_date TIMESTAMP, updated_date TIMESTAMP
    )""")

    con.execute("""CREATE TABLE institutions (
        inst_id BIGINT PRIMARY KEY, ror VARCHAR,
        display_name VARCHAR NOT NULL, country_code VARCHAR,
        type VARCHAR, homepage_url VARCHAR, image_url VARCHAR,
        thumbnail_url VARCHAR, latitude DOUBLE, longitude DOUBLE,
        city VARCHAR, region VARCHAR, works_count INTEGER,
        cited_by_count INTEGER, created_date TIMESTAMP, updated_date TIMESTAMP
    )""")

    con.execute("""CREATE TABLE work_authors (
        work_id BIGINT, author_id BIGINT,
        author_position VARCHAR, is_corresponding INTEGER,
        raw_affiliation_string VARCHAR,
        PRIMARY KEY (work_id, author_id, author_position)
    )""")

    con.execute("""CREATE TABLE work_institutions (
        work_id BIGINT, inst_id BIGINT,
        PRIMARY KEY (work_id, inst_id)
    )""")

    print("Schema created.")


def load_support_data(con):
    """Load institutional_relationships_IN_CH and authors_summary_in_ch for mapping."""
    print("Loading support data...")
    inst_path = SEARCH_APP_DATA / "institutional_relationships_IN_CH.parquet"
    auth_path = SEARCH_APP_DATA / "authors_summary_in_ch.parquet"

    inst_df = pl.read_parquet(inst_path)
    auth_df = pl.read_parquet(auth_path)

    inst_map = {}
    for row in inst_df.iter_rows(named=True):
        name = row.get("institution_name")
        cc = row.get("country_code")
        if name and cc:
            inst_map[name] = cc

    auth_collab_map = {}
    for row in auth_df.iter_rows(named=True):
        name = row.get("name")
        status = row.get("collab_status")
        if name and status:
            auth_collab_map[name] = status

    return inst_map, auth_collab_map


def _split_institution_entry(entry: str):
    """Split a 'Name, CC' entry into (clean_name, country_code).

    The publications parquet 'institutions' column uses '; '-separated entries,
    each of which is typically 'Institution Name, XX' where XX is a 2-letter
    country code. Some entries have no country suffix (leave as-is, cc=None).
    """
    entry = entry.strip()
    if len(entry) >= 4 and entry[-4:-2] == ", " and entry[-2:].isalpha() and entry[-2:].isupper():
        return entry[:-4].strip(), entry[-2:]
    return entry, None


def load_and_insert_data(con, inst_map, auth_collab_map):
    """Load parquet data and insert into DuckDB."""
    print("Loading publications parquet...")
    pubs_path = SEARCH_APP_DATA / "publications_full_dataset_2000-2024.parquet"
    df = pl.read_parquet(pubs_path)

    print(f"Processing {len(df)} publications...")

    author_name_to_id: dict[str, int] = {}
    author_counter = 1

    # Keyed by clean display_name (after stripping ', CC' suffix) so we dedupe
    # institutions across the entire dataset instead of per-work.
    inst_name_to_id: dict[str, int] = {}
    inst_records: dict[int, dict] = {}
    inst_counter = 1

    works_list = []
    authors_list = []
    work_authors_list = []
    work_institutions_seen: set[tuple[int, int]] = set()
    work_institutions_list = []
    synthetic_work_id = -1  # negative to avoid collisions with real OpenAlex IDs

    for row in df.iter_rows(named=True):
        work_id_str = row.get("work_id", "")
        work_id = strip_id_prefix(work_id_str, "W")
        if work_id is None:
            # Parquet row lacks an OpenAlex work_id but may have a valid DOI/title.
            # v1 keeps it; assign a synthetic negative ID so v2 keeps it too.
            work_id = synthetic_work_id
            synthetic_work_id -= 1

        works_list.append({
            "work_id": work_id,
            "doi": row.get("doi"),
            "title": row.get("title"),
            "publication_date": row.get("publication_date"),
            "publication_year": row.get("publication_year"),
            "document_type": row.get("document type"),
            "cited_by_count": row.get("cited_by_count") or 0,
            "is_oa": 1 if row.get("is_oa") else 0,
            "source_display_name": row.get("source_display_name"),
            "abstract": row.get("abstract"),
        })

        authors_str = row.get("authors")
        if authors_str and isinstance(authors_str, str):
            author_names = [a.strip() for a in authors_str.split(";") if a.strip()]
            for idx, author_name in enumerate(author_names):
                aid = author_name_to_id.get(author_name)
                if aid is None:
                    aid = author_counter
                    author_counter += 1
                    author_name_to_id[author_name] = aid
                    authors_list.append({
                        "author_id": aid,
                        "display_name": author_name,
                        "collab_status": auth_collab_map.get(author_name),
                    })
                work_authors_list.append({
                    "work_id": work_id,
                    "author_id": aid,
                    "author_position": str(idx + 1),
                    "is_corresponding": 0,
                    "raw_affiliation_string": None,
                })

        institutions_str = row.get("institutions")
        if institutions_str and isinstance(institutions_str, str):
            entries = [e for e in institutions_str.split(";") if e.strip()]
            for entry in entries:
                clean_name, cc_from_suffix = _split_institution_entry(entry)
                if not clean_name:
                    continue
                iid = inst_name_to_id.get(clean_name)
                if iid is None:
                    iid = inst_counter
                    inst_counter += 1
                    inst_name_to_id[clean_name] = iid
                    country_code = cc_from_suffix or inst_map.get(clean_name)
                    inst_records[iid] = {
                        "inst_id": iid,
                        "display_name": clean_name,
                        "country_code": country_code,
                    }
                elif inst_records[iid]["country_code"] is None and cc_from_suffix:
                    inst_records[iid]["country_code"] = cc_from_suffix
                key = (work_id, iid)
                if key not in work_institutions_seen:
                    work_institutions_seen.add(key)
                    work_institutions_list.append({"work_id": work_id, "inst_id": iid})

    institutions_list = list(inst_records.values())

    print(f"Inserting {len(works_list)} works...")
    works_df = pl.DataFrame(works_list)
    con.register("works_temp", works_df)
    con.execute("""INSERT INTO works
        (work_id, doi, title, publication_date, publication_year, document_type,
         cited_by_count, is_oa, source_display_name, abstract)
        SELECT work_id, doi, title, publication_date, publication_year, document_type,
         cited_by_count, is_oa, source_display_name, abstract FROM works_temp""")
    con.unregister("works_temp")

    print(f"Inserting {len(authors_list)} authors...")
    authors_df = pl.DataFrame(authors_list)
    con.register("authors_temp", authors_df)
    con.execute("""INSERT INTO authors
        (author_id, display_name, collab_status)
        SELECT author_id, display_name, collab_status FROM authors_temp""")
    con.unregister("authors_temp")

    print(f"Inserting {len(institutions_list)} institutions...")
    institutions_df = pl.DataFrame(institutions_list)
    con.register("institutions_temp", institutions_df)
    con.execute("""INSERT INTO institutions
        (inst_id, display_name, country_code)
        SELECT inst_id, display_name, country_code FROM institutions_temp""")
    con.unregister("institutions_temp")

    print(f"Inserting {len(work_authors_list)} work_authors...")
    work_authors_df = pl.DataFrame(work_authors_list)
    con.register("work_authors_temp", work_authors_df)
    con.execute("""INSERT INTO work_authors
        (work_id, author_id, author_position, is_corresponding, raw_affiliation_string)
        SELECT work_id, author_id, author_position, is_corresponding, raw_affiliation_string
        FROM work_authors_temp""")
    con.unregister("work_authors_temp")

    print(f"Inserting {len(work_institutions_list)} work_institutions...")
    work_institutions_df = pl.DataFrame(work_institutions_list)
    con.register("work_institutions_temp", work_institutions_df)
    con.execute("""INSERT INTO work_institutions
        (work_id, inst_id)
        SELECT work_id, inst_id FROM work_institutions_temp""")
    con.unregister("work_institutions_temp")

    print("Data inserted.")
    return len(works_list), len(authors_list), len(institutions_list), len(work_authors_list), len(work_institutions_list)


def create_indexes(con):
    """Create indexes for performance."""
    print("Creating indexes...")
    con.execute("CREATE INDEX idx_works_pub_year ON works(publication_year)")
    con.execute("CREATE INDEX idx_work_authors_work_id ON work_authors(work_id)")
    con.execute("CREATE INDEX idx_work_authors_author_id ON work_authors(author_id)")
    con.execute("CREATE INDEX idx_work_institutions_work_id ON work_institutions(work_id)")
    con.execute("CREATE INDEX idx_work_institutions_inst_id ON work_institutions(inst_id)")
    con.execute("CREATE INDEX idx_authors_display_name ON authors(display_name)")
    con.execute("CREATE INDEX idx_institutions_display_name ON institutions(display_name)")
    con.execute("CREATE INDEX idx_institutions_country_code ON institutions(country_code)")
    print("Indexes created.")


def main():
    DEV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DEV_DB_PATH.exists():
        print(f"Removing existing {DEV_DB_PATH}...")
        DEV_DB_PATH.unlink()

    print(f"Creating DuckDB at {DEV_DB_PATH}...")
    con = duckdb.connect(str(DEV_DB_PATH))

    create_schema(con)
    inst_map, auth_collab_map = load_support_data(con)
    w_count, a_count, i_count, wa_count, wi_count = load_and_insert_data(con, inst_map, auth_collab_map)

    create_indexes(con)

    con.close()

    print("\n=== Dev DB Build Complete ===")
    print(f"works: {w_count}")
    print(f"authors: {a_count}")
    print(f"institutions: {i_count}")
    print(f"work_authors: {wa_count}")
    print(f"work_institutions: {wi_count}")
    print(f"DB location: {DEV_DB_PATH}")


if __name__ == "__main__":
    main()
