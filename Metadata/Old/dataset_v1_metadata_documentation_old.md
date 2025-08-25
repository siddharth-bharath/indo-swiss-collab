---
output:
  word_document: default
  html_document: default
---



# Indo-Swiss Research Collaboration Database - Dataset Metadata Documentation

## Overview
This documentation describes the four primary datasets created during the Indo-Swiss research collaboration analysis project. All datasets are stored in Parquet format for efficient storage and analysis.

---

## 1. `publications_full_dataset_2000-2024.parquet`
**Primary publication-level dataset with enhanced bibliographic metadata**

### Description
The main publication dataset containing comprehensive bibliographic information for 24,979 unique Indo-Swiss collaborative research publications from 2000-2024. This dataset integrates metadata from OpenAlex, Web of Science, and Scopus databases.

### Key Characteristics
- **Rows**: 24,979 publications
- **Columns**: 41 fields
- **Primary Key**: `work_id` (OpenAlex identifier)
- **Date Range**: 2000-2024
- **Data Sources**: OpenAlex (primary), Web of Science, Scopus

### Critical Fields
- **Core Identifiers**: `work_id`, `doi`, `title`
- **Publication Info**: `publication_date`, `publication_year`, `cited_by_count`
- **Research Classification**: 
  - `primary_topic_name`, `primary_field_name`, `primary_domain_name`
  - `primary_topic_score` (confidence: 0-1 scale)
- **Content**: `abstract` (enhanced from multiple sources), `document type`
- **Enhanced Data**: `funding_details`, `funding_text`, multiple keyword fields
- **Author/Institution Summary**: `authors`, `institutions`, `countries`, `nAuthors`

### Data Quality
- **Abstract coverage**: 91.8% (22,929/24,979)
- **Citation data**: 85.1% (21,264/24,979)
- **Topic classification**: 97.6% (24,392/24,979)
- **Funding information**: 53.0% (13,234/24,979)

### Use Cases
- Bibliometric analysis and trend identification
- Research impact assessment
- Topic and domain analysis
- Funding pattern analysis
- Publication timeline studies

---

## 2. `authors_processed_flat.parquet`
**Flat author-publication relationship dataset with institutional affiliations**

### Description
A comprehensive flat file containing individual author-publication records with parsed institutional affiliations and country information. Each row represents one author's participation in one publication.

### Key Characteristics
- **Rows**: 5,399,835 author-publication records
- **Columns**: 12 fields
- **Granularity**: One row per author per publication
- **Processing**: JSON affiliation data parsed and standardized

### Critical Fields
- **Identifiers**: `work_id`, `author_id`, `display_name`, `orcid`
- **Publication Role**: `author_position`, `is_corresponding`
- **Raw Data**: `affiliations` (original JSON), `affiliation_raw`
- **Processed Affiliations**: 
  - `institutions_with_country` (format: "Institution Name, CC")
  - `author_countries` (comma-separated country codes)
- **Metrics**: `n_institutions_author`, `n_countries_author`

### Data Quality
- **Institution Coverage**: 97.0% of records have institutional data
- **Country Coverage**: 97.0% of records have country information
- **Processing Time**: 86 seconds for 5.4M records
- **Unique Affiliations**: 82,284 JSON records processed

### Use Cases
- Author collaboration network analysis
- Institutional mobility tracking
- Author-level productivity analysis
- Multi-affiliation pattern studies
- Geographic collaboration mapping

---

## 3. `authors_summary_with_lists.parquet`
**Author-level aggregated dataset with nested institutional and country work counts**
### Description
A highly processed author-centric dataset that aggregates all publications per unique author, including nested list columns containing work counts by institution and country. Version 2 introduces a sophisticated collaboration classification system that provides nuanced insights into India-Switzerland research partnerships.

### Key Characteristics
- **Rows**: 556,125 unique authors
- **Columns**: 11 fields (including 2 list columns)
- **Aggregation Level**: One row per unique author
- **Complex Data Types**: List columns containing data.tables
- **Enhancement**: Advanced collaboration status categorization

### Critical Fields
- **Author Identity**: `author_id`, `name`, `orcid`
- **Productivity Metrics**: `nWorks`, `n_corresponding_works`
- **Institutional Diversity**: `total_institutions`, `total_countries`
- **List Columns**:
  - `institution_work_counts`: data.table(institutions, n_works)
  - `country_work_counts`: data.table(countries, n_works)
- **Enhanced Collaboration Classification**: `collab_status` (categorical)

### Collaboration Status Classification (NEW)
The `collab_status` variable provides a comprehensive categorization of author collaboration patterns with India (IN) and Switzerland (CH):

