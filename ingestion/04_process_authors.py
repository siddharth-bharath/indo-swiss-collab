"""Process author-level data from OpenAlex authorships and publications.

Inputs:
  - interim/openalex_authorships.parquet (step 02)
  - output/publications_full_dataset_<label>.parquet (step 03, optional for context)

Outputs:
  - output/authors_processed_flat.parquet (one row per work-author)
  - output/authors_summary_with_lists.parquet (one row per author)
  - output/work_institution_links.parquet (deduped work-institution mapping)
  - output/institutional_relationships_IN_CH.parquet (+ .xlsx)
  - output/authors_summary_in_ch.parquet (filtered subset)

Per SCHEMAS.md §04 and Metadata/dataset_v1_metadata_documentation.md §A.2–A.5, A.7.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import polars as pl
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM_DIR, OUTPUT_DIR


def load_inputs(publications_path: Path | None = None) -> tuple[pl.DataFrame, pl.DataFrame | None]:
    """Load authorships and (optionally) publications for context."""
    auth = pl.read_parquet(INTERIM_DIR / "openalex_authorships.parquet")

    pubs = None
    if publications_path and publications_path.exists():
        pubs = pl.read_parquet(publications_path)
    else:
        # Auto-detect most recent publications parquet
        output_pubfiles = list(OUTPUT_DIR.glob("publications_full_dataset_*.parquet"))
        if output_pubfiles:
            pubs_path = max(output_pubfiles, key=lambda p: p.stat().st_mtime)
            pubs = pl.read_parquet(pubs_path)

    return auth, pubs


def build_authors_flat(auth: pl.DataFrame) -> pl.DataFrame:
    """Build authors_processed_flat: annotate raw authorships with parsed institutions.

    Converts author_position from string (first/middle/last) to integer order within work.
    Parses affiliations JSON and derives institution/country summaries per author per work.

    Returns:
        DataFrame with columns: work_id, author_id, display_name, orcid, author_position (int),
        is_corresponding, affiliations, affiliation_raw, institutions_with_country, author_countries,
        n_institutions_author, n_countries_author.
    """

    def parse_affiliations_row(affiliations_json: str | None) -> dict[str, Any]:
        """Parse affiliations JSON and return dict with institution/country summaries."""
        if not affiliations_json:
            return {
                "institutions_with_country": "",
                "author_countries": "",
                "n_institutions_author": 0,
                "n_countries_author": 0,
            }

        try:
            aff_list = json.loads(affiliations_json)
        except (json.JSONDecodeError, TypeError):
            return {
                "institutions_with_country": "",
                "author_countries": "",
                "n_institutions_author": 0,
                "n_countries_author": 0,
            }

        if not aff_list:
            return {
                "institutions_with_country": "",
                "author_countries": "",
                "n_institutions_author": 0,
                "n_countries_author": 0,
            }

        institutions = []
        countries = set()

        for aff in aff_list:
            if not isinstance(aff, dict):
                continue
            inst_name = aff.get("display_name", "")
            country = aff.get("country_code", "")
            if inst_name and country:
                institutions.append(f"{inst_name}, {country}")
                countries.add(country)

        institutions_str = "; ".join(institutions)
        countries_str = ", ".join(sorted(countries))

        return {
            "institutions_with_country": institutions_str,
            "author_countries": countries_str,
            "n_institutions_author": len(set(institutions)),
            "n_countries_author": len(countries),
        }

    # Vectorize the parsing function - build lists separately
    parsed_results = [parse_affiliations_row(aff) for aff in auth["affiliations"]]

    inst_with_country = [r["institutions_with_country"] for r in parsed_results]
    author_countries = [r["author_countries"] for r in parsed_results]
    n_inst = [r["n_institutions_author"] for r in parsed_results]
    n_countries = [r["n_countries_author"] for r in parsed_results]

    # Add parsed columns to auth
    flat = auth.with_columns(
        pl.Series("institutions_with_country", inst_with_country),
        pl.Series("author_countries", author_countries),
        pl.Series("n_institutions_author", n_inst),
        pl.Series("n_countries_author", n_countries),
    )

    # Convert author_position from string to integer within each work
    # Strategy: within each work, assign 1 to "first", len to "last", and 2..len-1 to "middle" in order
    def compute_int_position(df_group: pl.DataFrame) -> pl.DataFrame:
        n = len(df_group)
        positions = df_group["author_position"].to_list()
        int_pos = []
        middle_count = 0
        for pos in positions:
            if pos == "first":
                int_pos.append(1)
            elif pos == "last":
                int_pos.append(n)
            else:  # middle
                int_pos.append(2 + middle_count)
                middle_count += 1
        return df_group.with_columns(
            pl.Series("author_position_int", int_pos, dtype=pl.Int32)
        )

    flat = flat.group_by("work_id", maintain_order=True).map_groups(
        compute_int_position
    )

    # Select final output columns and rename position column
    flat = flat.select(
        [
            "work_id",
            "author_id",
            "display_name",
            "orcid",
            "author_position_int",
            "is_corresponding",
            "affiliations",
            "affiliation_raw",
            "institutions_with_country",
            "author_countries",
            "n_institutions_author",
            "n_countries_author",
        ]
    ).rename({"author_position_int": "author_position"})

    return flat


def build_authors_summary(flat: pl.DataFrame) -> pl.DataFrame:
    """Build authors_summary_with_lists: per-author aggregates with nested lists.

    Aggregates institutions and countries with work counts, derives collab_status.
    Uses pandas for the nested list-of-struct aggregations.

    Returns:
        DataFrame with columns: author_id, name, orcid, nWorks, n_corresponding_works,
        total_institutions, total_countries, institution_work_counts, country_work_counts,
        collab_status, has_india_swiss_collab.
    """

    # Convert to pandas for aggregation
    df = flat.to_pandas()

    # Basic per-author aggregates
    author_summary = (
        df.groupby("author_id")
        .agg(
            name=("display_name", "first"),
            orcid=("orcid", "first"),
            nWorks=("work_id", "nunique"),
            n_corresponding_works=("is_corresponding", "sum"),
        )
        .reset_index()
    )

    # Institution aggregates: for each author, count unique institutions across works
    # institutions_with_country is semicolon-separated "Name, CC"
    def count_unique_from_semi_joined(series: pd.Series) -> int:
        """Count unique items in a semicolon-joined string across multiple rows."""
        unique_items = set()
        for val in series.dropna():
            if val:
                unique_items.update(val.split("; "))
        return len(unique_items)

    def count_unique_countries(series: pd.Series) -> int:
        """Count unique country codes from comma-joined strings."""
        unique_countries = set()
        for val in series.dropna():
            if val:
                unique_countries.update(val.split(", "))
        return len(unique_countries)

    institution_total = (
        df.groupby("author_id")["institutions_with_country"]
        .apply(count_unique_from_semi_joined)
        .reset_index()
    )
    institution_total.columns = ["author_id", "total_institutions"]

    country_total = (
        df.groupby("author_id")["author_countries"]
        .apply(count_unique_countries)
        .reset_index()
    )
    country_total.columns = ["author_id", "total_countries"]

    author_summary = author_summary.merge(institution_total, on="author_id", how="left")
    author_summary = author_summary.merge(country_total, on="author_id", how="left")
    author_summary = author_summary.fillna({"total_institutions": 0, "total_countries": 0})

    # Institution work counts: list of {institutions, n_works}
    def build_institution_work_counts(group: pd.DataFrame) -> list[dict]:
        """Build nested list of {institutions, n_works} sorted descending by n_works."""
        inst_works = {}
        for _, row in group.iterrows():
            insts = row["institutions_with_country"]
            if insts:
                for inst in insts.split("; "):
                    inst_works[inst] = inst_works.get(inst, 0) + 1

        # Convert to list of dicts and sort by n_works descending
        result = [{"institutions": k, "n_works": v} for k, v in inst_works.items()]
        result.sort(key=lambda x: x["n_works"], reverse=True)
        return result

    def build_country_work_counts(group: pd.DataFrame) -> list[dict]:
        """Build nested list of {countries, n_works} sorted descending by n_works."""
        country_works = {}
        for _, row in group.iterrows():
            countries = row["author_countries"]
            if countries:
                for country in countries.split(", "):
                    country_works[country] = country_works.get(country, 0) + 1

        result = [{"countries": k, "n_works": v} for k, v in country_works.items()]
        result.sort(key=lambda x: x["n_works"], reverse=True)
        return result

    institution_work_counts = (
        df.groupby("author_id", group_keys=False)
        .apply(build_institution_work_counts, include_groups=False)
        .reset_index()
    )
    institution_work_counts.columns = ["author_id", "institution_work_counts"]

    country_work_counts = (
        df.groupby("author_id", group_keys=False)
        .apply(build_country_work_counts, include_groups=False)
        .reset_index()
    )
    country_work_counts.columns = ["author_id", "country_work_counts"]

    author_summary = author_summary.merge(
        institution_work_counts, on="author_id", how="left"
    )
    author_summary = author_summary.merge(country_work_counts, on="author_id", how="left")

    # Collab status: Joint, Both, IN, CH, None
    # Joint: author has ≥1 work where both IN and CH appear in their own author_countries
    # Both: author has IN and CH affiliations but never on same work
    # IN: IN only
    # CH: CH only
    # None: neither
    collab_status = []
    for author_id in author_summary["author_id"]:
        author_rows = df[df["author_id"] == author_id]
        has_joint = False
        has_IN = False
        has_CH = False

        for _, row in author_rows.iterrows():
            countries = row["author_countries"]
            if countries:
                if "IN" in countries.split(", "):
                    has_IN = True
                if "CH" in countries.split(", "):
                    has_CH = True
                if "IN" in countries.split(", ") and "CH" in countries.split(", "):
                    has_joint = True

        if has_joint:
            status = "Joint"
        elif has_IN and has_CH:
            status = "Both"
        elif has_IN:
            status = "IN"
        elif has_CH:
            status = "CH"
        else:
            status = "None"

        collab_status.append(status)

    author_summary["collab_status"] = collab_status
    author_summary["has_india_swiss_collab"] = author_summary["collab_status"] == "Joint"

    return pl.from_pandas(author_summary)


def build_work_institution_links(flat: pl.DataFrame) -> pl.DataFrame:
    """Build work_institution_links: deduped work-institution mapping.

    Uses Python for parsing and unnesting JSON affiliations.

    Returns:
        DataFrame with columns: work_id, inst_id, institution_name, ror, country_code.
    """

    work_inst_records = []

    for row in flat.select(["work_id", "affiliations"]).to_dicts():
        work_id = row["work_id"]
        aff_json = row["affiliations"]

        if not aff_json:
            continue

        try:
            aff_list = json.loads(aff_json)
        except (json.JSONDecodeError, TypeError):
            continue

        for aff in aff_list:
            if not isinstance(aff, dict):
                continue
            inst_id = aff.get("inst_id")
            if inst_id:
                work_inst_records.append(
                    {
                        "work_id": work_id,
                        "inst_id": inst_id,
                        "institution_name": aff.get("display_name"),
                        "ror": aff.get("ror"),
                        "country_code": aff.get("country_code"),
                    }
                )

    # Dedupe by (work_id, inst_id)
    result = pl.DataFrame(work_inst_records).unique(
        subset=["work_id", "inst_id"], maintain_order=False
    ).sort(["work_id", "inst_id"])

    return result


def build_institutional_in_ch(work_inst_links: pl.DataFrame, flat: pl.DataFrame) -> pl.DataFrame:
    """Build institutional_relationships_IN_CH: IN+CH institutions with metrics.

    Filters to IN and CH countries, counts publications, unique authors, and author names.

    Returns:
        DataFrame with columns: inst_id, institution_name, country_code, ror, work_ids,
        n_publications, n_authors, author_names.
    """

    # Filter to IN and CH
    in_ch = work_inst_links.filter(pl.col("country_code").is_in(["IN", "CH"]))

    # Get per-institution metrics
    agg_df = (
        in_ch.group_by("inst_id", "institution_name", "country_code", "ror")
        .agg(
            work_ids=pl.col("work_id").unique(),
            n_publications=pl.col("work_id").n_unique(),
        )
        .with_columns(
            work_ids=pl.col("work_ids").list.join("; ")
        )
    )

    # Get author counts and names per institution
    # From flat: for each work_id in institution, get unique authors
    flat_for_auth = flat.select(["work_id", "author_id", "display_name"])

    # Build author mapping
    auth_agg = (
        in_ch.select("inst_id", "work_id")
        .join(flat_for_auth, on="work_id")
        .group_by("inst_id")
        .agg(
            n_authors=pl.col("author_id").n_unique(),
            author_names=pl.col("display_name").unique(),
        )
        .with_columns(
            author_names=pl.col("author_names").list.join("; ")
        )
    )

    result = agg_df.join(auth_agg, on="inst_id", how="left")
    return result.select(
        [
            "inst_id",
            "institution_name",
            "country_code",
            "ror",
            "work_ids",
            "n_publications",
            "n_authors",
            "author_names",
        ]
    )


def write_institutional_xlsx(df: pl.DataFrame, output_path: Path) -> None:
    """Write institutional_relationships_IN_CH to Excel."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Institutions"

    # Write header
    df_pd = df.to_pandas()
    for r_idx, row in enumerate(
        dataframe_to_rows(df_pd, index=False, header=True), 1
    ):
        for c_idx, value in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    wb.save(output_path)


