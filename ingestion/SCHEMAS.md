# Ingestion output contracts

Strict output schemas for each step. Subagents implementing scripts must match these exactly — downstream steps depend on column names and types.

The schemas mirror the Phase 1 deliverables documented in `Metadata/dataset_v1_metadata_documentation.md` and `Metadata/relational_db_documentation.md`. When uncertain, prefer the documented schema in `Metadata/` over this file, and raise the mismatch.

---

## 01 → `interim/wos.parquet`, `interim/scopus.parquet`

Columns are the `name_to` values from `prep-tables/wos_names_for_merging.csv` and `prep-tables/scopus_names_for_merging.csv` (drop any column mapped to `IGNORE`). Plus:

- `sourcefile` — string, filename stripped of the `wos_`/`scopus_` prefix
- `period` — string, inferred from sourcefile (`2024`, `Jun-2025`, `Sep-2025`, else `Other`)

Filter rule: retain only rows where both India and Switzerland appear in the affiliations / addresses column (per `data_import.Rmd` lines 104–126).

---

## 02 → `interim/openalex_works.parquet`

One row per OpenAlex work. Columns (from OpenAlex `/works` endpoint; `clean_id` strips URL prefixes):

- `work_id` (str, stripped `W` form, e.g. `W1234567`)
- `doi` (str, lowercase, prefix stripped)
- `title` (str)
- `display_name` (str)
- `publication_date` (date)
- `publication_year` (int)
- `cited_by_count` (int)
- `type` (str, lowercased OpenAlex type)
- `is_oa` (bool)
- `is_retracted` (bool)
- `primary_location` (JSON str)
- `source_display_name`, `source_id`, `issn_l`, `host_organization`, `host_organization_name`, `landing_page_url`, `pdf_url`, `license`, `version` (strs)
- `ids` (JSON str of per-source identifiers)
- `topics` (JSON str of the full topics array from OpenAlex)
- `keywords` (JSON str of OpenAlex keywords)
- `grants` (JSON str)
- `abstract` (str, reconstructed from `abstract_inverted_index`)
- `countries_distinct_count`, `institutions_distinct_count` (int)
- `is_authors_truncated` (bool)

## 02 → `interim/openalex_authorships.parquet`

One row per (work, author). Columns:

- `work_id` (str)
- `author_id` (str, stripped `A` form)
- `display_name` (str)
- `orcid` (str)
- `author_position` (str: `first` / `middle` / `last`)
- `is_corresponding` (bool)
- `affiliations` (JSON str — list of {inst_id, ror, display_name, country_code, lineage, type})
- `affiliation_raw` (str)

---

## 03 → `output/publications_full_dataset_<label>.parquet`

Must match `Metadata/dataset_v1_metadata_documentation.md` §A.1 exactly. Columns include `work_id`, `doi`, `title`, `display_name`, `publication_date`, `publication_year`, `cited_by_count`, `document type` (note space), `is_oa`, `source_display_name`, `source_id`, `issn_l`, `host_organization`, `host_organization_name`, `landing_page_url`, `pdf_url`, `license`, `version`, `ids`, `abstract`, `is_retracted`, `grants`, `primary_topic_*`, `primary_subfield_*`, `primary_field_*`, `primary_domain_*`, `funding_details`, `funding_text`, `author_keywords`, `index_keywords_scopus`, `keywords_plus_wos`, `authors`, `institutions`, `countries`, `nAuthors`, `institution_ids`, `ror_ids`.

Enhancement rules (from `WoS-Scopus-openAlex_merging.rmd`):
- `cited_by_count`: max across sources
- `abstract`: prefer OpenAlex, fill gaps from Scopus, then WoS, longest wins on tie
- `funding_details`, `funding_text`: longest non-empty across sources
- `author_keywords`: semicolon-merge from all three sources, deduped
- `document type`: lowercased

## 03 → `output/work_topic_links.parquet`

Long-form mapping of every topic match per work. Columns: `work_id`, `topic_id`, `topic_name`, `topic_score`, `is_primary`.

---

## 04 → `output/authors_processed_flat.parquet`

