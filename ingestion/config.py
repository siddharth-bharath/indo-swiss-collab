"""Shared paths and constants for the indo-swiss-collab ingestion pipeline.

Cross-platform: Ubuntu laptop uses ~/Data/ISRD/source_data,
Windows desktop uses D:/Data/ISRD/source_data. Override either with
the ISRD_SOURCE_DATA environment variable.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INGESTION_DIR = REPO_ROOT / "ingestion"
INTERIM_DIR = INGESTION_DIR / "interim"
OUTPUT_DIR = INGESTION_DIR / "output"

DATA_DIR = REPO_ROOT / "Data"
PREP_TABLES_DIR = REPO_ROOT / "prep-tables"
TOPICS_SQLITE = REPO_ROOT / "openAlex_topics.sqlite"
BASELINE_DUCKDB = REPO_ROOT / "indo_swiss_research.duckdb"

OPENALEX_MAILTO = "siddharth.bharath@protonmail.com"


def raw_data_dir() -> Path:
    override = os.environ.get("ISRD_SOURCE_DATA")
    if override:
        return Path(override).expanduser()
    if platform.system() == "Windows":
        return Path(r"D:\Data\ISRD\source_data")
    return Path.home() / "Data" / "ISRD" / "source_data"


for _d in (INTERIM_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
