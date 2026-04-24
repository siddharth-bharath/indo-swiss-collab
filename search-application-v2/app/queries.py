"""Parameterized DuckDB SQL queries for the search app."""

from app.config import RESULTS_PER_PAGE


def build_search_query(
    title_abstract=None,
    year_from=None,
    year_to=None,
    authors=None,
    affiliations=None,
):
    """Build a parameterized search query and return (sql_str, params_list).

    Args:
        title_abstract: optional substring for title or abstract
        year_from: optional int for >= publication_year
        year_to: optional int for <= publication_year
        authors: optional list of author name substrings (AND semantics)
        affiliations: optional list of institution name substrings (AND semantics)

    Returns:
        (sql_where_clause, params_list) where params are in order of ? placeholders
    """
    where_parts = []
    params = []

    # Title/abstract: case-insensitive substring
    if title_abstract:
        where_parts.append("(w.title ILIKE ? OR w.abstract ILIKE ?)")
        search_term = f"%{title_abstract}%"
        params.extend([search_term, search_term])

    # Year range
    if year_from is not None:
        where_parts.append("w.publication_year >= ?")
        params.append(year_from)
    if year_to is not None:
        where_parts.append("w.publication_year <= ?")
        params.append(year_to)

    # Authors: each entry must match at least one author (AND semantics across entries)
    if authors:
        for author_term in authors:
            where_parts.append(
                "EXISTS (SELECT 1 FROM work_authors wa "
                "JOIN authors a USING(author_id) "
                "WHERE wa.work_id = w.work_id AND a.display_name ILIKE ?)"
            )
            params.append(f"%{author_term}%")

    # Affiliations (institutions): each entry must match at least one institution (AND semantics)
    if affiliations:
        for affil_term in affiliations:
            where_parts.append(
                "EXISTS (SELECT 1 FROM work_institutions wi "
                "JOIN institutions i USING(inst_id) "
                "WHERE wi.work_id = w.work_id AND i.display_name ILIKE ?)"
            )
            params.append(f"%{affil_term}%")

    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    return where_clause, params


def search(conn, title_abstract=None, year_from=None, year_to=None, authors=None, affiliations=None, page=1):
    """Execute a search query with pagination.

    Returns:
        (results_list, total_count)
        where results_list is a list of dicts with keys:
        [work_id, title, abstract, doi, publication_year, source_display_name, institutions, authors]
    """
    where_clause, params = build_search_query(
        title_abstract=title_abstract,
        year_from=year_from,
        year_to=year_to,
        authors=authors or [],
        affiliations=affiliations or [],
    )

    # Get total count
    count_query = f"""
        SELECT COUNT(*) FROM works w
        WHERE {where_clause}
    """
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Get paginated results
    offset = (page - 1) * RESULTS_PER_PAGE
    results_query = f"""
        SELECT
            w.work_id, w.title, w.abstract, w.doi, w.publication_year,
            w.source_display_name,
            (SELECT STRING_AGG(DISTINCT i.display_name, '; ')
             FROM work_institutions wi JOIN institutions i USING (inst_id)
             WHERE wi.work_id = w.work_id) AS institutions,
            (SELECT STRING_AGG(a.display_name, '; ' ORDER BY wa.author_position)
             FROM work_authors wa JOIN authors a USING (author_id)
             WHERE wa.work_id = w.work_id
             ) AS authors
        FROM works w
        WHERE {where_clause}
        ORDER BY w.publication_year DESC, w.work_id
        LIMIT ? OFFSET ?
    """
    params.extend([RESULTS_PER_PAGE, offset])
    results = conn.execute(results_query, params).fetchall()

    # Convert to list of dicts
    results_list = [
        {
            "work_id": row[0],
            "title": row[1],
            "abstract": row[2],
            "doi": row[3],
            "publication_year": row[4],
            "source_display_name": row[5],
            "institutions": row[6],
            "authors": row[7],
        }
        for row in results
    ]

    return results_list, total_count


def download_all(conn, title_abstract=None, year_from=None, year_to=None, authors=None, affiliations=None):
    """Execute a search query without pagination, for CSV download.

    Returns:
        (results_list, total_count)
    """
    where_clause, params = build_search_query(
        title_abstract=title_abstract,
        year_from=year_from,
        year_to=year_to,
        authors=authors or [],
        affiliations=affiliations or [],
    )

    results_query = f"""
        SELECT
            w.work_id, w.title, w.abstract, w.doi, w.publication_year,
            w.source_display_name,
            (SELECT STRING_AGG(DISTINCT i.display_name, '; ')
             FROM work_institutions wi JOIN institutions i USING (inst_id)
             WHERE wi.work_id = w.work_id) AS institutions,
            (SELECT STRING_AGG(a.display_name, '; ' ORDER BY wa.author_position)
             FROM work_authors wa JOIN authors a USING (author_id)
             WHERE wa.work_id = w.work_id
             ) AS authors
        FROM works w
        WHERE {where_clause}
        ORDER BY w.publication_year DESC, w.work_id
    """
    results = conn.execute(results_query, params).fetchall()

    results_list = [
        {
            "work_id": row[0],
            "title": row[1],
            "abstract": row[2],
            "doi": row[3],
            "publication_year": row[4],
            "source_display_name": row[5],
            "institutions": row[6],
            "authors": row[7],
        }
        for row in results
    ]

    return results_list, len(results_list)
