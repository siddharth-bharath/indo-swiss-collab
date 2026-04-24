"""DOI-level merge of Web of Science, Scopus, and OpenAlex publications.

Inputs:
  - interim/openalex_works.parquet (step 02)
  - interim/openalex_authorships.parquet (step 02)
  - interim/wos.parquet (step 01)
  - interim/scopus.parquet (step 01)

Outputs:
  - output/publications_full_dataset_<label>.parquet (primary deliverable)
  - output/work_topic_links.parquet (long-form topic mapping)

Per SCHEMAS.md §03 and Metadata/dataset_v1_metadata_documentation.md §A.1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM_DIR, OUTPUT_DIR


def load_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Load interim parquets from steps 01 and 02."""
    oa_works = pl.read_parquet(INTERIM_DIR / "openalex_works.parquet")
    oa_auth = pl.read_parquet(INTERIM_DIR / "openalex_authorships.parquet")

    wos_path = INTERIM_DIR / "wos.parquet"
    wos = pl.read_parquet(wos_path) if wos_path.exists() else pl.DataFrame()

    scopus_path = INTERIM_DIR / "scopus.parquet"
    scopus = pl.read_parquet(scopus_path) if scopus_path.exists() else pl.DataFrame()

    return oa_works, oa_auth, wos, scopus


