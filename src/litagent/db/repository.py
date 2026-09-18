"""Plain-function repository over the SQLite schema.

No repository base class (matches the old codebase's stated convention) --
just functions that take a `sqlite3.Connection` and Pydantic models in
`db/models.py`. Callers own transaction boundaries (`conn.commit()`).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import UTC, datetime

from litagent.db.models import (
    Feedback,
    LandscapeCategory,
    LandscapeEntry,
    Paper,
    PaperAnalysis,
    PaperDirectionMatch,
    RelevanceCategory,
    ResearchDirection,
    Run,
)
from litagent.discovery.base import DiscoveredPaper

# Section 10: title-similarity dedup is the last-resort tier, only reached
# when neither party has a DOI/arXiv ID and the normalized titles differ --
# e.g. a title with a typo fixed between preprint versions. High threshold
# because a false-positive merge silently drops a distinct paper.
_TITLE_SIMILARITY_THRESHOLD = 0.93

_NON_TITLE_CHARS_RE = re.compile(r"[^a-z0-9 ]")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --- Papers ------------------------------------------------------------


def normalize_title(title: str) -> str:
    decomposed = unicodedata.normalize("NFKD", title)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = _NON_TITLE_CHARS_RE.sub(" ", stripped.lower())
    return " ".join(cleaned.split())


def _title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def _content_hash(normalized_title: str, doi: str | None, arxiv_id: str | None) -> str:
    basis = doi or arxiv_id or normalized_title
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _row_to_paper(row: sqlite3.Row) -> Paper:
    return Paper(
        id=row["id"],
        title=row["title"],
        abstract=row["abstract"],
        authors=json.loads(row["authors"]),
        publication_date=_parse_dt(row["publication_date"]),
        venue=row["venue"],
        doi=row["doi"],
        arxiv_id=row["arxiv_id"],
        semantic_scholar_id=row["semantic_scholar_id"],
        openalex_id=row["openalex_id"],
        url=row["url"],
        pdf_url=row["pdf_url"],
        source=row["source"],
        citation_count=row["citation_count"],
        content_hash=row["content_hash"],
        first_seen_at=_parse_dt(row["first_seen_at"]),
        last_updated_at=_parse_dt(row["last_updated_at"]),
    )


def get_paper(conn: sqlite3.Connection, paper_id: str) -> Paper | None:
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _row_to_paper(row) if row else None


def find_existing_paper(conn: sqlite3.Connection, discovered: DiscoveredPaper) -> Paper | None:
    """Section 10's dedup order: DOI -> arXiv ID -> normalized title -> title+author similarity."""
    if discovered.doi:
        row = conn.execute("SELECT * FROM papers WHERE doi = ?", (discovered.doi,)).fetchone()
        if row:
            return _row_to_paper(row)
    if discovered.arxiv_id:
        row = conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", (discovered.arxiv_id,)
        ).fetchone()
        if row:
            return _row_to_paper(row)
    if discovered.semantic_scholar_id:
        row = conn.execute(
            "SELECT * FROM papers WHERE semantic_scholar_id = ?",
            (discovered.semantic_scholar_id,),
        ).fetchone()
        if row:
            return _row_to_paper(row)
    if discovered.openalex_id:
        row = conn.execute(
            "SELECT * FROM papers WHERE openalex_id = ?", (discovered.openalex_id,)
        ).fetchone()
        if row:
            return _row_to_paper(row)

    normalized = normalize_title(discovered.title)
    candidate: Paper | None = None
    best_score = 0.0
    for row in conn.execute("SELECT * FROM papers").fetchall():
        existing_title = row["title"]
        if normalize_title(existing_title) == normalized:
            return _row_to_paper(row)
        score = _title_similarity(existing_title, discovered.title)
        if score > best_score:
            best_score, candidate = score, _row_to_paper(row)
    if candidate is not None and best_score >= _TITLE_SIMILARITY_THRESHOLD:
        return candidate
    return None


