"""Ingest Web of Science and Scopus export files to parquet format.

Replicates data_assembly/data_import.Rmd (lines 12–146) in Python.
- Loads WoS .xls and Scopus .csv files from the raw data directory
- Renames columns per prep-tables mapping CSVs
- Filters to India+Switzerland collaboration rows only
- Adds period metadata inferred from sourcefile
- Writes to interim/wos.parquet and interim/scopus.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from tqdm import tqdm

from config import raw_data_dir, PREP_TABLES_DIR, INTERIM_DIR


def load_rename_mapping(csv_path: Path) -> tuple[dict[str, str], set[str]]:
    """Load column rename mapping from CSV.

    Returns:
        (rename_dict, drop_set) where rename_dict maps old_col -> new_col
        and drop_set contains columns with name_to == "IGNORE"
    """
    df = pd.read_csv(csv_path)
    cols = df.columns.tolist()

    old_col = cols[0]  # First column is source column name
    new_col = "name_to"

    rename_dict = {}
    drop_set = set()

    for _, row in df.iterrows():
        old_name = row[old_col]
        new_name = row[new_col]

        if new_name == "IGNORE":
            drop_set.add(old_name)
        else:
            rename_dict[old_name] = new_name

    return rename_dict, drop_set


def load_wos(raw_dir: Path) -> pd.DataFrame:
    """Load and process all WoS XLS files.

    Args:
        raw_dir: Path to raw data directory

    Returns:
        Processed WoS dataframe with renamed columns, sourcefile, period, and filtered rows
    """
    files = sorted(raw_dir.glob("wos*.xls*"))
    if not files:
        files = sorted([f for f in raw_dir.iterdir() if f.name.lower().startswith("wos")])

    if not files:
        return pd.DataFrame()

    rename_mapping, drop_cols = load_rename_mapping(PREP_TABLES_DIR / "wos_names_for_merging.csv")

    dfs = []
    iterator = tqdm(files, desc="Loading WoS files") if len(files) > 3 else files

    for fpath in iterator:
        df = pd.read_excel(fpath, engine="xlrd", dtype=str)

        df.columns = df.columns.str.lower()

        sourcefile_name = fpath.name.replace("wos_", "").replace(".xls", "")
        if sourcefile_name.endswith("x"):
            sourcefile_name = sourcefile_name[:-1]
        df["sourcefile"] = sourcefile_name

        df = df.drop(columns=drop_cols, errors="ignore")
        df = df.rename(columns=rename_mapping)

        dfs.append(df)

    wos_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    if wos_df.empty:
        return wos_df

    wos_df = wos_df.drop_duplicates()

    affil_col = "authors with affiliations"
    if affil_col in wos_df.columns:
        has_india = wos_df[affil_col].str.contains("india", case=False, na=False)
        has_ch = wos_df[affil_col].str.contains("switzerland", case=False, na=False)
        both_mask = has_india & has_ch

        dropped = len(wos_df) - both_mask.sum()
        if dropped > 0:
            print(f"WoS: Dropped {dropped} rows without both India and Switzerland affiliations")

        wos_df = wos_df[both_mask].copy()

    wos_df["period"] = wos_df["sourcefile"].apply(_infer_period)

    return wos_df


def load_scopus(raw_dir: Path) -> pd.DataFrame:
    """Load and process all Scopus CSV files.

    Args:
        raw_dir: Path to raw data directory

    Returns:
        Processed Scopus dataframe with renamed columns, sourcefile, period, and filtered rows
    """
    files = sorted([f for f in raw_dir.glob("scopus*.csv") if f.is_file()])
    if not files:
        files = sorted([f for f in raw_dir.iterdir()
                       if f.is_file() and f.name.lower().startswith("scopus")])

    if not files:
        return _empty_scopus_dataframe()

    rename_mapping, drop_cols = load_rename_mapping(PREP_TABLES_DIR / "scopus_names_for_merging.csv")

    dfs = []
    iterator = tqdm(files, desc="Loading Scopus files") if len(files) > 3 else files

    for fpath in iterator:
        df = pd.read_csv(fpath, dtype=str)

        df.columns = df.columns.str.lower()

        sourcefile_name = fpath.name.replace("scopus_", "").replace(".csv", "")
        df["sourcefile"] = sourcefile_name

        df = df.drop(columns=drop_cols, errors="ignore")
        df = df.rename(columns=rename_mapping)

        dfs.append(df)

    scopus_df = pd.concat(dfs, ignore_index=True) if dfs else _empty_scopus_dataframe()

    if scopus_df.empty:
        return scopus_df

    if "abstract" not in scopus_df.columns:
        scopus_df["abstract"] = None

    scopus_df = scopus_df.drop_duplicates()

    affil_col = "affiliations"
    if affil_col in scopus_df.columns:
        has_india = scopus_df[affil_col].str.contains("india", case=False, na=False)
        has_ch = scopus_df[affil_col].str.contains("switzerland", case=False, na=False)
        both_mask = has_india & has_ch

        dropped = len(scopus_df) - both_mask.sum()
        if dropped > 0:
            print(f"Scopus: Dropped {dropped} rows without both India and Switzerland affiliations")

        scopus_df = scopus_df[both_mask].copy()

    scopus_df["period"] = scopus_df["sourcefile"].apply(_infer_period)

    return scopus_df


def _infer_period(sourcefile: str) -> str:
    """Infer period from sourcefile name.

    Logic:
    - contains '2024_' -> '2024'
    - contains '06-2025' -> 'Jun-2025'
    - contains '09-2025' -> 'Sep-2025'
    - else -> 'Other'
    """
    if "2024_" in sourcefile:
        return "2024"
    elif "06-2025" in sourcefile:
        return "Jun-2025"
    elif "09-2025" in sourcefile:
        return "Sep-2025"
    else:
        return "Other"


def _empty_scopus_dataframe() -> pd.DataFrame:
    """Return an empty Scopus dataframe with the correct schema."""
    mapping, _ = load_rename_mapping(PREP_TABLES_DIR / "scopus_names_for_merging.csv")
    cols = list(mapping.values()) + ["sourcefile", "period"]
    cols = [c for c in cols if c != "IGNORE"]
    return pd.DataFrame({c: pd.Series(dtype=str) for c in cols})


def write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    """Write dataframe to parquet using pyarrow engine."""
    df.to_parquet(output_path, engine="pyarrow", index=False)


def print_summary(wos_df: pd.DataFrame, scopus_df: pd.DataFrame) -> None:
    """Print summary statistics."""
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)

    print(f"\nWeb of Science:")
    print(f"  Total rows: {len(wos_df):,}")
    if not wos_df.empty and "doi" in wos_df.columns:
        unique_dois = wos_df["doi"].notna().sum()
        print(f"  Rows with DOI: {unique_dois:,}")
    if not wos_df.empty and "period" in wos_df.columns:
        period_counts = wos_df["period"].value_counts().sort_index()
        for period, count in period_counts.items():
            print(f"    {period}: {count:,}")

    print(f"\nScopus:")
    print(f"  Total rows: {len(scopus_df):,}")
    if not scopus_df.empty and "doi" in scopus_df.columns:
        unique_dois = scopus_df["doi"].notna().sum()
        print(f"  Rows with DOI: {unique_dois:,}")
    if not scopus_df.empty and "period" in scopus_df.columns:
        period_counts = scopus_df["period"].value_counts().sort_index()
        for period, count in period_counts.items():
            print(f"    {period}: {count:,}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    raw_dir = raw_data_dir()

    print(f"Loading data from: {raw_dir}")

    wos_df = load_wos(raw_dir)
    scopus_df = load_scopus(raw_dir)

    wos_path = INTERIM_DIR / "wos.parquet"
    scopus_path = INTERIM_DIR / "scopus.parquet"

    print(f"\nWriting WoS to: {wos_path}")
    write_parquet(wos_df, wos_path)

    print(f"Writing Scopus to: {scopus_path}")
    write_parquet(scopus_df, scopus_path)

    print_summary(wos_df, scopus_df)
    print(f"\nDone. Output files ready at {INTERIM_DIR}/")
