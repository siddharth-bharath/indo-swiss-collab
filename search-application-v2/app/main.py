import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import RESULTS_PER_PAGE
from app.db import get_connection, load_autocomplete_lists
from app.queries import download_all, search

autocomplete_authors: list[str] = []
autocomplete_institutions: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global autocomplete_authors, autocomplete_institutions
    conn = get_connection()
    autocomplete_authors, autocomplete_institutions = load_autocomplete_lists(conn)
    yield


app = FastAPI(lifespan=lifespan)

app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(app_dir / "templates"))


def _build_form_items(
    title_abstract: str,
    doi: str,
    year_from: str,
    year_to: str,
    authors: list[str],
    affiliations: list[str],
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if title_abstract:
        items.append(("title_abstract", title_abstract))
    if doi:
        items.append(("doi", doi))
    if year_from:
        items.append(("year_from", year_from))
    if year_to:
        items.append(("year_to", year_to))
    for a in authors:
        items.append(("authors", a))
    for i in affiliations:
        items.append(("affiliations", i))
    return items


@app.get("/", name="index")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/about", name="about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {})


@app.get("/institutions")
def get_institutions():
    return {"institutions": autocomplete_institutions}


@app.get("/authors")
def get_authors():
    return {"authors": autocomplete_authors}


@app.post("/search", name="search_results")
def search_results(
    request: Request,
    title_abstract: str = Form(default=""),
    doi: str = Form(default=""),
    year_from: str = Form(default=""),
    year_to: str = Form(default=""),
    authors: list[str] = Form(default=[]),
    affiliations: list[str] = Form(default=[]),
    page: int = Form(default=1),
):
    title_abstract_clean = title_abstract.strip() if title_abstract else ""
    doi_clean = doi.strip() if doi else ""
    year_from_clean = year_from.strip() if year_from else ""
    year_to_clean = year_to.strip() if year_to else ""
    authors_clean = [a.strip() for a in authors if a.strip()]
    affils_clean = [a.strip() for a in affiliations if a.strip()]

    form_items = _build_form_items(
        title_abstract_clean, doi_clean, year_from_clean, year_to_clean,
        authors_clean, affils_clean,
    )

    try:
        conn = get_connection()
        year_from_int = int(year_from_clean) if year_from_clean else None
        year_to_int = int(year_to_clean) if year_to_clean else None

        results_data, total_count = search(
            conn,
            title_abstract=title_abstract_clean or None,
            year_from=year_from_int,
            year_to=year_to_int,
            authors=authors_clean,
            affiliations=affils_clean,
            page=page,
        )

        total_pages = (total_count + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE if total_count > 0 else 0
        start_index = (page - 1) * RESULTS_PER_PAGE + 1 if total_count > 0 else 0
        end_index = min(page * RESULTS_PER_PAGE, total_count)

        return templates.TemplateResponse(
            request,
            "results.html",
            {
                "query": "Advanced Search",
                "results": results_data,
                "total_count": total_count,
                "current_page": page,
                "total_pages": total_pages,
                "start_index": start_index,
                "end_index": end_index,
                "search_type": "advanced",
                "form_items": form_items,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "results.html",
            {
                "query": "Advanced Search",
                "results": [],
                "error": str(e),
                "search_type": "advanced",
                "form_items": form_items,
            },
        )


@app.post("/download", name="download")
def download(
    title_abstract: str = Form(default=""),
    doi: str = Form(default=""),
    year_from: str = Form(default=""),
    year_to: str = Form(default=""),
    authors: list[str] = Form(default=[]),
    affiliations: list[str] = Form(default=[]),
):
    try:
        conn = get_connection()

        ta = title_abstract.strip() if title_abstract else None
        yf = int(year_from.strip()) if year_from.strip() else None
        yt = int(year_to.strip()) if year_to.strip() else None
        authors_clean = [a.strip() for a in authors if a.strip()]
        affils_clean = [a.strip() for a in affiliations if a.strip()]

        results_data, _ = download_all(
            conn,
            title_abstract=ta,
            year_from=yf,
            year_to=yt,
            authors=authors_clean,
            affiliations=affils_clean,
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results_{timestamp}.csv"

        output = io.StringIO()
        if results_data:
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "work_id", "title", "abstract", "doi", "publication_year",
                    "source_display_name", "institutions", "authors",
                ],
            )
            writer.writeheader()
            for row in results_data:
                writer.writerow(row)

        return StreamingResponse(
            iter([output.getvalue().encode("utf-8")]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return StreamingResponse(
            iter([f"Error: {str(e)}".encode("utf-8")]),
            media_type="text/plain",
        )