def upsert_paper(conn: sqlite3.Connection, discovered: DiscoveredPaper) -> tuple[Paper, bool]:
    """Store `discovered`, deduplicating against existing rows. Returns `(paper, created)`."""
    existing = find_existing_paper(conn, discovered)
    now = now_iso()
    if existing is not None:
        # A paper found again through another provider may fill in an
        # identifier or citation count the first sighting didn't have --
        # merge rather than ignore, but never overwrite a populated field
        # with an empty one.
        merged = {
            "doi": existing.doi or discovered.doi,
            "arxiv_id": existing.arxiv_id or discovered.arxiv_id,
            "semantic_scholar_id": existing.semantic_scholar_id or discovered.semantic_scholar_id,
            "openalex_id": existing.openalex_id or discovered.openalex_id,
            "citation_count": (
                discovered.citation_count
                if discovered.citation_count is not None
                else existing.citation_count
            ),
            "abstract": existing.abstract or discovered.abstract,
            "pdf_url": existing.pdf_url or discovered.pdf_url,
        }
        conn.execute(
            """UPDATE papers SET doi = ?, arxiv_id = ?, semantic_scholar_id = ?,
                   openalex_id = ?, citation_count = ?, abstract = ?, pdf_url = ?,
                   last_updated_at = ? WHERE id = ?""",
            (*merged.values(), now, existing.id),
        )
        return get_paper(conn, existing.id), False  # type: ignore[return-value]

    paper_id = uuid.uuid4().hex
    normalized = normalize_title(discovered.title)
    conn.execute(
        """INSERT INTO papers (
               id, title, abstract, authors, publication_date, venue, doi,
               arxiv_id, semantic_scholar_id, openalex_id, url, pdf_url,
               source, citation_count, content_hash, first_seen_at, last_updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            paper_id,
            discovered.title,
            discovered.abstract,
            json.dumps(discovered.authors),
            discovered.published_at.isoformat() if discovered.published_at else None,
            None,
            discovered.doi,
            discovered.arxiv_id,
            discovered.semantic_scholar_id,
            discovered.openalex_id,
            discovered.paper_url,
            discovered.pdf_url,
            discovered.source,
            discovered.citation_count,
            _content_hash(normalized, discovered.doi, discovered.arxiv_id),
            now,
            now,
        ),
    )
    return get_paper(conn, paper_id), True  # type: ignore[return-value]


# --- Authors / institutions (section 15) ------------------------------------


def _normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z ]", " ", stripped.lower()).split())


def _upsert_named(conn: sqlite3.Connection, table: str, name: str) -> int:
    normalized = _normalize_name(name)
    row = conn.execute(
        f"SELECT id FROM {table} WHERE normalized_name = ?", (normalized,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        f"INSERT INTO {table} (name, normalized_name) VALUES (?, ?)",
        (name, normalized),
    )
    return cursor.lastrowid


def link_authors_and_institutions(
    conn: sqlite3.Connection, paper_id: str, authors: list[str], institutions: list[str]
) -> None:
    """Attach author/institution rows to a paper.

    Incomplete metadata never blocks storage (section 15): an empty
    `institutions` list just links no institutions.
    """
    for order, author_name in enumerate(authors):
        author_id = _upsert_named(conn, "authors", author_name)
        conn.execute(
            """INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order)
               VALUES (?, ?, ?)""",
            (paper_id, author_id, order),
        )
    for institution_name in institutions:
        institution_id = _upsert_named(conn, "institutions", institution_name)
        conn.execute(
            "INSERT OR IGNORE INTO paper_institutions (paper_id, institution_id) VALUES (?, ?)",
            (paper_id, institution_id),
        )


def institutions_for_paper(conn: sqlite3.Connection, paper_id: str) -> list[str]:
    rows = conn.execute(
        """SELECT i.name FROM institutions i
           JOIN paper_institutions pi ON pi.institution_id = i.id
           WHERE pi.paper_id = ?""",
        (paper_id,),
    ).fetchall()
    return [row["name"] for row in rows]


# --- Research directions -----------------------------------------------


def upsert_research_direction(conn: sqlite3.Connection, direction: ResearchDirection) -> None:
    now = now_iso()
    existing = conn.execute(
        "SELECT created_at FROM research_directions WHERE id = ?", (direction.id,)
    ).fetchone()
    created_at = existing["created_at"] if existing else now
    conn.execute(
        """INSERT INTO research_directions (id, name, config, created_at, updated_at, active)
           VALUES (?, ?, ?, ?, ?, 1)
           ON CONFLICT(id) DO UPDATE SET
               name = excluded.name, config = excluded.config, updated_at = excluded.updated_at""",
        (direction.id, direction.name, direction.model_dump_json(), created_at, now),
    )


def active_direction_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT id FROM research_directions WHERE active = 1").fetchall()
    return [row["id"] for row in rows]


# --- Paper <-> direction relevance (section 12, 33) -------------------------


def _row_to_match(row: sqlite3.Row) -> PaperDirectionMatch:
    return PaperDirectionMatch(
        paper_id=row["paper_id"],
        direction_id=row["direction_id"],
        relevance_score=row["relevance_score"],
        relevance_category=RelevanceCategory(row["relevance_category"]),
        reason=row["reason"],
        subtopics=json.loads(row["subtopics"]),
        stage_reached=row["stage_reached"],
        analysed=bool(row["analysed"]),
        analysis=PaperAnalysis.model_validate_json(row["analysis"]) if row["analysis"] else None,
        digested_at=_parse_dt(row["digested_at"]),
        created_at=_parse_dt(row["created_at"]),
    )


def store_paper_direction_match(conn: sqlite3.Connection, match: PaperDirectionMatch) -> None:
    conn.execute(
        """INSERT INTO paper_directions (
               paper_id, direction_id, relevance_score, relevance_category, reason,
               subtopics, stage_reached, analysed, analysis, digested_at, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(paper_id, direction_id) DO UPDATE SET
               relevance_score = excluded.relevance_score,
               relevance_category = excluded.relevance_category,
               reason = excluded.reason,
               subtopics = excluded.subtopics,
               stage_reached = excluded.stage_reached,
               analysed = excluded.analysed,
               analysis = excluded.analysis""",
        (
            match.paper_id,
            match.direction_id,
            match.relevance_score,
            match.relevance_category.value,
            match.reason,
            json.dumps(match.subtopics),
            match.stage_reached.value
            if hasattr(match.stage_reached, "value")
            else match.stage_reached,
            int(match.analysed),
            match.analysis.model_dump_json() if match.analysis else None,
            match.digested_at.isoformat() if match.digested_at else None,
            match.created_at.isoformat(),
        ),
    )


def get_paper_direction_match(
    conn: sqlite3.Connection, paper_id: str, direction_id: str
) -> PaperDirectionMatch | None:
    row = conn.execute(
        "SELECT * FROM paper_directions WHERE paper_id = ? AND direction_id = ?",
        (paper_id, direction_id),
    ).fetchone()
    return _row_to_match(row) if row else None


def mark_digested(conn: sqlite3.Connection, paper_id: str, direction_id: str) -> None:
    conn.execute(
        "UPDATE paper_directions SET digested_at = ? WHERE paper_id = ? AND direction_id = ?",
        (now_iso(), paper_id, direction_id),
    )


def undigested_matches(
    conn: sqlite3.Connection, direction_id: str, categories: tuple[str, ...]
) -> list[tuple[Paper, PaperDirectionMatch]]:
    placeholders = ",".join("?" for _ in categories)
    rows = conn.execute(
        f"""SELECT * FROM paper_directions
            WHERE direction_id = ? AND digested_at IS NULL
              AND relevance_category IN ({placeholders})
            ORDER BY relevance_score DESC""",
        (direction_id, *categories),
    ).fetchall()
    results = []
    for row in rows:
        paper = get_paper(conn, row["paper_id"])
        if paper is not None:
            results.append((paper, _row_to_match(row)))
    return results


# --- Landscape (section 6) --------------------------------------------------

# Fixed delivery order, independent of SQL's default text ordering of the
# category values (which would put "adjacent" first alphabetically).
_LANDSCAPE_CATEGORY_ORDER = {category: index for index, category in enumerate(LandscapeCategory)}


def _row_to_landscape_entry(row: sqlite3.Row) -> LandscapeEntry:
    return LandscapeEntry(
        id=row["id"],
        direction_id=row["direction_id"],
        category=LandscapeCategory(row["category"]),
        paper_id=row["paper_id"],
        rank=row["rank"],
        signal_summary=row["signal_summary"],
        delivered_at=_parse_dt(row["delivered_at"]),
        created_at=_parse_dt(row["created_at"]),
    )


def replace_landscape(
    conn: sqlite3.Connection, direction_id: str, entries: list[LandscapeEntry]
) -> None:
    conn.execute("DELETE FROM landscape_entries WHERE direction_id = ?", (direction_id,))
    for entry in entries:
        conn.execute(
            """INSERT INTO landscape_entries
                   (direction_id, category, paper_id, rank, signal_summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry.direction_id,
                entry.category.value,
                entry.paper_id,
                entry.rank,
                entry.signal_summary,
                entry.created_at.isoformat(),
            ),
        )