One row per (work, author). Per `Metadata/dataset_v1_metadata_documentation.md` §A.2.
Columns: `work_id`, `author_id`, `display_name`, `orcid`, `author_position` (int order), `is_corresponding` (bool), `affiliations` (JSON str), `affiliation_raw`, `institutions_with_country` (semicolon-joined `Name, CC`), `author_countries` (comma-joined CCs), `n_institutions_author`, `n_countries_author`.

## 04 → `output/authors_summary_with_lists.parquet`

Per §A.3. Columns: `author_id`, `name`, `orcid`, `nWorks`, `n_corresponding_works`, `total_institutions`, `total_countries`, `institution_work_counts` (nested list of {institutions, n_works}), `country_work_counts` (nested list of {countries, n_works}), `collab_status` ∈ {`Joint`,`Both`,`IN`,`CH`,`None`}, `has_india_swiss_collab` (bool).

`collab_status` rules (from `data_openalex.r::create_author_summary_fast`):
- `Joint` — author has ≥1 work where both IN and CH appear on the author's own affiliations
- `Both` — author has had IN and CH affiliations but never on the same work
- `IN` — IN only
- `CH` — CH only
- `None` — neither

## 04 → `output/work_institution_links.parquet`

Per §A.7. Columns: `work_id`, `inst_id`, `institution_name`, `ror`, `country_code`.

## 04 → `output/institutional_relationships_IN_CH.parquet` (+ `.xlsx`)

Per §A.4, filtered to IN+CH only. Columns: `inst_id`, `institution_name`, `country_code` ∈ {`IN`,`CH`}, `ror`, `work_ids` (semicolon-joined), `n_publications`, `n_authors`, `author_names` (semicolon-joined).

## 04 → `output/authors_summary_in_ch.parquet`

Subset of `authors_summary_with_lists` where `collab_status ∈ {IN, CH, Joint, Both}`.

---

## 05 → `output/indo_swiss_research.duckdb`

Schema must replicate `data_assembly/create_DuckDB.R` exactly. See `Metadata/relational_db_documentation.md` for the full table/column list. Key invariants:

- All OpenAlex IDs stored as `BIGINT` with the letter prefix stripped (`W`, `A`, `I`, `T`, `F`, `S`, `D`).
- Views: `indo_swiss_works`, `topic_hierarchy`, `work_with_topics`.
- Indexes per `create_DuckDB.R` §8.
- Topic hierarchy loaded from existing `openAlex_topics.sqlite`.

---

## Parity acceptance criteria

For each output parquet, the Python implementation passes parity when:
1. `polars.scan_parquet(py).collect_schema() == polars.scan_parquet(r).collect_schema()` (column names and dtypes match — with documented exceptions below)
2. Row count matches exactly
3. Primary-key columns have identical set of values
4. For numeric aggregate columns, `sum()` and `mean()` match to 6 decimals
5. Spot queries documented in `tests/test_parity.py` agree

### Known R-baseline row counts (from `Data/` on Ubuntu laptop, 2026-04-24)

| Baseline file | Row count | Maps to Python step |
|---|---|---|
| `publication_details_WoS-Scopus.parquet` | 19,053 | post-merge of step 01 output |
| `publication_combined_2000_2024.parquet` | 24,907 | step 02 works, post-clean |
| `authorships_combined_2000_2024.parquet` | 5,399,835 | step 02 authorships |
| `publications_full_dataset_2000-2024.parquet` | 24,979 | step 03 primary deliverable |
| `authors_summary_in_ch.parquet` | 89,302 | step 04 filtered summary |

### Known R-baseline schema quirks to NOT replicate

- `publications_full_dataset_2000-2024.parquet` contains stray columns `institutions1` (String) and `nAuthors1` (Int32) that are not in `Metadata/dataset_v1_metadata_documentation.md`. Treat as R-pipeline artefacts; the Python output should follow the documented schema and omit them.
- `publication_combined_2000_2024.parquet` has column `type` (String); `publications_full_dataset_2000-2024.parquet` has `document type` (String, with a space) — do not auto-rename across steps unless the R pipeline does.

If a discrepancy is irreconcilable, document in `tests/parity_report.md` with a justification and a proposed schema change that Siddharth can approve.