def main(publications_path: Path | None = None) -> None:
    """Main orchestration function."""
    print("Loading inputs...")
    auth, _pubs = load_inputs(publications_path)

    print(f"Loaded {len(auth):,} author-work records")

    print("\nBuilding authors_processed_flat...")
    flat = build_authors_flat(auth)
    flat_path = OUTPUT_DIR / "authors_processed_flat.parquet"
    flat.write_parquet(flat_path)
    print(f"  Wrote {len(flat):,} rows to {flat_path.name}")

    print("\nBuilding authors_summary_with_lists...")
    summary = build_authors_summary(flat)
    summary_path = OUTPUT_DIR / "authors_summary_with_lists.parquet"
    summary.write_parquet(summary_path)
    print(f"  Wrote {len(summary):,} rows to {summary_path.name}")

    print("\nBuilding work_institution_links...")
    work_inst = build_work_institution_links(flat)
    work_inst_path = OUTPUT_DIR / "work_institution_links.parquet"
    work_inst.write_parquet(work_inst_path)
    print(f"  Wrote {len(work_inst):,} rows to {work_inst_path.name}")

    print("\nBuilding institutional_relationships_IN_CH...")
    inst_in_ch = build_institutional_in_ch(work_inst, flat)
    inst_path = OUTPUT_DIR / "institutional_relationships_IN_CH.parquet"
    inst_in_ch.write_parquet(inst_path)
    xlsx_path = OUTPUT_DIR / "institutional_relationships_IN_CH.xlsx"
    write_institutional_xlsx(inst_in_ch, xlsx_path)
    print(f"  Wrote {len(inst_in_ch):,} rows to {inst_path.name} and {xlsx_path.name}")

    print("\nBuilding authors_summary_in_ch...")
    summary_in_ch = summary.filter(
        pl.col("collab_status").is_in(["Joint", "Both", "IN", "CH"])
    )
    summary_in_ch_path = OUTPUT_DIR / "authors_summary_in_ch.parquet"
    summary_in_ch.write_parquet(summary_in_ch_path)
    print(f"  Wrote {len(summary_in_ch):,} rows to {summary_in_ch_path.name}")

    print("\n=== Summary ===")
    print(f"authors_processed_flat: {len(flat):,} rows")
    print(f"authors_summary_with_lists: {len(summary):,} rows")
    print(f"work_institution_links: {len(work_inst):,} rows")
    print(f"institutional_relationships_IN_CH: {len(inst_in_ch):,} rows")
    print(f"authors_summary_in_ch: {len(summary_in_ch):,} rows")

    print("\nCollab status distribution:")
    print(summary.group_by("collab_status").agg(pl.len()).sort("len", descending=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process author-level data from OpenAlex authorships."
    )
    parser.add_argument(
        "--publications",
        type=Path,
        help="Path to publications_full_dataset parquet (optional, for context)",
    )
    args = parser.parse_args()

    main(args.publications)