#### Category Definitions:
- **"None"** (466,823 authors, 83.9%): Authors with neither Indian nor Swiss institutional affiliations
- **"CH"** (53,290 authors, 9.6%): Authors with Swiss affiliations but never Indian affiliations
- **"IN"** (28,404 authors, 5.1%): Authors with Indian affiliations but never Swiss affiliations
- **"Joint"** (5,886 authors, 1.1%): Authors with true India-Switzerland collaboration (both IN and CH affiliations appearing in the same publication)
- **"Both"** (1,722 authors, 0.3%): Authors with both Indian and Swiss affiliations across their career, but never in the same publication

#### Analytical Significance:
- **True Collaborators**: "Joint" category represents genuine bilateral research partnerships
- **Mobile Researchers**: "Both" category indicates researchers who have worked in both countries separately
- **National Contributors**: "IN" and "CH" categories show country-specific research participation
- **International Context**: "None" category provides baseline for global research landscape

### Use Cases
- Author productivity analysis
- International collaboration pattern identification
- Institutional affiliation diversity studies
- Career trajectory analysis
- Research mobility assessment

---

## 4. `institutional_relationships_IN_CH.parquet`
**Institution-centric dataset for India and Switzerland organizations**

### Description
A relational database-ready dataset focusing exclusively on institutions from India (IN) and Switzerland (CH), containing publication and author linkages for each institution.

### Key Characteristics
- **Rows**: 2,250 unique institutions
- **Columns**: 6 fields
- **Geographic Scope**: India and Switzerland only
- **Relational Structure**: Institution-to-publications mapping

### Critical Fields
- **Institution Identity**: `institution_name`, `country_code`
- **Publication Linkage**: `work_ids` (semicolon-separated publication IDs)
- **Productivity Metrics**: `n_publications`, `n_authors`
- **Author Linkage**: `author_names` (semicolon-separated author names)

### Top Institutions by Publication Count
1. **ETH Zurich** (CH): 3,448 publications, 3,274 authors
2. **University of Zurich** (CH): 2,834 publications, 2,257 authors
3. **European Organization for Nuclear Research** (CH): 2,802 publications, 8,693 authors
4. **Tata Institute of Fundamental Research** (IN): 2,553 publications, 888 authors
5. **Panjab University** (IN): 2,494 publications, 413 authors

### Use Cases
- Institutional collaboration network analysis
- Bilateral research partnership assessment
- Institution-level productivity benchmarking
- Research capacity mapping
- Policy-relevant institutional analysis

---

## Dataset Relationships and Integration

### Primary Linkage Keys
- **`work_id`**: Links publications across all datasets
- **`author_id`**: Links author records between flat and summary datasets
- **`institution_name` + `country_code`**: Links institutional data

### Data Lineage
1. **Source**: OpenAlex, Web of Science, Scopus raw data
2. **Enhanced**: `publications_full_dataset_2000-2024.parquet`
3. **Processed**: `authors_processed_flat.parquet` (JSON parsing)
4. **Aggregated**: `authors_summary_with_lists.parquet` (author-level)
5. **Specialized**: `institutional_relationships_IN_CH.parquet` (institutional focus)

### Technical Specifications
- **File Format**: Parquet (compressed, columnar storage)
- **Processing Framework**: R with data.table for performance
- **Total Processing Time**: ~7 minutes for complete pipeline
- **Storage Efficiency**: Parquet provides 60-80% size reduction vs CSV

### Quality Assurance
- **Zero data loss** during aggregation and deduplication
- **Consistent identifiers** across all datasets
- **Validated relationships** between publications, authors, and institutions
- **Geographic standardization** using ISO country codes

### Future Extensions
- **Annual or quarterly updates**: Framework supports incremental data additions
- **Additional databases**: Architecture allows integration of new sources to create a full fledged relational database
- **Enhanced cleaning**: Institutional name standardization in progress
- **Collaboration Maps**: Cleaned data is amenable to creating different kinds of collaboration maps.

---

## Usage Guidelines

### For Analysis
- Use `publications_full_dataset_2000-2024.parquet` for publication-level analysis
- Use `authors_processed_flat.parquet` for detailed author-publication relationships
- Use `authors_summary_with_lists.parquet` for author-centric analysis
- Use `institutional_relationships_IN_CH.parquet` for institutional network analysis

### For Database Integration
- All datasets maintain consistent `work_id` linkage
- Institutional dataset ready for relational database integration
- Author summary supports complex queries on nested data

### Performance Considerations
- Parquet format optimized for analytical queries
- List columns in author summary require special handling in some tools
- Flat dataset suitable for most standard analytical operations