def parse_topics(oa_works: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Extract primary topic and build full work-topic mapping.

    Returns:
        (works_with_primary, work_topic_links)
    """
    def extract_primary_topic(topics_json: str | None) -> dict[str, Any]:
        """Parse topics JSON and extract primary (index 0) topic hierarchy."""
        if not topics_json:
            return {
                "primary_topic_id": None,
                "primary_topic_name": None,
                "primary_topic_score": None,
                "primary_subfield_id": None,
                "primary_subfield_name": None,
                "primary_field_id": None,
                "primary_field_name": None,
                "primary_domain_id": None,
                "primary_domain_name": None,
            }
        try:
            topics_list = json.loads(topics_json)
            if not topics_list:
                raise ValueError("Empty topics list")
            primary = topics_list[0]

            return {
                "primary_topic_id": primary.get("id"),
                "primary_topic_name": primary.get("display_name"),
                "primary_topic_score": primary.get("score"),
                "primary_subfield_id": primary.get("subfield", {}).get("id"),
                "primary_subfield_name": primary.get("subfield", {}).get("display_name"),
                "primary_field_id": primary.get("field", {}).get("id"),
                "primary_field_name": primary.get("field", {}).get("display_name"),
                "primary_domain_id": primary.get("domain", {}).get("id"),
                "primary_domain_name": primary.get("domain", {}).get("display_name"),
            }
        except Exception:
            return {
                "primary_topic_id": None,
                "primary_topic_name": None,
                "primary_topic_score": None,
                "primary_subfield_id": None,
                "primary_subfield_name": None,
                "primary_field_id": None,
                "primary_field_name": None,
                "primary_domain_id": None,
                "primary_domain_name": None,
            }

    def extract_all_topics(topics_json: str | None, work_id: str) -> list[dict[str, Any]]:
        """Extract all topic-level entries with is_primary flag."""
        if not topics_json:
            return []
        try:
            topics_list = json.loads(topics_json)
            rows = []
            for i, topic in enumerate(topics_list):
                rows.append({
                    "work_id": work_id,
                    "topic_id": topic.get("id"),
                    "topic_name": topic.get("display_name"),
                    "topic_score": topic.get("score"),
                    "is_primary": i == 0,
                })
            return rows
        except Exception:
            return []

    # Extract primary topics
    primary_cols = []
    for row in oa_works.iter_rows(named=True):
        primary_cols.append(extract_primary_topic(row["topics"]))

    primary_df = pl.DataFrame(primary_cols)
    works_with_primary = oa_works.hstack(primary_df).drop("topics")

    # Build work-topic mapping
    topic_rows = []
    for row in oa_works.iter_rows(named=True):
        topic_rows.extend(extract_all_topics(row["topics"], row["work_id"]))

    work_topic_links = pl.DataFrame(topic_rows) if topic_rows else pl.DataFrame({
        "work_id": pl.Series(dtype=pl.String),
        "topic_id": pl.Series(dtype=pl.String),
        "topic_name": pl.Series(dtype=pl.String),
        "topic_score": pl.Series(dtype=pl.Float64),
        "is_primary": pl.Series(dtype=pl.Boolean),
    })

    return works_with_primary, work_topic_links


def canonicalize_doi(doi: str | None) -> str | None:
    """Canonicalize DOI: lowercase, strip prefix, trim whitespace."""
    if not doi or not isinstance(doi, str):
        return None
    doi = doi.lower().strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi if doi else None


def merge_sources(
    oa: pl.DataFrame, wos: pl.DataFrame, scopus: pl.DataFrame
) -> pl.DataFrame:
    """DOI-level left merge: OA backbone + WoS + Scopus enhancements.

    Per SCHEMAS.md §03 Enhancement rules.
    """
    # Canonicalize DOIs
    oa = oa.with_columns(doi=pl.col("doi").map_elements(canonicalize_doi, return_dtype=pl.String))
    oa = oa.filter(pl.col("doi").is_not_null())

    if wos.height > 0:
        wos = wos.with_columns(
            doi=pl.col("doi").map_elements(canonicalize_doi, return_dtype=pl.String)
        ).filter(pl.col("doi").is_not_null())
        # Dedupe on DOI before the left-join. WoS exports sometimes contain
        # the same DOI in multiple source files; a left-join with a many-rows-per-key
        # right side would multiply OA rows and break the work_id PK downstream.
        wos = wos.unique(subset=["doi"], keep="first")

        wos_select = wos.select([
            "doi",
            pl.col("abstract").alias("abstract_wos"),
            pl.col("funding details").alias("funding_details_wos"),
            pl.col("funding text").alias("funding_text_wos"),
            pl.col("author keywords").alias("author_keywords_wos"),
            pl.col("keywords_plus_wos"),
            pl.col("times_cited").alias("cited_by_count_wos"),
            pl.col("document type").alias("document_type_wos"),
        ])
        oa = oa.join(wos_select, on="doi", how="left")
    else:
        # Add empty columns for WoS if file is missing/empty
        oa = oa.with_columns([
            pl.lit(None, dtype=pl.String).alias("abstract_wos"),
            pl.lit(None, dtype=pl.String).alias("funding_details_wos"),
            pl.lit(None, dtype=pl.String).alias("funding_text_wos"),
            pl.lit(None, dtype=pl.String).alias("author_keywords_wos"),
            pl.lit(None, dtype=pl.String).alias("keywords_plus_wos"),
            pl.lit(None, dtype=pl.String).alias("cited_by_count_wos"),
            pl.lit(None, dtype=pl.String).alias("document_type_wos"),
        ])

    if scopus.height > 0:
        scopus = scopus.with_columns(
            doi=pl.col("doi").map_elements(canonicalize_doi, return_dtype=pl.String)
        ).filter(pl.col("doi").is_not_null())
        scopus = scopus.unique(subset=["doi"], keep="first")

        scopus_select = scopus.select([
            "doi",
            pl.col("abstract").alias("abstract_scopus"),
            pl.col("funding details").alias("funding_details_scopus"),
            pl.col("funding text").alias("funding_text_scopus"),
            pl.col("author keywords").alias("author_keywords_scopus"),
            pl.col("index_keywords_scopus"),
            pl.col("times_cited").alias("cited_by_count_scopus"),
        ])
        oa = oa.join(scopus_select, on="doi", how="left")
    else:
        oa = oa.with_columns([
            pl.lit(None, dtype=pl.String).alias("abstract_scopus"),
            pl.lit(None, dtype=pl.String).alias("funding_details_scopus"),
            pl.lit(None, dtype=pl.String).alias("funding_text_scopus"),
            pl.lit(None, dtype=pl.String).alias("author_keywords_scopus"),
            pl.lit(None, dtype=pl.String).alias("index_keywords_scopus"),
            pl.lit(None, dtype=pl.String).alias("cited_by_count_scopus"),
        ])

    return oa


def enhance_fields(merged: pl.DataFrame) -> pl.DataFrame:
    """Apply enhancement rules per SCHEMAS.md §03.

    - cited_by_count: max across all sources
    - abstract: prefer OA, then longest of (Scopus, WoS)
    - funding_details/funding_text: longest non-empty
    - author_keywords: semicolon-merge deduped across all sources
    - document type: lowercase
    """
    df = merged.to_pandas()

    def to_int_or_none(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    def max_citations(row):
        vals = [
            to_int_or_none(row.get("cited_by_count")),
            to_int_or_none(row.get("cited_by_count_wos")),
            to_int_or_none(row.get("cited_by_count_scopus")),
        ]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    df["cited_by_count"] = df.apply(max_citations, axis=1)

    # abstract: prefer OA; else longest of (Scopus, WoS)
    def pick_abstract(row):
        candidates = [
            row.get("abstract"),
            row.get("abstract_scopus"),
            row.get("abstract_wos"),
        ]
        candidates = [c for c in candidates if pd.notna(c)]
        return max(candidates, key=len) if candidates else None

    df["abstract"] = df.apply(pick_abstract, axis=1)

    # funding_details: longest non-empty
    def pick_longer(val1, val2):
        s1 = val1 if pd.notna(val1) else ""
        s2 = val2 if pd.notna(val2) else ""
        return s1 if len(s1) >= len(s2) else s2 if s2 else None

    df["funding_details"] = df.apply(
        lambda row: pick_longer(
            row.get("funding_details_wos"),
            row.get("funding_details_scopus")
        ),
        axis=1
    )

    df["funding_text"] = df.apply(
        lambda row: pick_longer(
            row.get("funding_text_wos"),
            row.get("funding_text_scopus")
        ),
        axis=1
    )

    # author_keywords: semicolon-merge deduped
    def merge_keywords(row):
        sources = [
            row.get("author_keywords"),
            row.get("author_keywords_wos"),
            row.get("author_keywords_scopus"),
        ]
        all_kw = []
        for src in sources:
            if pd.notna(src) and src:
                kw_list = [k.strip() for k in src.split(";") if k.strip()]
                all_kw.extend(kw_list)

        if not all_kw:
            return None

        seen = set()
        unique_kw = []
        for kw in all_kw:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique_kw.append(kw)

        return "; ".join(unique_kw) if unique_kw else None

    df["author_keywords"] = df.apply(merge_keywords, axis=1)

    # document type: lowercase
    df["document type"] = df["type"].str.lower()

    # Drop source-specific columns
    drop_cols = [
        "type",
        "abstract_wos", "abstract_scopus",
        "funding_details_wos", "funding_details_scopus",
        "funding_text_wos", "funding_text_scopus",
        "author_keywords_wos", "author_keywords_scopus",
        "cited_by_count_wos", "cited_by_count_scopus",
        "document_type_wos",
    ]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    return pl.from_pandas(df)


_POSITION_ORDER = {"first": 0, "middle": 1, "last": 2}


def _parse_affiliations(aff_json: str | None) -> tuple[list[str], list[str], list[str], list[str]]:
    """Parse affiliations JSON → (institutions_with_cc, countries, inst_ids, ror_ids)."""
    if not aff_json or aff_json == "[]":
        return [], [], [], []
    try:
        parsed = json.loads(aff_json)
    except (json.JSONDecodeError, TypeError):
        return [], [], [], []
    affs = parsed if isinstance(parsed, list) else [parsed]

    institutions, countries, inst_ids, ror_ids = [], [], [], []
    for aff in affs:
        if not isinstance(aff, dict):
            continue
        name, cc = aff.get("display_name"), aff.get("country_code")
        if name and cc:
            institutions.append(f"{name}, {cc}")
            countries.append(cc)
        if aff.get("inst_id"):
            inst_ids.append(aff["inst_id"])
        if aff.get("ror"):
            ror_ids.append(aff["ror"])
    return institutions, countries, inst_ids, ror_ids


def aggregate_authorships(authorships: pl.DataFrame) -> pl.DataFrame:
    """Per-work aggregation from openalex_authorships using pandas.groupby
    (single pass over the frame; scales to the full ~5M-row table)."""
    if authorships.height == 0:
        return pl.DataFrame({
            "work_id": pl.Series(dtype=pl.String),
            "authors": pl.Series(dtype=pl.String),
            "nAuthors": pl.Series(dtype=pl.Int32),
            "institutions": pl.Series(dtype=pl.String),
            "countries": pl.Series(dtype=pl.String),
            "institution_ids": pl.Series(dtype=pl.String),
            "ror_ids": pl.Series(dtype=pl.String),
        })

    df = (
        authorships
        .with_columns(
            _pos=pl.col("author_position").replace_strict(_POSITION_ORDER, default=999).cast(pl.Int32)
        )
        .sort(["work_id", "_pos"])
        .to_pandas()
    )

    def agg_one(group: pd.DataFrame) -> pd.Series:
        # authors: preserve first-seen order, dedupe on author_id (not name)
        authors_seen: dict[str, str] = {}
        for aid, name in zip(group["author_id"], group["display_name"]):
            if name and (not isinstance(aid, str) or aid not in authors_seen):
                authors_seen[aid if isinstance(aid, str) else f"_none_{len(authors_seen)}"] = name
        authors_str = "; ".join(authors_seen.values()) if authors_seen else None
        n_authors = group["author_id"].dropna().nunique()

        all_inst, all_cc, all_iid, all_ror = [], set(), set(), set()
        for aff_json in group["affiliations"]:
            if aff_json is None:
                continue
            inst, cc, iid, ror = _parse_affiliations(aff_json)
            all_inst.extend(inst)
            all_cc.update(cc)
            all_iid.update(iid)
            all_ror.update(ror)
        return pd.Series({
            "authors": authors_str,
            "nAuthors": int(n_authors),
            "institutions": "; ".join(dict.fromkeys(all_inst)) or None,
            "countries": ", ".join(sorted(all_cc)) or None,
            "institution_ids": "; ".join(sorted(all_iid)) or None,
            "ror_ids": "; ".join(sorted(all_ror)) or None,
        })

    agg = df.groupby("work_id", sort=False, as_index=False).apply(agg_one, include_groups=False)
    return pl.from_pandas(agg)


def build_final(
    enhanced: pl.DataFrame,
    author_agg: pl.DataFrame,
    label: str,
) -> None:
    """Build and write final parquet outputs.

    Outputs:
        - publications_full_dataset_<label>.parquet
        - work_topic_links.parquet
    """
    # Join author aggregation
    final = enhanced.join(author_agg, on="work_id", how="left")

    # Ensure column order matches Metadata/dataset_v1_metadata_documentation.md §A.1
    # Note: Omit the stray institutions1 and nAuthors1 columns from the R baseline
    output_columns = [
        "work_id",
        "doi",
        "title",
        "display_name",
        "publication_date",
        "publication_year",
        "cited_by_count",
        "document type",
        "is_oa",
        "source_display_name",
        "source_id",
        "issn_l",
        "host_organization",
        "host_organization_name",
        "landing_page_url",
        "pdf_url",
        "license",
        "version",
        "ids",
        "abstract",
        "is_retracted",
        "grants",
        "primary_topic_id",
        "primary_topic_name",
        "primary_topic_score",
        "primary_subfield_id",
        "primary_subfield_name",
        "primary_field_id",
        "primary_field_name",
        "primary_domain_id",
        "primary_domain_name",
        "funding_details",
        "funding_text",
        "author_keywords",
        "index_keywords_scopus",
        "keywords_plus_wos",
        "authors",
        "institutions",
        "countries",
        "nAuthors",
        "institution_ids",
        "ror_ids",
    ]

    # Select and ensure correct types
    final_out = final.select(output_columns).with_columns([
        pl.col("publication_date").str.to_date(),
        pl.col("publication_year").cast(pl.Int32),
        pl.col("cited_by_count").cast(pl.Float64),
        pl.col("nAuthors").cast(pl.Int32),
    ])

    # Write publications_full_dataset
    out_path = OUTPUT_DIR / f"publications_full_dataset_{label}.parquet"
    final_out.write_parquet(out_path)
    print(f"Wrote {out_path} ({final_out.height} rows)")


def main(label: str = "2000-2024") -> None:
    """Main pipeline."""
    print(f"Loading inputs...")
    oa_works, oa_auth, wos, scopus = load_inputs()
    print(f"  OA works: {oa_works.height}")
    print(f"  OA authorships: {oa_auth.height}")
    print(f"  WoS: {wos.height}")
    print(f"  Scopus: {scopus.height}")

    print(f"\nParsing topics...")
    oa_works, work_topic_links = parse_topics(oa_works)
    print(f"  Works with primary topics: {oa_works.height}")
    print(f"  Work-topic links: {work_topic_links.height}")

    print(f"\nMerging sources by DOI...")
    merged = merge_sources(oa_works, wos, scopus)
    print(f"  Merged publications: {merged.height}")

    print(f"\nEnhancing fields...")
    enhanced = enhance_fields(merged)

    print(f"\nAggregating authorships...")
    author_agg = aggregate_authorships(oa_auth)
    print(f"  Author aggregates: {author_agg.height}")

    print(f"\nBuilding final outputs...")
    build_final(enhanced, author_agg, label)

    print(f"\nWriting work-topic links...")
    out_path = OUTPUT_DIR / "work_topic_links.parquet"
    work_topic_links.write_parquet(out_path)
    print(f"Wrote {out_path} ({work_topic_links.height} rows)")

    print(f"\nDone!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="2000-2024", help="Label for output parquet")
    args = parser.parse_args()
    main(args.label)
