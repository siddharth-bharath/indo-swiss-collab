#!/usr/bin/env Rscript

# Indo-Swiss Research Collaboration Database Creation (DuckDB version)
# - Uses existing OpenAlex topics hierarchy
# - Replaces 'publication' with 'work' in schema and logic
# - Uses inst_id (OpenAlex) and ror for institutions across all relationships
# - Adds work_institutions and work_topics from parquet mappings
# - Removes legacy publication_institutions
# - Converts primary keys to integer fields (strips letter prefixes)
# - Uses DuckDB for better analytical performance and parquet integration

# ===== 0. LIBS & PATHS =====

library(DBI)
library(duckdb)
library(data.table)
library(arrow)
library(jsonlite)
library(stringr)
library(lubridate)
library(dplyr)
library(tidyr)
library(dbplyr)

data_path <- "Data/"
db_path <- "indo_swiss_research.duckdb"
topics_db_path <- "openAlex_topics.sqlite"

# Helper function to strip letter prefix and convert to numeric (64-bit)
strip_id_prefix <- function(id_vector, prefix_letter) {
  # Remove the letter prefix and convert to numeric (64-bit)
  # Handle NA and empty values
  result <- rep(NA_real_, length(id_vector))
  valid_indices <- !is.na(id_vector) & id_vector != ""
  
  if (any(valid_indices)) {
	id_vector[valid_indices] = str_remove(id_vector[valid_indices], "https://openalex.org/")
    # Remove the prefix letter and convert to numeric
    numeric_part <- str_remove(id_vector[valid_indices], paste0("^", prefix_letter))
    converted_values <- as.numeric(numeric_part)
    
    # Check for overflow (NA values that weren't NA before conversion)
    original_valid <- id_vector[valid_indices]
    overflow_check <- is.na(converted_values) & !is.na(original_valid) & original_valid != ""
    
    if (any(overflow_check)) {
      overflow_examples <- original_valid[overflow_check][1:min(5, sum(overflow_check))]
      stop(paste("OVERFLOW DETECTED: The following", prefix_letter, "IDs could not be converted to numeric:",
                 paste(overflow_examples, collapse = ", "),
                 "\nThis indicates the numbers are too large for 64-bit storage."))
    }
    
    result[valid_indices] <- converted_values
  }
  
  return(result)
}

read_parquet_safe <- function(file_path) {
	tryCatch({
		arrow::read_parquet(file_path)
	}, error = function(e) {
		message(paste("Error reading", file_path, ":", e$message))
		return(NULL)
	})
}

# ===== 1. DB INIT =====

con <- dbConnect(duckdb::duckdb(), db_path)

create_table_safe <- function(con, table_name, create_statement) {
	tryCatch({
		dbExecute(con, paste("DROP TABLE IF EXISTS", table_name))
		dbExecute(con, create_statement)
		message(paste("Created table:", table_name))
	}, error = function(e) {
		message(paste("Error creating table", table_name, ":", e$message))
	})
}

message("Creating database schema...")

# ===== 2. SCHEMA =====

