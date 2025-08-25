# Indo-Swiss Research Collaboration Database — Comprehensive Metadata (v1)

**Author:** Siddharth Bharath, Pranshu Jaiswal  
**Contact:** siddharth.bharath@protonmail.com  
**GitHub Repository:** [indo-swiss-collab](https://github.com/siddharth-bharath/indo-swiss-collab)  
**Date Generated:** 2025-08-15

## Overview
This document contains metadata of the products of Phase 1 of the Indo Swiss Research Collaboration Database, last edited on 15 August 2025. The database covers the time range of 2000-2024. 

Data is stored in Parquet files, which are a modern, efficient way to save large tables of data. Parquet files are like digital spreadsheets, but they are specially designed to be fast and compact, making it easy to store and analyze big datasets. They can be opened and used by many data tools and programming languages.

It covers:

- All Parquet deliverables and their schemas
- Topics hierarchy from OpenAlex and storage
- Short R helpers you can run to verify schemas

All file paths are relative to the project root.

---

## A. Final analytical datasets (Parquet)

### 1. `Data/publications_full_dataset_2000-2024.parquet`
Primary publication-level dataset with enhanced bibliographic metadata for 24,979 OpenAlex works (2000–2024).

- Primary key: `work_id` (OpenAlex short ID)
- Sources: OpenAlex (primary), Web of Science, Scopus
- Notes: retractions filtered; document type lowercased.

Columns and descriptions:
- `work_id`: OpenAlex work identifier (short form)
- `doi`: DOI in lowercase
- `title`: harmonized title
- `display_name`: OpenAlex display name (same as title for most entries)
- `publication_date`: full date
- `publication_year`: numeric year
- `cited_by_count`: citations (max across sources)
- `document type`: normalized doc type (lowercase)
- `is_oa`: open-access boolean
- `source_display_name`: journal/venue name
- `source_id`: OpenAlex source id
- `issn_l`: linking ISSN
- `host_organization`: publisher org id
- `host_organization_name`: publisher org name
- `landing_page_url`: landing page URL
- `pdf_url`: PDF URL when present
- `license`: license string
- `version`: version label (e.g., submitted, published)
- `ids`: JSON of identifiers across sources
- `abstract`: abstract text (OpenAlex or enhanced)
- `is_retracted`: boolean retraction flag (filtered upstream)
- `grants`: OpenAlex grants JSON when present
- `primary_topic_id`: OpenAlex topic id for primary topic
- `primary_topic_name`: primary topic name
- `primary_topic_score`: classification confidence (0–1)
- `primary_subfield_id`: OpenAlex subfield id
- `primary_subfield_name`: subfield name
- `primary_field_id`: field id
- `primary_field_name`: field name
- `primary_domain_id`: domain id
- `primary_domain_name`: domain name
- `funding_details`: enhanced consolidated funding details (longest text from WoS/Scopus)
- `funding_text`: enhanced funding acknowledgement text
- `author_keywords`: author-provided keywords (WoS/Scopus enhanced)
- `index_keywords_scopus`: Scopus index keywords
- `keywords_plus_wos`: WoS Keywords Plus
- `authors`: semicolon-separated author names (aggregated)
- `institutions`: semicolon-separated institution names with country codes
- `countries`: comma-separated ISO country codes appearing in the paper
- `nAuthors`: number of authors
- `institution_ids`: semicolon-separated OpenAlex institution ids in the paper
- `ror_ids`: semicolon-separated ROR ids in the paper

Typical usage:
- Publication-level analysis, funding and topic analysis, linking to institutions (`inst_id`) and topics (`topic_id`) via the relational DB.

### 2. `Data/authors_processed_flat.parquet`
Flat author–publication dataset with parsed affiliations and countries. One row per author per work.

Columns:
- `work_id`: OpenAlex work id
- `author_id`: OpenAlex author id
- `display_name`: author display name
- `orcid`: ORCID when present
- `author_position`: integer author order
- `is_corresponding`: boolean corresponding author flag
- `affiliations`: original JSON of affiliations
- `affiliation_raw`: raw affiliation string (if present)
- `institutions_with_country`: semicolon-separated “Institution Name, CC”
- `author_countries`: comma-separated country codes for the author on this work
- `n_institutions_author`: count of institutions for this author on this work
- `n_countries_author`: count of unique countries for this author on this work

### 3. `Data/authors_summary_with_lists.parquet`
Author-level aggregates with nested list columns and collaboration categorization.

Columns:
- `author_id`: OpenAlex author id
- `name`: author display name
- `orcid`: ORCID
- `nWorks`: number of unique works from that author in this database.
- `n_corresponding_works`: number of works where corresponding
- `total_institutions`: count of unique institutions across works
- `total_countries`: count of unique countries across works
- `institution_work_counts`: nested table with columns `institutions`, `n_works`
- `country_work_counts`: nested table with columns `countries`, `n_works`
- `collab_status`: one of {`Joint`, `Both`, `IN`, `CH`, `None`}
- `has_india_swiss_collab`: boolean flag for per-work IN–CH joint presence

### 4. `Data/institutional_relationships_IN_CH.parquet` (+ `Data/institutional_relationships_IN_CH.xlsx`)
Institution-centric table restricted to India and Switzerland.

Columns:
- `inst_id`: OpenAlex institution id
- `institution_name`: cleaned institution name
- `country_code`: `IN` or `CH`
- `ror`: ROR id when available
- `work_ids`: semicolon-separated work ids for the institution
- `n_publications`: number of unique works
- `n_authors`: number of unique authors
- `author_names`: semicolon-separated author display names

### 5. `Data/institutional_list_IN_CH.xlsx`
Complete list of all Swiss and Indian institutions in this database (2,690 entries). Simplified institution-level summary table.

Columns:
- `inst_id`: OpenAlex institution id
- `institution_name`: cleaned institution name
- `country_code`: `IN` or `CH`
- `n_publications`: number of unique works
- `n_authors`: number of unique authors

### 6. `Data/publications_with_institutions_countries.parquet`
Aggregated work-level summary table providing per-work counts and combined lists of authors, affiliations, institutions, and countries, derived from expanded author–affiliation data. Useful for quickly analyzing the composition and international scope of each work.

Columns:
- `work_id`
- `authors_combined`: semicolon-separated authors
- `n_authors`: number of authors
- `n_corresponding`: count corresponding authors
- `n_authors_with_orcid`: authors with ORCID
- `n_authors_with_affiliations`: authors with affiliations
- `institutions_combined`: semicolon-separated institutions with country codes
- `countries_in_paper`: comma-separated ISO country codes
- `institution_ids_combined`: semicolon-separated OpenAlex institution ids
- `ror_ids_combined`: semicolon-separated ROR ids

### 7. `Data/work_institution_links.parquet`
Normalized many-to-many mapping for later creation of relational database.

Columns:
- `work_id`: OpenAlex work id (short form)
- `inst_id`: OpenAlex institution id
- `institution_name`: institution display name
- `ror`: ROR id
- `country_code`: ISO country code

### 8. `Data/work_topic_links.parquet`
All OpenAlex topics matched to each work (long format).

Columns:
- `work_id`: OpenAlex work id (short form)
- `topic_id`: OpenAlex topic id
- `topic_name`: topic display name
- `topic_score`: topic association score
- `is_primary`: boolean primary-topic flag

---

## B. Topics hierarchy from OpenAlex

The topics taxonomy is built once and stored in `openAlex_topics.sqlite` with four linked tables mirroring OpenAlex:

- `domains(domain_id, display_name, description, works_count, created_date, updated_date)`
- `fields(field_id, display_name, description, works_count, domain_id, created_date, updated_date)`
- `subfields(subfield_id, display_name, description, works_count, field_id, created_date, updated_date)`
- `topics(topic_id, display_name, description, works_count, cited_by_count, subfield_id, created_date, updated_date)`

How topics attach to works:
- Primary hierarchy per work written into `publications_full_dataset_2000-2024.parquet` via `primary_*` columns.
- All topic matches per work saved in `Data/work_topic_links.parquet` and loaded to the `work_topics` table in SQLite for analytics.

Convenience: The joined domain–field–subfield view is also exported to a Google Sheet (“OpenAlex_subfields”) for browsing.

---



## C. Usage notes

- For publication-level analytics use `publications_full_dataset_2000-2024.parquet`.
- For author-centric analysis use `authors_processed_flat.parquet` + `authors_summary_with_lists.parquet`.
- For institution-centric analysis use `institutional_relationships_IN_CH.parquet`.
- For topic analytics either use `work_topic_links.parquet` or the `work_topics` table and `topic_hierarchy` view.

Quality/consistency:
- Identifiers normalized and stable; deduplication applied; ISO country codes used.
- Funding details and text enhanced by longest-source heuristic; keywords merged from all sources.

---

Run this R Script below to check the details of the files.

```r
library(arrow)
library(DBI)
library(RSQLite)
library(dplyr)
library(vctrs)
library(purrr)

describe_parquet <- function(path) {
  cat("\n=== ", path, " ===\n", sep = "")
  dt <- arrow::read_parquet(path)
  cat("Rows:", nrow(dt), "\n")
  cat("Columns:", ncol(dt), "\n")
  tibble(name = names(dt), type = map_chr(dt, vctrs::vec_ptype_full))
}

# Parquet assets
describe_parquet('Data/publications_full_dataset_2000-2024.parquet')
describe_parquet('Data/authors_processed_flat.parquet')
describe_parquet('Data/authors_summary_with_lists.parquet')
describe_parquet('Data/publications_with_institutions_countries.parquet')
describe_parquet('Data/work_institution_links.parquet')
describe_parquet('Data/institutional_relationships_IN_CH.parquet')
describe_parquet('Data/work_topic_links.parquet')
```