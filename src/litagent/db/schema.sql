-- Literature agent schema (new_design.md section 16).
--
-- SQLite, applied once by `db.connection.get_connection()` if the `papers`
-- table doesn't already exist. Deliberately plain SQL, no ORM/migration
-- framework -- the whole database is a single committed file on the `state`
-- branch, so "the schema" and "the file's current shape" are the same thing.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS research_directions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config TEXT NOT NULL,              -- full ResearchDirection, JSON-encoded
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT NOT NULL DEFAULT '[]', -- JSON list[str], display order preserved
    publication_date TEXT,
    venue TEXT,
    doi TEXT UNIQUE,
    arxiv_id TEXT UNIQUE,
    semantic_scholar_id TEXT UNIQUE,
    openalex_id TEXT UNIQUE,
    url TEXT,
    pdf_url TEXT,
    source TEXT NOT NULL,
    citation_count INTEGER,
    content_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_papers_content_hash ON papers (content_hash);
CREATE INDEX IF NOT EXISTS ix_papers_publication_date ON papers (publication_date);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES authors (id) ON DELETE CASCADE,
    author_order INTEGER NOT NULL,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_institutions (
    paper_id TEXT NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    institution_id INTEGER NOT NULL REFERENCES institutions (id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, institution_id)
);

-- One row per (paper, direction) the relevance funnel has ever judged --
-- rejections included, so "why was paper X rejected" (section 33) is a
-- query, not a log grep. `analysed`/`analysis` are populated only for
-- papers that survived the funnel and went through detailed analysis.
CREATE TABLE IF NOT EXISTS paper_directions (
    paper_id TEXT NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    direction_id TEXT NOT NULL REFERENCES research_directions (id) ON DELETE CASCADE,
    relevance_score REAL,
    relevance_category TEXT NOT NULL,   -- core | interesting | peripheral | irrelevant
    reason TEXT,
    subtopics TEXT NOT NULL DEFAULT '[]', -- JSON list[str]
    stage_reached TEXT NOT NULL,        -- metadata | lexical | embedding | llm
    analysed INTEGER NOT NULL DEFAULT 0,
    analysis TEXT,                      -- PaperAnalysis, JSON-encoded
    digested_at TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (paper_id, direction_id)
);

-- Section 6: the one-time landscape discovery result per direction, kept
-- separate from paper_directions since it's a distinct workflow (not tied
-- to a daily run) that the user reviews/corrects directly.
CREATE TABLE IF NOT EXISTS landscape_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction_id TEXT NOT NULL REFERENCES research_directions (id) ON DELETE CASCADE,
    category TEXT NOT NULL,             -- foundations | major_approaches | recent_work | adjacent
    paper_id TEXT NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    signal_summary TEXT,
    delivered_at TEXT,                  -- set once shown in a daily digest (never for a fresh DB)
    created_at TEXT NOT NULL,
    UNIQUE (direction_id, category, paper_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    direction_id TEXT REFERENCES research_directions (id) ON DELETE SET NULL,
    feedback_type TEXT NOT NULL,        -- relevant | not_relevant | more_like_this | save
    feedback_text TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,               -- running | success | partial_failure | failure
    direction_ids TEXT NOT NULL DEFAULT '[]',
    providers_queried TEXT NOT NULL DEFAULT '[]',
    papers_discovered INTEGER NOT NULL DEFAULT 0,
    papers_deduplicated INTEGER NOT NULL DEFAULT 0,
    papers_rejected INTEGER NOT NULL DEFAULT 0,
    papers_analysed INTEGER NOT NULL DEFAULT 0,
    papers_surfaced INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    slack_status TEXT,
    error TEXT
);
