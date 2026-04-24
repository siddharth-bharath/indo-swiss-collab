import os
from pathlib import Path

DB_PATH = Path(os.environ.get("ISRD_DB_PATH", "dev_data/indo_swiss_research_dev.duckdb"))
RESULTS_PER_PAGE = int(os.environ.get("ISRD_RESULTS_PER_PAGE", "100"))
