import re
import pytest
from bs4 import BeautifulSoup


def _v1_post_search(client, **form):
    """Post to v1's /search and return (total_count, [dois] on page 1)."""
    resp = client.post("/search", data=form)
    html = resp.data.decode("utf-8") if hasattr(resp, 'data') else resp.text
    return _parse_results_html(html)


def _v2_post_search(client, **form):
    """TestClient form posting to v2's /search."""
    # TestClient.post expects dict or list of tuples
    resp = client.post("/search", data=form)
    return _parse_results_html(resp.text)


def _parse_results_html(html):
    """Extract (total_count, sorted_list_of_dois_on_page_1) from results.html.

    Looks for:
    - "Showing X results out of Y" pattern to extract total_count
    - DOI links: <a href="https://doi.org/{doi}" class="doi-link">...</a>
    """
    # Extract total count
    m = re.search(r"Showing\s+\d+\s+results\s+out\s+of\s+(\d+)", html)
    total = int(m.group(1)) if m else 0

    soup = BeautifulSoup(html, "html.parser")
    dois = []

    for a in soup.select("a.doi-link"):
        href = a.get("href", "")
        if href.startswith("https://doi.org/"):
            doi = href[len("https://doi.org/"):]
            dois.append(doi)

    return total, sorted(dois)


PARITY_CASES = [
    ("empty", {}),
    ("title_abstract=climate", {"title_abstract": "climate"}),
    ("title_abstract=quantum", {"title_abstract": "quantum"}),
    ("year_range_2020_2022", {"year_from": "2020", "year_to": "2022"}),
    ("year_from_only_2023", {"year_from": "2023"}),
    ("year_to_only_2005", {"year_to": "2005"}),
    ("affil_ETH_Zurich", {"affiliations": ["ETH Zurich"]}),
    ("affil_TIFR", {"affiliations": ["Tata Institute of Fundamental Research"]}),
    ("affil_UZH", {"affiliations": ["University of Zurich"]}),
    ("affil_two_AND", {"affiliations": ["ETH Zurich", "Indian Institute of Technology"]}),
    ("author_name_substring", {"authors": ["Gupta"]}),
    ("author_AND_affil", {"authors": ["Sharma"], "affiliations": ["ETH Zurich"]}),
    ("title_AND_year", {"title_abstract": "neural", "year_from": "2018", "year_to": "2021"}),
    ("author_two_AND", {"authors": ["Gupta", "Meier"]}),
    ("no_results_by_filter", {"title_abstract": "zzzzz-no-such-term"}),
]


@pytest.mark.parametrize("desc,form", PARITY_CASES, ids=[c[0] for c in PARITY_CASES])
def test_search_parity(v1_client, v2_client, desc, form):
    """Compare total_count between v1 and v2.

    Page-1 ordering can legitimately differ (v1 has no ORDER BY, v2 uses publication_year DESC).
    So we test total count only; if total counts match, both apps are filtering correctly.
    """
    form_with_page = {**form, "page": "1"}
    t1, dois1 = _v1_post_search(v1_client, **form_with_page)
    t2, dois2 = _v2_post_search(v2_client, **form_with_page)

    assert t1 == t2, f"[{desc}] total_count: v1={t1} v2={t2}"


INSTITUTION_SPOT_CHECKS = [
    ("ETH Zurich", 3448),
    ("University of Zurich", 2834),
    ("European Organization for Nuclear Research", 2802),
    ("Tata Institute of Fundamental Research", 2553),
    ("Panjab University", 2494),
]


@pytest.mark.parametrize("inst,expected", INSTITUTION_SPOT_CHECKS,
                         ids=[s[0] for s in INSTITUTION_SPOT_CHECKS])
def test_institution_spot_count(v2_client, inst, expected):
    """v2 institution counts vs Phase-1 report numbers.

    Tolerance +/-20: Phase-1 numbers came from a structured institutional_relationships
    table, while v2 uses substring match on normalized institution names. Small drift is
    expected, including contributions from rows that had null OpenAlex work_ids (now
    included in v2 via synthetic IDs, whereas Phase-1 counts came from a narrower table).
    v1<>v2 parity itself is tested separately in test_search_parity.
    """
    t, _ = _v2_post_search(v2_client, affiliations=[inst], page="1")
    assert abs(t - expected) <= 20, f"{inst}: v2={t} expected~{expected}"


def test_autocomplete_authors_parity(v1_client, v2_client):
    """Compare author autocomplete lists between v1 and v2.

    v1 has ~53,045 unique author names from authors_summary_in_ch.parquet.
    Allow up to 10 differences for edge cases.
    """
    r1 = v1_client.get("/authors")
    r2 = v2_client.get("/authors")

    # v1 returns a Flask response; extract JSON
    j1 = r1.get_json() if hasattr(r1, 'get_json') else r1.json
    if callable(j1):
        j1 = j1()

    # v2 returns TestClient response
    j2 = r2.json()

    a1 = set(j1.get("authors", []))
    a2 = set(j2.get("authors", []))

    sym = a1.symmetric_difference(a2)
    assert len(sym) <= 10, (
        f"author autocomplete differs by {len(sym)} entries "
        f"(v1 count={len(a1)}, v2 count={len(a2)})"
        f"\n  v1 only (sample): {sorted(list(a1 - a2))[:5]}"
        f"\n  v2 only (sample): {sorted(list(a2 - a1))[:5]}"
    )


def test_autocomplete_institutions_parity(v1_client, v2_client):
    """Compare institution autocomplete lists between v1 and v2.

    v1 has ~2,250 unique institutions; v2 has ~2,235.
    Allow up to 30 differences for minor normalization variations.
    """
    r1 = v1_client.get("/institutions")
    r2 = v2_client.get("/institutions")

    j1 = r1.get_json() if hasattr(r1, 'get_json') else r1.json
    if callable(j1):
        j1 = j1()

    j2 = r2.json()

    i1 = set(j1.get("institutions", []))
    i2 = set(j2.get("institutions", []))

    sym = i1.symmetric_difference(i2)
    assert len(sym) <= 30, (
        f"institution autocomplete differs by {len(sym)} entries "
        f"(v1 count={len(i1)}, v2 count={len(i2)})"
        f"\n  v1 only (sample): {sorted(list(i1 - i2))[:5]}"
        f"\n  v2 only (sample): {sorted(list(i2 - i1))[:5]}"
    )
