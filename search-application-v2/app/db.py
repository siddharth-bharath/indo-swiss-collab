import duckdb
from app.config import DB_PATH

_connection = None
_autocomplete_cache = None


def get_connection():
    """Get a read-only DuckDB connection to the analytical database."""
    global _connection
    if _connection is None:
        _connection = duckdb.connect(str(DB_PATH), read_only=True)
    return _connection


def load_autocomplete_lists(conn):
    """Load autocomplete lists for authors and institutions at app startup.

    Returns:
        (authors_list, institutions_list) - both sorted lists of strings
    """
    global _autocomplete_cache
    if _autocomplete_cache is not None:
        return _autocomplete_cache

    authors_result = conn.execute(
        "SELECT DISTINCT display_name FROM authors "
        "WHERE collab_status IN ('IN','CH','Joint','Both') AND display_name IS NOT NULL "
        "ORDER BY display_name"
    ).fetchall()
    authors_list = [row[0] for row in authors_result]

    institutions_result = conn.execute(
        "SELECT DISTINCT display_name FROM institutions "
        "WHERE country_code IN ('IN','CH') AND display_name IS NOT NULL "
        "ORDER BY display_name"
    ).fetchall()
    institutions_list = [row[0] for row in institutions_result]

    _autocomplete_cache = (authors_list, institutions_list)
    return _autocomplete_cache
