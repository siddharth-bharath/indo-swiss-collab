# Indo-Swiss Research Collaboration Database: version 0.5 work log {#indo-swiss-research-collaboration-database:-version-0.5-work-log}

## 

[Indo-Swiss Research Collaboration Database: Phase 1 documentation](#indo-swiss-research-collaboration-database:-version-0.5-work-log)

[1\. Introduction](#1.-introduction)

[2\. Data Acquisition and Initial Processing](#2.-data-acquisition-and-initial-processing)

[2.1. Data Import and Consolidation](#2.1.-data-import-and-consolidation)

[2.2. Harmonisation of Data Fields](#2.2.-harmonisation-of-data-fields)

[2.3. Filtering for Indo-Swiss Collaborations](#heading=h.8lh3nyn4i418)

[3\. DOI-based Deduplication and Merging](#3.-doi-based-deduplication-and-merging)

[3.1. DOI Processing within Each Database](#3.1.-doi-processing-within-each-database)

[3.2. Merging WoS and Scopus Datasets using DOI](#3.2.-merging-wos-and-scopus-datasets-using-doi)

[3.3. Conflict Resolution in Merged Data](#3.3.-conflict-resolution-in-merged-data)

[4\. Author and Affiliation Data Processing](#4.-author-and-affiliation-data-processing)

[4.1. Web of Science Author Data Processing](#4.1.-web-of-science-author-data-processing)

[4.2. Scopus Author Data Processing](#4.2.-scopus-author-data-processing)

[4.3. Combining and Refining Author Datasets](#4.3.-combining-and-refining-author-datasets)

[5\. Institution Data Preparation](#5.-institution-data-preparation)

[5.1 Extraction of Institution Data](#5.1-extraction-of-institution-data)

[5.2 Standardisation of Institution Data](#5.2-standardisation-of-institution-data)

[6\. Database Structure and Outputs](#6.-database-structure-and-outputs)

[7\. Searchable interface to the database](#heading=h.yr74bza49u2q)

[Application Architecture](#heading=h.92zplajul9ds)

[Backend Logic (app.py)](#heading=h.s599lyx7y7yl)

[User Interface (index.html and results.html)](#heading=h.yajauowvu9ne)

[Data Handling and Querying](#heading=h.91htv71xo35e)

[Error Handling and User Feedback](#heading=h.kstrwi2a2nh0)

[8\. Alignment with Phase 1 Project Goals](#7.-alignment-with-phase-1-project-goals)

[9\. Future Work and Next Steps](#8.-future-work-and-next-steps)

[8.1. Advanced Classification of Research Fields](#8.1.-advanced-classification-of-research-fields)

[8.2. Development of Searchable Database Interface and Visualisations](#8.2.-development-of-searchable-database-interface-and-visualisations)

[8.3. Integration of SNSF Funding Data](#8.3.-integration-of-snsf-funding-data)

[8.4. Pilot Bibliometric Analyses](#8.4.-pilot-bibliometric-analyses)

[8.5. Further Data Refinement and Expansion in future phases](#8.5.-further-data-refinement-and-expansion-in-future-phases)

[8.6. Focused Bibliometric Analyses for Specific Interests](#8.6.-focused-bibliometric-analyses-for-specific-interests)

[Appendix A: Data Field Harmonisation](#appendix-a:-data-field-harmonisation)

[A.1 Web of Science Fields Retained](#a.1-web-of-science-fields-retained)

[A.2 Scopus Fields Retained](#a.2-scopus-fields-retained)

## 

##  

**Authors:** Siddharth Bharath, Pranshu Jaiswal, Manfred Max Bergman (University of Basel), Lena Robra (Swissnex in India)

**Data Acquisition Support:** Zinette Bergman (University of Basel), Sarah Thomforde (University of Basel)

## 1\. Introduction {#1.-introduction}

This document details the methodology employed to construct a database mapping research collaborations between India and Switzerland from 2000 to 2024\. This work has been carried out between February \- May 2024\. The primary objective of this phase was to acquire, clean, and structure publication metadata from Scopus and Web of Science to form a foundational dataset. This dataset is intended to support the identification of co-authored publications and group them by fields of research, research institutions, and researchers, thereby enabling initial bibliometric analyses and the development of a searchable database. This report provides a comprehensive account of the data assembly process, focusing on the key decisions made during data import, cleaning, merging, and the processing of author and institutional information.

The code that carries out the data processing was in the R Programming Language. AI assisted cleaning of data fields (for clearing institution names and research topics) was done in Python. We also created a search interface for the database using Python. All code for the project is publicly accessible on GitHub \- [https://github.com/siddharth-bharath/indo-swiss-collab](https://github.com/siddharth-bharath/indo-swiss-collab)

## 2\. Data Acquisition and Initial Processing {#2.-data-acquisition-and-initial-processing}

The data for this project were downloaded from the Scopus and Web of Science databases using the institutional access provided by the University of Basel, with assistance from Zinette Bergman and Sarah Thomforde.

We initiated the database construction by acquiring raw publication data from Web of Science (WoS) and Scopus. WoS data were provided as XLS files, and Scopus data as CSV files.

### 2.1. Data Import and Consolidation {#2.1.-data-import-and-consolidation}

We imported all source files for WoS and Scopus. For each database, we combined the data from multiple files into a single data structure. We then removed duplicate entries within each of these consolidated datasets to ensure unique records from each source before further processing.

### 2.2. Harmonisation of Data Fields {#2.2.-harmonisation-of-data-fields}

A critical early step was the harmonisation of data fields (column names) between the WoS and Scopus datasets, as they use different naming conventions for similar information. We then utilised predefined mapping tables to standardise these names. This process involved:

* Identifying columns that were not relevant to the project's scope and marking them for exclusion  
* Renaming the remaining relevant columns to a common, standardised set of names across both datasets.

(See Appendix A for a detailed list of fields used from Scopus and Web of Science and those that were ignored.)

### 2.3 Data import from OpenAlex

## 3\. DOI-based Deduplication and Merging {#3.-doi-based-deduplication-and-merging}

We used Digital Object Identifiers (DOIs) as the primary key for matching and deduplicating records from WoS and Scopus.

### 3.1. DOI Processing within Each Database {#3.1.-doi-processing-within-each-database}

Before merging, we processed and cleaned DOIs within each dataset:

* **Web of Science (WoS):**  
  * We determined that approximately 88% of WoS entries contained a DOI.  
  * We identified and addressed non-unique DOIs within the WoS dataset. When multiple entries shared the same DOI, we prioritised the record with a higher citation count. If citation counts were identical, we selected the entry with more comprehensive ORCID (Open Researcher and Contributor ID) information. This resulted in 13,931 unique DOI entries from WoS.  
* **Scopus:**  
  * Approximately 96% of Scopus entries included a DOI.  
  * We identified and resolved non-unique DOIs. Such duplicates often arose from instances like a single work appearing as both a book preface and a chapter. Our cleaning protocol prioritised entries that included an abstract. If abstracts were equally available or absent, we favoured entries with higher citation counts, followed by those with an earlier publication year. We treated the string "\[No abstract available\]" as a missing abstract. This process yielded 16,466 unique DOI entries from Scopus.

### 3.2. Merging WoS and Scopus Datasets using DOI {#3.2.-merging-wos-and-scopus-datasets-using-doi}

After the intra-database cleaning, we performed a full join of the WoS and Scopus datasets based on the cleaned, unique DOIs.

* We created a datasource column to indicate whether a publication record originated from 'Scopus' only, 'WoS' only, or was found in 'Both' databases. This resulted in 11,760 entries common to both, 4,706 entries only in Scopus, and 2,171 entries only in Web of Science.  
* The merged dataset, containing 18,637 unique publications with DOIs, was then prepared for further harmonisation.

### 3.3. Conflict Resolution in Merged Data {#3.3.-conflict-resolution-in-merged-data}

For records found in both databases, we addressed discrepancies in shared fields:

* **Publication Year:** If the publication years differed between WoS and Scopus for the same DOI, we selected the earlier year. We noted that 9 matched papers had a publication year difference greater than one year; for this set, we consistently chose the earlier year.  
* **Bibliographic Fields:** For several common bibliographic fields (article title, document type, publisher, ISBN, ISSN, open access status, issue, volume, PubMed ID, language, source title, and page count), we established a rule to prefer the information from Scopus over WoS data in instances of conflicting information.

We assigned a unique publication number (pubNum) to each entry in the merged dataset. We also renamed the primary affiliation fields from both sources to addresses.s (Scopus) and addresses.w (Web of Science) for clarity. The resulting merged and harmonised dataset was saved as an intermediate RData file.

## 4\. Author and Affiliation Data Processing {#4.-author-and-affiliation-data-processing}

We processed author and affiliation information, prioritising Web of Science data due to its generally more structured author-affiliation linking. For publications found only in Scopus, Scopus author data was used. The aim was to accurately identify the national affiliations of contributing researchers.

### 4.1. Web of Science Author Data Processing {#4.1.-web-of-science-author-data-processing}

For publications sourced from WoS or found in both databases, we extracted author information from the WoS fields for author full names and authors with affiliations.

* We split the authors with affiliations field, which often contains multiple authors and their respective institutions in a semi-structured format, into individual author-institution pairs.  
* We then parsed these pairs to extract distinct author names and their institutional affiliations.  
* To standardise country identification, we utilised the 'countries' R library. This library processed the institution strings and assigned a standardised country name (e.g., "Switzerland", "India"). The process involved cleaning common variations in country name representations (e.g., removing phrases like "(data truncated to fit)" or specific state/city information like "USA" when a broader country name was identifiable).  
* For each author associated with a publication, we determined their country category: 'Swiss' (only Swiss affiliations for that paper), 'India' (only Indian affiliations), 'Both' (affiliations in both Switzerland and India for that paper), or 'None' (affiliations only in other countries).  
* Finally, we structured this information by nesting all author details (name, institution, country, and country category) under each unique publication number. This processed author data from WoS was saved as an intermediate RData file.

### 4.2. Scopus Author Data Processing {#4.2.-scopus-author-data-processing}

For publications found only in Scopus, we extracted author information using the Scopus fields for author names and affiliations.

* The affiliations field in Scopus presented a challenge as it sometimes listed multiple institutions for a single author without clear delimiters. To parse this, we developed a method that involved splitting the affiliation string based on a predefined list of country names, effectively separating concatenated institutional addresses.  
* We then extracted author names and their corresponding parsed institutions.  
* Similar to the WoS data, we employed the 'countries' R library to assign standardised country names to these extracted institutions.  
* We categorised each author's national affiliation for the publication as 'Swiss', 'India', 'Both', or 'None'.  
* This processed Scopus author data was then nested by publication number and saved as an intermediate RData file.

### 4.3. Combining and Refining Author Datasets {#4.3.-combining-and-refining-author-datasets}

We loaded the main merged publication dataset and the two processed author datasets.

* To create a unified author information layer, we combined these datasets. For publications originating from 'WoS' or 'Both' data sources, we used the processed WoS author details. For publications found only in 'Scopus', we used the processed Scopus author details.  
* We performed a check to ensure all publications in the merged dataset had associated author details; the process was designed to halt if any entries lacked this information, indicating a potential issue in the upstream processing.  
* We then derived several new metrics for each publication based on the consolidated author and affiliation data. These metrics included:  
  * nCountries: Number of unique countries represented in the publication's authorship.  
  * nAuthors: Total number of unique authors.  
  * nInst: Number of unique institutions.  
  * nSwissInst: Number of unique Swiss institutions.  
  * nIndInst: Number of unique Indian institutions.  
  * nSwissAuth: Number of unique authors affiliated with Swiss institutions.  
  * nIndAuth: Number of unique authors affiliated with Indian institutions.  
  * nBothAuth: Number of unique authors identified with affiliations in both India and Switzerland for that specific publication.  
* We conducted a check to identify any publications where country-level parsing of affiliations might have failed (i.e., nCountries \< 1 or missing).  
* Finally, we harmonised remaining redundant columns that existed in both WoS and Scopus original files (e.g., author keywords, correspondence address, affiliations, author full names, authors). For entries sourced from 'WoS' or 'Both', we retained the WoS version of these fields; for 'Scopus-only' entries, we used the Scopus version.  
* The dataset, now enriched with detailed and combined author information, was saved as a consolidated RData file.

## 5\. Institution Data Preparation {#5.-institution-data-preparation}

### 5.1 Extraction of Institution Data {#5.1-extraction-of-institution-data}

To facilitate the analysis of institutional collaborations and to prepare for a necessary manual cleaning step, we extracted and structured institution-specific data.

* We unnested the author details from the combined dataset to create a flat table where each row represented an author-institution-publication link.  
* We filtered this table to include only affiliations located in India or Switzerland.  
* We then grouped the data by institution name, country, and the original data source (WoS, Scopus, or Both) to calculate the total number of unique publications (nPapers) and unique authors (nAuth) associated with each institution from each source.  
* This summarised institutional data was exported as a CSV file, named with the date of creation (e.g., institutions\_for\_cleaning\_20250314.csv), for manual review and cleaning of institution name variants.  
* An initial automated step towards cleaning involved extracting the primary institution name (typically the part of the affiliation string before the first comma) and converting it to lowercase to group similar entries.

### 5.2 Standardisation of Institution Data {#5.2-standardisation-of-institution-data}

Institutional affiliations as listed in scientific publications often lack standardisation, with variations in department names, campus listings, and abbreviations for a single institution. This makes accurate attribution of publications challenging.  
For example, the University of Basel appears under numerous variations, such as:

* "Department of Physics, University of Basel, Basel, Switzerland"  
* "Univ Basel, Dept Phys, Basel, Switzerland"  
* "Swiss Tropical and Public Health Institute, University of Basel, Basel, Switzerland"  
* "Univ Basel Hosp, CH-4031 Basel, Switzerland"  
* "Univ Basel, Dept Environm Sci, Basel, Switzerland"

Over 300 such variations exist for the University of Basel alone in the current database.

We developed an analysis pipeline employing Large Language Models (LLMs) to parse institution names and match them against a predefined list of approximately 100 Swiss federal research institutions, universities, cantonal universities, and publicly funded organisations. This reference list of Swiss institutions was generated from the Swiss National Science Foundation’s database of all organisations that have received grants from them. 

The swiss\_standardizer.py script automated the cleaning and standardization of Swiss institute names. It began by loading the raw institution data and two reference lists: one for Indian universities and another for Swiss research institutions. For each row in the dataset, the script checked if a standardized name already existed; if not, it constructed a prompt that included the raw institute name and the relevant country-specific reference list. It sent this prompt to the Anthropic Claude 3.5 Haiku model, which returned a single, standardized name matching the reference list if possible, or provided a best-effort standardization with an exclamation mark if no match was found, or '---' if it could not standardize.

The process ensured consistency by enforcing strict output rules in the prompt, such as maintaining standard abbreviations and including location information when available. The script iterated through each institution, applied the standardization logic, and saved the results incrementally to a CSV file to prevent data loss in case of interruptions. This approach leveraged both curated reference data and AI-driven text normalization, resulting in a cleaned and harmonized list of Swiss institute names suitable for downstream analysis or reporting.

A manual quality check of this AI standardised data is pending, as is setting up this pipeline for Indian institutions. More details on this in Section 9\. 

## 6\. Database Structure and Outputs {#6.-database-structure-and-outputs}

The primary outputs of this data assembly phase are two files:

* One file containing primarily publication-level bibliographic information. It includes the names and affiliations of all authors as directly derived from the publication metadata.  
* A file focused on author and institutional information, which contains publication identifiers and the nested author-affiliation details, along with author-based metrics. This is the file on which data cleaning of institutional names will be carried out.

## 7\. Alignment with Phase 1 Project Goals {#7.-alignment-with-phase-1-project-goals}

This data assembly work directly addresses several core goals outlined for Phase 1 of the "Mapping Indo-Swiss Research Collaborations" project:

* **Data Acquisition and Cleaning:** We successfully downloaded and processed metadata from Scopus and Web of Science for the 2000-2024 period. This involved extracting author, institution, country, abstract, and keyword information.  
* **Database Structuring:** We reconciled the two data sources, primarily using DOIs, to remove duplicates and structure the information into a single, more coherent database, represented by the main consolidated RData file and its derivatives.  
* **Foundation for Grouping Publications:** The processed database now contains the necessary fields to group publications by:  
  * **Research Institutions:** Extracted institution names are available and have been prepared for a cleaning phase.  
  * **Researchers:** Author names and their affiliations have been processed.  
  * **Fields of Research:** Keywords and abstracts are included in the database, which will serve as the basis for future classification efforts.  
* **Basis for Searchable Database and Bibliometric Analysis:** The structured RData files form the core dataset that will be used to develop searchable database functionalities and for conducting pilot bibliometric analyses, as envisioned in the project proposal.

While the integration of SNSF funding data and advanced machine learning for topic categorisation were mentioned as exploratory goals for Phase 1, the current work focused on establishing the foundational publication database from Web of Science and Scopus. These aspects remain key areas for subsequent development.

## 8\. Future Work and Next Steps {#8.-future-work-and-next-steps}

The completion of this data assembly phase lays the groundwork for several subsequent activities outlined in the project proposal. The following sections represent areas for future development based on the compiled database:

### 8.1. Advanced Classification of Research Fields {#8.1.-advanced-classification-of-research-fields}

Understanding the thematic areas of collaboration is crucial. Currently, the database primarily relies on the "Research Areas" classification provided by Web of Science, which categorises journals into 153 areas within five broad domains (Technology, Social Sciences, Physical Sciences, Life Sciences & Biomedicine, Arts & Humanities). This schema presents two main limitations:

* Classification is journal-based, leading to potential misclassification of multidisciplinary research papers or articles in broad-scope journals.  
* The existing categories are often not granular or intuitive enough for users seeking specific research topics. The classification tree is also relatively shallow.

A more nuanced and deeper classification tree would significantly improve the analysis and reporting of collaborative research topics.

### 8.2. Development of Searchable Database Interface and Visualisations {#8.2.-development-of-searchable-database-interface-and-visualisations}

(This section will outline plans for creating a user-friendly interface for searching the database and for developing visualisations to represent collaboration patterns, timelines, and institutional networks.)

### 8.3. Integration of SNSF Funding Data {#8.3.-integration-of-snsf-funding-data}

In the initial proposal for this project we thought to add data from the SNSF into the database. However, the grant-centric nature of the SNSF data made it difficult to match with the publication-centric approach that we adopted. Hence we have not integrated it in this project.

### 8.4. Pilot Bibliometric Analyses {#8.4.-pilot-bibliometric-analyses}

To be updated after analyses are updated

### 8.5. Further Data Refinement and Expansion in future phases {#8.5.-further-data-refinement-and-expansion-in-future-phases}

(This section will cover ongoing and future efforts in areas such as:)

* *Advanced Institution and Researcher Disambiguation.*  
* *Annual / semi-annual Database Updates with new publication data.*  
* *Expansion to Include Joint Grants and Other Collaboration Forms (beyond co-authored publications).*  
* *Expansion to Include Patents and other forms of intellectual property.*  
* *Exploration of Generative AI for Enhanced User Interaction with the database.*

### 8.6. Focused Bibliometric Analyses for Specific Interests {#8.6.-focused-bibliometric-analyses-for-specific-interests}

(This section will discuss the potential for more targeted analyses based on specific research or policy questions, building upon the foundational database and pilot analyses.)

# 

# 

# Appendix A: Data Field Harmonisation {#appendix-a:-data-field-harmonisation}

This appendix details the data fields that were selected and harmonised from the Web of Science (WoS) and Scopus databases for use in the final dataset. For each database, a mapping table was used internally to identify the original field name and assign a standardised "Harmonised Name". The "Inferred Meaning" column provides a brief description of the data contained in each harmonised field that was retained. Fields not listed in these tables were excluded from the final dataset.

### A.1 Web of Science Fields Retained {#a.1-web-of-science-fields-retained}

The following table lists the original Web of Science field names that were retained, their corresponding harmonised names, and their inferred meanings.

| Original WoS Field Name | Harmonised Name | Inferred Meaning |
| :---- | :---- | :---- |
| Publication Type | document type | Type of publication (e.g., Article, Review, Book). |
| Authors | authors.w | List of authors (WoS specific format). |
| Author Full Names | author full names.w | Full names of authors (WoS specific format). |
| Group Authors | group authors | Names of authoring groups or consortia. |
| Book Authors | book authors | Authors of a book (if applicable). |
| Book Group Authors | book group authors | Authoring groups for a book (if applicable). |
| Book Editors | book editors | Editors of a book (if applicable). |
| Article Title | article title.w | Title of the article or publication. |
| Source Title | source title.w | Title of the journal, book, or conference proceedings. |
| Document Type | document type.w | Type of document (e.g., Article, Letter, Editorial). |
| Conference Title | conference title | Title of the conference. |
| Conference Date | conference date | Date(s) of the conference. |
| Conference Location | conference location | Location of the conference. |
| Conference Sponsor | conference sponsor | Sponsoring organisation(s) of the conference. |
| Author Keywords | author keywords.w | Keywords provided by the authors. |
| Keywords Plus | keywords plus | Additional keywords generated by WoS indexing. |
| Abstract | abstract | Abstract or summary of the publication. |
| Addresses | addresses.w | Author affiliations (WoS specific format). |
| Correspondence Address | correspondence address.w | Address of the corresponding author. |
| Email Addresses | email addresses | Email addresses of authors. |
| Funder | funder | Funding organisations. |
| Publisher | publisher.w | Publisher of the work. |
| Publisher City | publisher city | City of the publisher. |
| Publisher Address | publisher address | Full address of the publisher. |
| Publication Year | year.w | Year of publication. |
| Volume | volume.w | Volume number of the journal or book series. |
| Issue | issue.w | Issue number of the journal. |
| Part Number | part number | Part number, if applicable. |
| Supplement | supplement | Supplement information, if applicable. |
| Special Issue | special issue | Special issue information, if applicable. |
| Beginning Page | page start | Starting page number. |
| Ending Page | page end | Ending page number. |
| Article Number | article number | Article number, if used instead of page numbers. |
| DOI | doi | Digital Object Identifier. |
| DOI Link | doi link | URL link to the DOI. |
| Book DOI | book doi | DOI for the book, if applicable. |
| PubMed ID | pubmed id.w | PubMed identification number. |
| ORCIDs | orcids | ORCID identifiers of authors. |
| ResearcherIDs (WoS) | researcherid\_wos | Web of Science ResearcherIDs. |
| ISSN | issn.w | International Standard Serial Number. |
| eISSN | eissn | Electronic International Standard Serial Number. |
| ISBN | isbn.w | International Standard Book Number. |
| Journal Abbreviation | journal abbreviation | Abbreviated title of the journal. |
| ISO Source Abbreviation | iso source abbreviation | ISO standard abbreviation for the source title. |
| Publication Date | publication date | Full publication date. |
| Times Cited, All Databases | times\_cited | Total citation count from all WoS databases. |
| IDS Number | ids number | WoS internal identification number. |
| UT (Unique ID) | ut | WoS Unique ID. |
| Language | language.w | Language of the publication. |
| Page Count | page count.w | Total number of pages. |

**WoS Fields Ignored (Original Name):** Reprint Address, Cited References, Number of Pages, WoS Categories, Research Areas, Book Series Title, Book Series Subtitle, Cited Reference Count, Times Cited, WoS Core, Open Access Designations, Highly Cited Status, Hot Paper Status, Date of Export, Source.

### A.2 Scopus Fields Retained {#a.2-scopus-fields-retained}

The following table lists the original Scopus field names that were retained, their corresponding harmonised names, and their inferred meanings.

| Original Scopus Field Name | Harmonised Name | Inferred Meaning |
| :---- | :---- | :---- |
| Authors | authors.s | List of authors (Scopus specific format). |
| Author full names | author full names.s | Full names of authors, often with Scopus IDs. |
| Author(s) ID | author\_scopus\_id | Scopus Author IDs. |
| Title | article title.s | Title of the article or publication. |
| Year | year.s | Year of publication. |
| Source title | source title.s | Title of the journal, book, or conference proceedings. |
| Volume | volume.s | Volume number of the journal or book series. |
| Issue | issue.s | Issue number of the journal. |
| Art. No. | article number | Article number, if used instead of page numbers. |
| Page start | page start | Starting page number. |
| Page end | page end | Ending page number. |
| Page count | page count.s | Total number of pages. |
| Cited by | times\_cited | Number of times the publication has been cited. |
| DOI | doi | Digital Object Identifier. |
| Link | link | URL link to the publication on Scopus. |
| Affiliations | affiliations.s | Author affiliations (Scopus specific format). |
| Authors with affiliations | authors with affiliations.s | Detailed author and affiliation strings. |
| Abstract | abstract | Abstract or summary of the publication. |
| Author Keywords | author keywords.s | Keywords provided by the authors. |
| Index Keywords | keywords plus | Keywords assigned by Scopus indexing. |
| Funding Details | funding details | Information about funding sources. |
| Funding Text 1 | funding text\_1 | Additional funding text. |
| Funding Sponsor | funder | Sponsoring funding organisations. |
| References | references | Cited references (often a count or partial list). |
| Correspondence Address | correspondence address.s | Address of the corresponding author. |
| Editors | book editors | Editors of the work (if applicable). |
| Publisher | publisher.s | Publisher of the work. |
| Conference name | conference title | Name of the conference. |
| Conference date | conference date | Date(s) of the conference. |
| Conference location | conference location | Location of the conference. |
| ISSN | issn.s | International Standard Serial Number. |
| ISBN | isbn.s | International Standard Book Number. |
| PubMed ID | pubmed id.s | PubMed identification number. |
| Language of Original Document | language.s | Original language of the publication. |
| Abbreviated Source Title | journal abbreviation | Abbreviated title of the source. |
| Document Type | document type.s | Type of document (e.g., Article, Review). |
| Open Access | open access.s | Open access status information. |
| Source | source | Indicates the database source (Scopus). |

Scopus Fields Ignored (Original Name): Affiliation country, Funding Text 2, Funding Acronym, Funding Number, Sponsors, Conference code, CODEN, Publication Stage, EID.

