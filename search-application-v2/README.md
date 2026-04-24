# Indo-Swiss Collab Search App v2

FastAPI + DuckDB rewrite of the search interface.

## Local Development

1. Install dependencies:
   ```bash
   cd search-application-v2
   /home/siddharth/.config/genwise/venv/bin/pip install -r requirements.txt
   ```

2. Build the dev DuckDB:
   ```bash
   /home/siddharth/.config/genwise/venv/bin/python scripts/build_dev_db.py
   ```

3. Run the app:
   ```bash
   ISRD_DB_PATH=dev_data/indo_swiss_research_dev.duckdb \
     /home/siddharth/.config/genwise/venv/bin/python -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload
   ```

4. Visit http://127.0.0.1:8000 in your browser.

## Routes

- `GET /` - Home page with search form
- `GET /about` - About page
- `GET /institutions` - JSON list of IN/CH institutions (autocomplete)
- `GET /authors` - JSON list of IN/CH authors (autocomplete)
- `POST /search` - Search with pagination
- `POST /download` - Download all results as CSV

## Notes

- DOI field is accepted in forms but NOT used for filtering (preserves v1 behavior).
- Author and institution filters use AND semantics (all must match).
- Title/abstract search is case-insensitive substring match.