def get_landscape(conn: sqlite3.Connection, direction_id: str) -> dict[str, list[Paper]]:
    rows = conn.execute(
        """SELECT * FROM landscape_entries WHERE direction_id = ?
           ORDER BY category, rank""",
        (direction_id,),
    ).fetchall()
    by_category: dict[str, list[Paper]] = {}
    for row in rows:
        paper = get_paper(conn, row["paper_id"])
        if paper is not None:
            by_category.setdefault(row["category"], []).append(paper)
    return by_category


def undelivered_landscape_entries(
    conn: sqlite3.Connection, direction_id: str
) -> list[tuple[Paper, LandscapeEntry]]:
    """Landscape entries never yet shown in a digest, in delivery order
    (foundations -> major_approaches -> recent_work -> adjacent, then rank)."""
    rows = conn.execute(
        "SELECT * FROM landscape_entries WHERE direction_id = ? AND delivered_at IS NULL",
        (direction_id,),
    ).fetchall()
    entries = [_row_to_landscape_entry(row) for row in rows]
    entries.sort(key=lambda e: (_LANDSCAPE_CATEGORY_ORDER[e.category], e.rank))

    results = []
    for entry in entries:
        paper = get_paper(conn, entry.paper_id)
        if paper is not None:
            results.append((paper, entry))
    return results