create_table_safe(con, "domains", "
CREATE TABLE domains (
	domain_id BIGINT PRIMARY KEY,
	display_name VARCHAR NOT NULL,
	description VARCHAR,
	works_count INTEGER DEFAULT 0,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)")

create_table_safe(con, "fields", "
CREATE TABLE fields (
	field_id BIGINT PRIMARY KEY,
	display_name VARCHAR NOT NULL,
	description VARCHAR,
	works_count INTEGER DEFAULT 0,
	domain_id BIGINT,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY (domain_id) REFERENCES domains(domain_id)
)")

create_table_safe(con, "subfields", "
CREATE TABLE subfields (
	subfield_id BIGINT PRIMARY KEY,
	display_name VARCHAR NOT NULL,
	description VARCHAR,
	works_count INTEGER DEFAULT 0,
	field_id BIGINT,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY (field_id) REFERENCES fields(field_id)
)")

create_table_safe(con, "topics", "
CREATE TABLE topics (
	topic_id BIGINT PRIMARY KEY,
	display_name VARCHAR NOT NULL,
	description VARCHAR,
	works_count INTEGER DEFAULT 0,
	subfield_id BIGINT,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY (subfield_id) REFERENCES subfields(subfield_id)
)")

create_table_safe(con, "works", "
CREATE TABLE works (
	work_id BIGINT PRIMARY KEY,
	doi VARCHAR,
	title VARCHAR,
	publication_date VARCHAR,
	publication_year INTEGER,
	document_type VARCHAR,
	cited_by_count INTEGER DEFAULT 0,
	is_oa INTEGER DEFAULT 0,
	source_display_name VARCHAR,
	abstract VARCHAR,
	language VARCHAR,
	volume VARCHAR,
	issue VARCHAR,
	first_page VARCHAR,
	last_page VARCHAR,
	pdf_url VARCHAR,
	landing_page_url VARCHAR,
	author_keywords VARCHAR,
	keywords VARCHAR,
	index_keywords_scopus VARCHAR,
	keywords_plus_wos VARCHAR,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)")

create_table_safe(con, "authors", "
CREATE TABLE authors (
	author_id BIGINT PRIMARY KEY,
	display_name VARCHAR NOT NULL,
	orcid VARCHAR,
	works_count INTEGER DEFAULT 0,
	cited_by_count INTEGER DEFAULT 0,
	h_index INTEGER,
	i10_index INTEGER,
	collab_status VARCHAR CHECK(collab_status IN ('Joint', 'Both', 'IN', 'CH', 'None')),
	total_institutions INTEGER DEFAULT 0,
	total_countries INTEGER DEFAULT 0,
	n_corresponding_works INTEGER DEFAULT 0,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)")

create_table_safe(con, "institutions", "
CREATE TABLE institutions (
	inst_id BIGINT PRIMARY KEY,
	ror VARCHAR,
	display_name VARCHAR NOT NULL,
	country_code VARCHAR,
	type VARCHAR,
	homepage_url VARCHAR,
	image_url VARCHAR,
	thumbnail_url VARCHAR,
	latitude DOUBLE,
	longitude DOUBLE,
	city VARCHAR,
	region VARCHAR,
	works_count INTEGER DEFAULT 0,
	cited_by_count INTEGER DEFAULT 0,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)")

create_table_safe(con, "work_authors", "
CREATE TABLE work_authors (
	work_id BIGINT,
	author_id BIGINT,
	author_position VARCHAR,
	is_corresponding INTEGER DEFAULT 0,
	raw_affiliation_string VARCHAR,
	PRIMARY KEY (work_id, author_id, author_position),
	FOREIGN KEY (work_id) REFERENCES works(work_id),
	FOREIGN KEY (author_id) REFERENCES authors(author_id)
)")

create_table_safe(con, "work_author_institutions", "
CREATE TABLE work_author_institutions (
	work_id BIGINT,
	author_id BIGINT,
	inst_id BIGINT,
	PRIMARY KEY (work_id, author_id, inst_id),
	FOREIGN KEY (work_id) REFERENCES works(work_id),
	FOREIGN KEY (author_id) REFERENCES authors(author_id),
	FOREIGN KEY (inst_id) REFERENCES institutions(inst_id)
)")

create_table_safe(con, "author_institutions", "
CREATE TABLE author_institutions (
	author_id BIGINT,
	inst_id BIGINT,
	n_works INTEGER DEFAULT 0,
	PRIMARY KEY (author_id, inst_id),
	FOREIGN KEY (author_id) REFERENCES authors(author_id),
	FOREIGN KEY (inst_id) REFERENCES institutions(inst_id)
)")

create_table_safe(con, "author_countries", "
CREATE TABLE author_countries (
	author_id BIGINT,
	country_code VARCHAR,
	n_works INTEGER DEFAULT 0,
	PRIMARY KEY (author_id, country_code),
	FOREIGN KEY (author_id) REFERENCES authors(author_id)
)")

create_table_safe(con, "work_topics", "
CREATE TABLE work_topics (
	work_id BIGINT,
	topic_id BIGINT,
	score DOUBLE,
	is_primary INTEGER DEFAULT 0,
	PRIMARY KEY (work_id, topic_id),
	FOREIGN KEY (work_id) REFERENCES works(work_id),
	FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
)")

create_table_safe(con, "work_institutions", "
CREATE TABLE work_institutions (
	work_id BIGINT,
	inst_id BIGINT,
	PRIMARY KEY (work_id, inst_id),
	FOREIGN KEY (work_id) REFERENCES works(work_id),
	FOREIGN KEY (inst_id) REFERENCES institutions(inst_id)
)")

create_table_safe(con, "funding", "
CREATE TABLE funding (
	funding_id BIGINT PRIMARY KEY,
	work_id BIGINT,
	funder_name VARCHAR,
	funder_id VARCHAR,
	award_id VARCHAR,
	funding_text VARCHAR,
	FOREIGN KEY (work_id) REFERENCES works(work_id)
)")

create_table_safe(con, "update_log", "
CREATE TABLE update_log (
	update_id BIGINT PRIMARY KEY,
	update_type VARCHAR,
	start_date TIMESTAMP,
	end_date TIMESTAMP,
	records_added INTEGER DEFAULT 0,
	update_source VARCHAR,
	notes VARCHAR
)")

# ===== 3. LOAD EXISTING OPENALEX TOPICS HIERARCHY =====

message("\nLoading existing OpenAlex topics hierarchy...")
topics_con <- dbConnect(RSQLite::SQLite(), topics_db_path)

# Load data and handle timestamp conversion issues
domains_data <- dbGetQuery(topics_con, "SELECT * FROM domains")
fields_data <- dbGetQuery(topics_con, "SELECT * FROM fields")
subfields_data <- dbGetQuery(topics_con, "SELECT * FROM subfields")
topics_data <- dbGetQuery(topics_con, "SELECT * FROM topics") %>% select(-cited_by_count)

dbDisconnect(topics_con)

# Remove problematic timestamp columns to avoid conversion issues
timestamp_cols <- c("created_date", "updated_date")
for (col in timestamp_cols) {
  if (col %in% names(domains_data)) {
    domains_data[[col]] <- NULL
  }
  if (col %in% names(fields_data)) {
    fields_data[[col]] <- NULL
  }
  if (col %in% names(subfields_data)) {
    subfields_data[[col]] <- NULL
  }
  if (col %in% names(topics_data)) {
    topics_data[[col]] <- NULL
  }
}

# Convert IDs to integer (strip letter prefixes)
domains_data$domain_id <- strip_id_prefix(domains_data$domain_id, "D")
fields_data$field_id <- strip_id_prefix(fields_data$field_id, "F")
fields_data$domain_id <- strip_id_prefix(fields_data$domain_id, "D")
subfields_data$subfield_id <- strip_id_prefix(subfields_data$subfield_id, "S")
subfields_data$field_id <- strip_id_prefix(subfields_data$field_id, "F")
topics_data$topic_id <- strip_id_prefix(topics_data$topic_id, "T")
topics_data$subfield_id <- strip_id_prefix(topics_data$subfield_id, "S")

dbWriteTable(con, "domains", domains_data, append = TRUE)
dbWriteTable(con, "fields", fields_data, append = TRUE)
dbWriteTable(con, "subfields", subfields_data, append = TRUE)
dbWriteTable(con, "topics", topics_data, append = TRUE)

message(paste("Loaded", nrow(domains_data), "domains,",
				nrow(fields_data), "fields,",
				nrow(subfields_data), "subfields,",
				nrow(topics_data), "topics"))

# ===== 4. LOAD WORKS =====

works_file <- file.path(data_path, "publications_full_dataset_2000-2024.parquet")
if (file.exists(works_file)) {
	works_dt <- as.data.table(read_parquet_safe(works_file))
	message(paste("Loaded", nrow(works_dt), "works"))

	# Convert work_id to integer (strip 'W' prefix)
	works_dt[, work_id := strip_id_prefix(work_id, "W")]

	works_insert <- works_dt[, .(
		work_id = work_id,
		doi = doi,
		title = title,
		publication_date = as.character(publication_date),
		publication_year = publication_year,
		document_type = `document type`,
		cited_by_count = as.integer(cited_by_count),
		is_oa = as.integer(is_oa == "true" | is_oa == TRUE),
		source_display_name = source_display_name,
		abstract = abstract,
		language = NA_character_,
		volume = NA_character_,
		issue = NA_character_,
		first_page = NA_character_,
		last_page = NA_character_,
		pdf_url = NA_character_,
		landing_page_url = NA_character_,
		author_keywords = if("author_keywords" %in% names(works_dt)) author_keywords else NA_character_,
		keywords = if("keywords" %in% names(works_dt)) keywords else NA_character_,
		index_keywords_scopus = if("index_keywords_scopus" %in% names(works_dt)) index_keywords_scopus else NA_character_,
		keywords_plus_wos = if("keywords_plus_wos" %in% names(works_dt)) keywords_plus_wos else NA_character_
	)]
	works_insert <- works_insert[!is.na(work_id)]
	dbWriteTable(con, "works", works_insert, append = TRUE)
	message(paste("Inserted", nrow(works_insert), "works"))
} else {
	message("Works file not found:", works_file)
}

# ===== 5. AUTHORS & WORK_AUTHORS =====

authors_flat_file <- file.path(data_path, "authors_processed_flat.parquet")
if (file.exists(authors_flat_file)) {
	authors_flat_dt <- as.data.table(read_parquet_safe(authors_flat_file))
	message(paste("Processing authors and work-author relationships from", nrow(authors_flat_dt), "records"))

	# Convert IDs to integer (strip letter prefixes)
	authors_flat_dt[, `:=`(
		work_id = strip_id_prefix(work_id, "W"),
		author_id = strip_id_prefix(author_id, "A")
	)]

	# Load both author files and merge them before inserting
	authors_summary_file <- file.path(data_path, "authors_summary_with_lists.parquet")
	if (file.exists(authors_summary_file)) {
		authors_summary_dt <- as.data.table(read_parquet_safe(authors_summary_file))
		message(paste("Loaded", nrow(authors_summary_dt), "authors from summary file"))
		
		# Convert author_id to integer
		authors_summary_dt[, author_id := strip_id_prefix(author_id, "A")]
		
		# Merge flat data with summary data to get complete author info
		if (!all(c("author_id", "display_name") %in% names(authors_flat_dt))) {
			if ("name" %in% names(authors_flat_dt)) authors_flat_dt[, display_name := name]
		}
		
		# Get minimal author data from flat file
		min_auth <- authors_flat_dt[!is.na(author_id), .(author_id, display_name)]
		min_auth <- min_auth[!duplicated(author_id)]
		
		# Merge with summary data to get collaboration fields
		complete_authors <- merge(
			min_auth,
			authors_summary_dt[, .(author_id, orcid, works_count = nWorks, collab_status, total_institutions, total_countries, n_corresponding_works)],
			by = "author_id", all.x = TRUE
		)
		
		# Fill missing values
		complete_authors[, `:=`(
			orcid = ifelse(is.na(orcid), NA_character_, orcid),
			works_count = ifelse(is.na(works_count), 0L, as.integer(works_count)),
			collab_status = ifelse(is.na(collab_status), NA_character_, collab_status),
			total_institutions = ifelse(is.na(total_institutions), 0L, as.integer(total_institutions)),
			total_countries = ifelse(is.na(total_countries), 0L, as.integer(total_countries)),
			n_corresponding_works = ifelse(is.na(n_corresponding_works), 0L, as.integer(n_corresponding_works))
		)]
		
		# Insert complete author data
		if (nrow(complete_authors) > 0) {
			dbWriteTable(con, "authors", complete_authors, append = TRUE)
			message(paste("Inserted", nrow(complete_authors), "complete authors with collaboration data"))
		}
	} else {
		# Fallback: insert minimal author data if summary file not available
		if (!all(c("author_id", "display_name") %in% names(authors_flat_dt))) {
			if ("name" %in% names(authors_flat_dt)) authors_flat_dt[, display_name := name]
		}
		min_auth <- authors_flat_dt[!is.na(author_id), .(author_id, display_name)]
		min_auth <- min_auth[!duplicated(author_id)]
		if (nrow(min_auth) > 0) {
			min_auth[, `:=`(orcid = NA_character_, works_count = 0L, collab_status = NA_character_, total_institutions = 0L, total_countries = 0L, n_corresponding_works = 0L)]
			dbWriteTable(con, "authors", min_auth, append = TRUE)
			message(paste("Inserted", nrow(min_auth), "minimal authors (summary file not found)"))
		}
	}

	# Process work_authors (same as before)
	# Keep author positions as text values (first, middle, last)
	work_authors <- authors_flat_dt[!is.na(work_id) & !is.na(author_id), .(
		work_id = work_id,
		author_id = author_id,
		author_position = as.character(author_position),
		is_corresponding = as.integer(is_corresponding == TRUE | is_corresponding == "true"),
		raw_affiliation_string = affiliation_raw
	)]
	# Drop rows missing author_position to satisfy composite PK NOT NULL
	work_authors <- work_authors[!is.na(author_position) & author_position != ""]
	# Dedupe by PK columns to avoid UNIQUE violations (keep first record)
	work_authors <- unique(work_authors, by = c("work_id", "author_id", "author_position"))
	existing_works <- dbGetQuery(con, "SELECT work_id FROM works")$work_id
	work_authors <- work_authors[work_id %in% existing_works]
    if (nrow(work_authors) > 0) {
        dbWriteTable(con, "work_authors", work_authors, append = TRUE)
        message(paste("Created", nrow(work_authors), "work-author relationships"))
    }
}

# ===== 6. INSTITUTIONS & LINKS =====

# 6a. Load work-institution links and populate institutions + work_institutions
wil_file <- file.path(data_path, "work_institution_links.parquet")
if (file.exists(wil_file)) {
	wil_dt <- as.data.table(read_parquet_safe(wil_file))
	message(paste("Loaded", nrow(wil_dt), "work-institution links"))

	# Convert IDs to integer (strip letter prefixes)
	wil_dt[, `:=`(
		work_id = strip_id_prefix(work_id, "W"),
		inst_id = strip_id_prefix(inst_id, "I")
	)]

    # Aggregate institution attributes per inst_id to avoid UNIQUE PK conflicts
    insts <- wil_dt[!is.na(inst_id),
        .(
            ror = { tmp <- ror[!is.na(ror) & ror != ""]; if (length(tmp)) tmp[1] else NA_character_ },
            display_name = { tmp <- institution_name[!is.na(institution_name) & institution_name != ""]; if (length(tmp)) tmp[1] else NA_character_ },
            country_code = { tmp <- country_code[!is.na(country_code) & country_code != ""]; if (length(tmp)) tmp[1] else NA_character_ }
        ),
        by = inst_id
    ]
    # Insert only missing inst_ids
    existing_inst <- tryCatch(dbGetQuery(con, "SELECT inst_id FROM institutions")$inst_id, error = function(e) numeric(0))
    insts <- insts[!inst_id %in% existing_inst]
    if (nrow(insts) > 0) {
        dbWriteTable(con, "institutions", insts, append = TRUE)
        message(paste("Inserted", nrow(insts), "institutions"))
    } else {
        message("No new institutions to insert")
    }

	work_insts <- unique(wil_dt[, .(work_id, inst_id)])
	existing_works <- dbGetQuery(con, "SELECT work_id FROM works")$work_id
	work_insts <- work_insts[work_id %in% existing_works]
    if (nrow(work_insts) > 0) {
        dbWriteTable(con, "work_institutions", work_insts, append = TRUE)
        message(paste("Created", nrow(work_insts), "work-institution relationships"))
    }
} else {
	message("Work-institution links parquet not found:", wil_file)
}

# 6b. Build author_institutions and author_countries from expanded affiliation parts
parts_dir <- file.path(data_path, "tmp_author_inst_expanded")
if (dir.exists(parts_dir)) {
	part_files <- list.files(parts_dir, pattern = "^part_.*\\.parquet$", full.names = TRUE)
	if (length(part_files) > 0) {
		expanded_dt <- data.table::rbindlist(lapply(part_files, read_parquet_safe), use.names = TRUE, fill = TRUE)
		# Convert IDs to integer (strip letter prefixes)
		expanded_dt[, `:=`(
			work_id = strip_id_prefix(work_id, "W"),
			author_id = strip_id_prefix(author_id, "A"),
			inst_id = strip_id_prefix(inst_id, "I"),
			country_code = as.character(country_code)
		)]
		expanded_dt <- expanded_dt[!is.na(inst_id) & !is.na(author_id)]

		# Ensure all referenced parents exist
		existing_works <- tryCatch(dbGetQuery(con, "SELECT work_id FROM works")$work_id, error = function(e) numeric(0))
		existing_authors <- tryCatch(dbGetQuery(con, "SELECT author_id FROM authors")$author_id, error = function(e) numeric(0))
		existing_insts <- tryCatch(dbGetQuery(con, "SELECT inst_id FROM institutions")$inst_id, error = function(e) numeric(0))

		# Filter to valid FK rows
		expanded_dt <- expanded_dt[
		  work_id %in% existing_works &
		  author_id %in% existing_authors &
		  inst_id %in% existing_insts
		]

		# Per-work author-institution links
		wai <- unique(expanded_dt[, .(work_id, author_id, inst_id)])
        if (nrow(wai) > 0) {
          dbWriteTable(con, "work_author_institutions", wai, append = TRUE)
          message(paste("Inserted", nrow(wai), "work-author-institution rows"))
        }

		# Aggregates
		auth_inst <- expanded_dt[, .(n_works = uniqueN(work_id)), by = .(author_id, inst_id)]
        if (nrow(auth_inst) > 0) {
          dbWriteTable(con, "author_institutions", auth_inst, append = TRUE)
          message(paste("Inserted", nrow(auth_inst), "author-institution rows"))
        }

		auth_ctry <- expanded_dt[!is.na(country_code) & country_code != "", .(n_works = uniqueN(work_id)), by = .(author_id, country_code)]
		# Ensure authors exist for author_countries
		auth_ctry <- auth_ctry[author_id %in% existing_authors]
        if (nrow(auth_ctry) > 0) {
          dbWriteTable(con, "author_countries", auth_ctry, append = TRUE)
          message(paste("Inserted", nrow(auth_ctry), "author-country rows"))
        }
	}
}

# ===== 7. WORK-TOPIC LINKS =====

wtl_file <- file.path(data_path, "work_topic_links.parquet")
if (file.exists(wtl_file)) {
	wtl_dt <- as.data.table(read_parquet_safe(wtl_file))
	message(paste("Loaded", nrow(wtl_dt), "work-topic links"))

	# Convert IDs to integer (strip letter prefixes)
	wtl_dt[, `:=`(
		work_id = strip_id_prefix(work_id, "W"),
		topic_id = strip_id_prefix(topic_id, "T")
	)]
	wtl_dt <- wtl_dt[, .(work_id, topic_id, score = as.numeric(topic_score))]
	wtl_dt[, is_primary := 0L]
	existing_works <- dbGetQuery(con, "SELECT work_id FROM works")$work_id
	wtl_dt <- wtl_dt[work_id %in% existing_works]
	if (nrow(wtl_dt) > 0) {
		dbWriteTable(con, "work_topics", wtl_dt, append = TRUE)
		message(paste("Inserted", nrow(wtl_dt), "work-topic rows"))
	}
} else {
	message("Work-topic links parquet not found:", wtl_file)
}

# ===== 8. INDEXES =====

message("\nCreating indexes for performance...")
index_statements <- c(
	"CREATE INDEX idx_work_year ON works(publication_year)",
	"CREATE INDEX idx_work_doi ON works(doi)",
	"CREATE INDEX idx_work_cited ON works(cited_by_count)",
	"CREATE INDEX idx_work_author_keywords ON works(author_keywords)",
	"CREATE INDEX idx_work_keywords ON works(keywords)",
	"CREATE INDEX idx_work_index_keywords_scopus ON works(index_keywords_scopus)",
	"CREATE INDEX idx_work_keywords_plus_wos ON works(keywords_plus_wos)",
	"CREATE INDEX idx_author_name ON authors(display_name)",
	"CREATE INDEX idx_author_collab ON authors(collab_status)",
	"CREATE INDEX idx_ai_author ON author_institutions(author_id)",
	"CREATE INDEX idx_ai_inst ON author_institutions(inst_id)",
	"CREATE INDEX idx_ac_author ON author_countries(author_id)",
	"CREATE INDEX idx_ac_country ON author_countries(country_code)",
	"CREATE INDEX idx_inst_country ON institutions(country_code)",
	"CREATE INDEX idx_inst_name ON institutions(display_name)",
	"CREATE INDEX idx_inst_ror ON institutions(ror)",
	"CREATE INDEX idx_wa_work ON work_authors(work_id)",
	"CREATE INDEX idx_wa_author ON work_authors(author_id)",
	"CREATE INDEX idx_wai_work ON work_author_institutions(work_id)",
	"CREATE INDEX idx_wai_author ON work_author_institutions(author_id)",
	"CREATE INDEX idx_wai_inst ON work_author_institutions(inst_id)",
	"CREATE INDEX idx_wi_work ON work_institutions(work_id)",
	"CREATE INDEX idx_wi_inst ON work_institutions(inst_id)",
	"CREATE INDEX idx_wt_work ON work_topics(work_id)",
	"CREATE INDEX idx_wt_topic ON work_topics(topic_id)"
)
for (idx_stmt in index_statements) {
	tryCatch({ dbExecute(con, idx_stmt) }, error = function(e) { message(paste("Index might already exist:", e$message)) })
}

# ===== 9. VIEWS =====

message("\nCreating analytical views...")
dbExecute(con, "DROP VIEW IF EXISTS indo_swiss_works")
dbExecute(con, "
CREATE VIEW indo_swiss_works AS
SELECT DISTINCT w.*
FROM works w
JOIN work_institutions wi ON w.work_id = wi.work_id
JOIN institutions i ON wi.inst_id = i.inst_id
WHERE EXISTS (
	SELECT 1 FROM work_institutions wi2
	JOIN institutions i2 ON wi2.inst_id = i2.inst_id
	WHERE wi2.work_id = w.work_id AND i2.country_code = 'IN'
)
AND EXISTS (
	SELECT 1 FROM work_institutions wi3
	JOIN institutions i3 ON wi3.inst_id = i3.inst_id
	WHERE wi3.work_id = w.work_id AND i3.country_code = 'CH'
)
")

dbExecute(con, "DROP VIEW IF EXISTS topic_hierarchy")
dbExecute(con, "
CREATE VIEW topic_hierarchy AS
SELECT 
	t.topic_id,
	t.display_name as topic_name,
	t.works_count as topic_works_count,
	s.subfield_id,
	s.display_name as subfield_name,
	s.works_count as subfield_works_count,
	f.field_id,
	f.display_name as field_name,
	f.works_count as field_works_count,
	d.domain_id,
	d.display_name as domain_name,
	d.works_count as domain_works_count
FROM topics t
JOIN subfields s ON t.subfield_id = s.subfield_id
JOIN fields f ON s.field_id = f.field_id
JOIN domains d ON f.domain_id = d.domain_id
")

dbExecute(con, "DROP VIEW IF EXISTS work_with_topics")
dbExecute(con, "
CREATE VIEW work_with_topics AS
SELECT w.work_id, w.title, wt.topic_id, t.display_name AS topic_name, wt.score
FROM works w
JOIN work_topics wt ON w.work_id = wt.work_id
JOIN topics t ON wt.topic_id = t.topic_id
")

# ===== 10. LOG & SUMMARY =====

update_log <- data.table(
	update_id = 1L,
	update_type = "initial_load",
	start_date = Sys.time(),
	end_date = Sys.time(),
	records_added = dbGetQuery(con, "SELECT COUNT(*) as n FROM works")$n,
	update_source = "parquet_files_and_openalex_topics",
	notes = "Initial database creation using DuckDB with integer primary keys (stripped letter prefixes) and OpenAlex topics hierarchy"
)
dbWriteTable(con, "update_log", update_log, append = TRUE)

message("\n=== DATABASE CREATION SUMMARY ===")

#Check that the db connection is open
if (!dbIsValid(con)) {
	stop("Database connection is not open")
}

#Open the db connection
con <- dbConnect(duckdb::duckdb(), db_path)

# Get and print table counts
works_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM works")$cnt
message(paste("Works:", works_count))

authors_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM authors")$cnt
message(paste("Authors:", authors_count))

institutions_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM institutions")$cnt
message(paste("Institutions:", institutions_count))

work_authors_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM work_authors")$cnt
message(paste("Work-Authors:", work_authors_count))

work_institutions_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM work_institutions")$cnt
message(paste("Work-Institutions:", work_institutions_count))

work_topics_count <- dbGetQuery(con, "SELECT COUNT(*) as cnt FROM work_topics")$cnt
message(paste("Work-Topics:", work_topics_count))

{# Authors per work
dbGetQuery(con, "SELECT AVG(author_count) as avg_authors, MAX(author_count) as max_authors FROM (SELECT work_id, COUNT(*) as author_count FROM work_authors GROUP BY work_id)")

# Institutions per work
dbGetQuery(con, "SELECT AVG(inst_count) as avg_institutions, MAX(inst_count) as max_institutions FROM (SELECT work_id, COUNT(*) as inst_count FROM work_institutions GROUP BY work_id)")

# Works per author
dbGetQuery(con, "SELECT AVG(works_count) as avg_works_per_author, MAX(works_count) as max_works FROM authors")

# Topics per work
dbGetQuery(con, "SELECT AVG(topic_count) as avg_topics, MAX(topic_count) as max_topics FROM (SELECT work_id, COUNT(*) as topic_count FROM work_topics GROUP BY work_id)")
}

# Abstract coverage
dbGetQuery(con, "SELECT COUNT(*) as with_abstract, COUNT(*)*100.0/(SELECT COUNT(*) FROM works) as pct FROM works WHERE abstract IS NOT NULL")

# DOI coverage
dbGetQuery(con, "SELECT COUNT(*) as with_doi, COUNT(*)*100.0/(SELECT COUNT(*) FROM works) as pct FROM works WHERE doi IS NOT NULL")

# ORCID coverage
dbGetQuery(con, "SELECT COUNT(*) as with_orcid, COUNT(*)*100.0/(SELECT COUNT(*) FROM authors) as pct FROM authors WHERE orcid IS NOT NULL")

# Collaboration status distribution
dbGetQuery(con, "SELECT collab_status, COUNT(*) as n_authors, COUNT(*)*100.0/(SELECT COUNT(*) FROM authors) as pct FROM authors GROUP BY collab_status")

# Topic hierarchy counts (already in script)
dbGetQuery(con, "SELECT COUNT(*) FROM domains")
dbGetQuery(con, "SELECT COUNT(*) FROM fields") 
dbGetQuery(con, "SELECT COUNT(*) FROM subfields")
dbGetQuery(con, "SELECT COUNT(*) FROM topics")

# Top research domains for Indo-Swiss collaborations
dbGetQuery(con, "
SELECT d.display_name, COUNT(DISTINCT w.work_id) as n_works
FROM indo_swiss_works w
JOIN work_topics wt ON w.work_id = wt.work_id
JOIN topics t ON wt.topic_id = t.topic_id
JOIN subfields s ON t.subfield_id = s.subfield_id
JOIN fields f ON s.field_id = f.field_id
JOIN domains d ON f.domain_id = d.domain_id
GROUP BY d.display_name
ORDER BY n_works DESC
LIMIT 5
")

dbDisconnect(con)


# Using R's built-in compression (works everywhere)
compress_with_r <- function(db_path) {
  output_path <- paste0(db_path, ".gz")
  
  # Read in chunks to handle large files
  con_in <- file(db_path, "rb")
  con_out <- gzfile(output_path, "wb", compression = 9)
  
  repeat {
    chunk <- readBin(con_in, "raw", 1024^2)  # 1MB chunks
    if (length(chunk) == 0) break
    writeBin(chunk, con_out)
  }
  
  close(con_in)
  close(con_out)
  
  cat("Compressed to:", output_path, "\n")
}

# Usage
compress_with_r(db_path)	