def mark_landscape_delivered(conn: sqlite3.Connection, entry_ids: list[int]) -> None:
    if not entry_ids:
        return
    placeholders = ",".join("?" for _ in entry_ids)
    conn.execute(
        f"UPDATE landscape_entries SET delivered_at = ? WHERE id IN ({placeholders})",
        (now_iso(), *entry_ids),
    )


# --- Feedback (section 34) --------------------------------------------------


def record_feedback(conn: sqlite3.Connection, feedback: Feedback) -> Feedback:
    cursor = conn.execute(
        """INSERT INTO feedback (paper_id, direction_id, feedback_type, feedback_text, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            feedback.paper_id,
            feedback.direction_id,
            feedback.feedback_type.value,
            feedback.feedback_text,
            feedback.created_at.isoformat(),
        ),
    )
    return feedback.model_copy(update={"id": cursor.lastrowid})


# --- Runs (section 30) -------------------------------------------------


def create_run(conn: sqlite3.Connection, run: Run) -> None:
    conn.execute(
        """INSERT INTO runs (id, started_at, status, direction_ids, providers_queried)
           VALUES (?, ?, ?, ?, ?)""",
        (
            run.id,
            run.started_at.isoformat(),
            run.status.value,
            json.dumps(run.direction_ids),
            json.dumps(run.providers_queried),
        ),
    )


def finish_run(conn: sqlite3.Connection, run: Run) -> None:
    conn.execute(
        """UPDATE runs SET completed_at = ?, status = ?, papers_discovered = ?,
               papers_deduplicated = ?, papers_rejected = ?, papers_analysed = ?,
               papers_surfaced = ?, llm_calls = ?, slack_status = ?, error = ?
           WHERE id = ?""",
        (
            run.completed_at.isoformat() if run.completed_at else None,
            run.status.value,
            run.papers_discovered,
            run.papers_deduplicated,
            run.papers_rejected,
            run.papers_analysed,
            run.papers_surfaced,
            run.llm_calls,
            run.slack_status,
            run.error,
            run.id,
        ),
    )
