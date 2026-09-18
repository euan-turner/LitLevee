"""Unit tests for the SQLite repository layer (section 31: no external
service needed -- just a tmp_path database file)."""

from __future__ import annotations

from datetime import UTC, datetime

from litagent.db.connection import _ensure_column, get_connection
from litagent.db.models import (
    Feedback,
    FeedbackType,
    LandscapeCategory,
    LandscapeEntry,
)
from litagent.db.repository import (
    institutions_for_paper,
    link_authors_and_institutions,
    mark_landscape_delivered,
    normalize_title,
    record_feedback,
    replace_landscape,
    undelivered_landscape_entries,
    upsert_paper,
)
from litagent.discovery.base import DiscoveredPaper


def _conn(tmp_path):
    return get_connection(tmp_path / "test.db")


def test_normalize_title_strips_punctuation_and_case() -> None:
    assert normalize_title("DistServe: Disaggregating Prefill & Decoding!") == (
        "distserve disaggregating prefill decoding"
    )


def test_upsert_paper_creates_new_row(tmp_path) -> None:
    conn = _conn(tmp_path)
    paper, created = upsert_paper(
        conn, DiscoveredPaper(title="DistServe", arxiv_id="2401.09670", source="arxiv")
    )
    assert created is True
    assert paper.arxiv_id == "2401.09670"


def test_upsert_paper_dedupes_by_arxiv_id(tmp_path) -> None:
    conn = _conn(tmp_path)
    first, _ = upsert_paper(
        conn, DiscoveredPaper(title="DistServe", arxiv_id="2401.09670", source="arxiv")
    )
    second, created = upsert_paper(
        conn,
        DiscoveredPaper(
            title="DistServe (v2)", arxiv_id="2401.09670", source="openalex", citation_count=5
        ),
    )
    assert created is False
    assert second.id == first.id
    assert second.citation_count == 5  # merged in from the second sighting


def test_upsert_paper_dedupes_by_doi(tmp_path) -> None:
    conn = _conn(tmp_path)
    first, _ = upsert_paper(conn, DiscoveredPaper(title="Splitwise", doi="10.1/x", source="openalex"))
    second, created = upsert_paper(
        conn, DiscoveredPaper(title="Splitwise", doi="10.1/x", source="arxiv")
    )
    assert created is False
    assert second.id == first.id


def test_upsert_paper_dedupes_by_normalized_title(tmp_path) -> None:
    conn = _conn(tmp_path)
    first, _ = upsert_paper(conn, DiscoveredPaper(title="ThunderServe!", source="openalex"))
    second, created = upsert_paper(conn, DiscoveredPaper(title="ThunderServe", source="arxiv"))
    assert created is False
    assert second.id == first.id


def test_upsert_paper_dedupes_by_title_similarity(tmp_path) -> None:
    conn = _conn(tmp_path)
    first, _ = upsert_paper(
        conn,
        DiscoveredPaper(
            title="CoCoScale: Leveraging Layer-wise Scaling for Online LLM Serving", source="openalex"
        ),
    )
    second, created = upsert_paper(
        conn,
        DiscoveredPaper(
            title="CoCoScale: Leveraging Layerwise Scaling for Online LLM Serving", source="arxiv"
        ),
    )
    assert created is False
    assert second.id == first.id


def test_upsert_paper_keeps_distinct_papers_separate(tmp_path) -> None:
    conn = _conn(tmp_path)
    first, _ = upsert_paper(conn, DiscoveredPaper(title="DistServe", source="arxiv"))
    second, created = upsert_paper(conn, DiscoveredPaper(title="Splitwise", source="arxiv"))
    assert created is True
    assert second.id != first.id


def test_link_authors_and_institutions(tmp_path) -> None:
    conn = _conn(tmp_path)
    paper, _ = upsert_paper(conn, DiscoveredPaper(title="DistServe", source="arxiv"))
    link_authors_and_institutions(conn, paper.id, ["Alice Smith"], ["UC Berkeley"])
    assert institutions_for_paper(conn, paper.id) == ["UC Berkeley"]


def test_record_feedback(tmp_path) -> None:
    conn = _conn(tmp_path)
    paper, _ = upsert_paper(conn, DiscoveredPaper(title="DistServe", source="arxiv"))
    feedback = record_feedback(
        conn,
        Feedback(
            paper_id=paper.id,
            feedback_type=FeedbackType.RELEVANT,
            created_at=datetime.now(UTC),
        ),
    )
    assert feedback.id is not None


def test_replace_landscape(tmp_path) -> None:
    conn = _conn(tmp_path)
    paper, _ = upsert_paper(conn, DiscoveredPaper(title="DistServe", source="arxiv"))
    conn.execute(
        "INSERT INTO research_directions (id, name, config, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("d1", "Direction", "{}", "now", "now"),
    )
    replace_landscape(
        conn,
        "d1",
        [
            LandscapeEntry(
                direction_id="d1",
                category=LandscapeCategory.FOUNDATIONS,
                paper_id=paper.id,
                rank=1,
                created_at=datetime.now(UTC),
            )
        ],
    )
    rows = conn.execute("SELECT * FROM landscape_entries WHERE direction_id = 'd1'").fetchall()
    assert len(rows) == 1


def _seed_direction_and_landscape(conn, *, categories: list[LandscapeCategory]) -> list[int]:
    conn.execute(
        "INSERT INTO research_directions (id, name, config, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("d1", "Direction", "{}", "now", "now"),
    )
    entries = []
    for i, category in enumerate(categories):
        paper, _ = upsert_paper(conn, DiscoveredPaper(title=f"Paper {i}", source="arxiv"))
        entries.append(
            LandscapeEntry(
                direction_id="d1",
                category=category,
                paper_id=paper.id,
                rank=1,
                signal_summary=f"Summary {i}",
                created_at=datetime.now(UTC),
            )
        )
    replace_landscape(conn, "d1", entries)
    rows = conn.execute("SELECT id FROM landscape_entries WHERE direction_id = 'd1'").fetchall()
    return [row["id"] for row in rows]


def test_undelivered_landscape_entries_orders_by_category_then_rank(tmp_path) -> None:
    conn = _conn(tmp_path)
    _seed_direction_and_landscape(
        conn,
        categories=[
            LandscapeCategory.ADJACENT,
            LandscapeCategory.RECENT_WORK,
            LandscapeCategory.FOUNDATIONS,
            LandscapeCategory.MAJOR_APPROACHES,
        ],
    )
    results = undelivered_landscape_entries(conn, "d1")
    assert [entry.category for _, entry in results] == [
        LandscapeCategory.FOUNDATIONS,
        LandscapeCategory.MAJOR_APPROACHES,
        LandscapeCategory.RECENT_WORK,
        LandscapeCategory.ADJACENT,
    ]


def test_mark_landscape_delivered_excludes_from_future_calls(tmp_path) -> None:
    conn = _conn(tmp_path)
    entry_ids = _seed_direction_and_landscape(conn, categories=[LandscapeCategory.FOUNDATIONS])

    assert len(undelivered_landscape_entries(conn, "d1")) == 1
    mark_landscape_delivered(conn, entry_ids)
    assert undelivered_landscape_entries(conn, "d1") == []


def test_ensure_column_migrates_older_table(tmp_path) -> None:
    db_path = tmp_path / "old.db"
    conn = get_connection(db_path)
    conn.execute(
        "CREATE TABLE legacy_table (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
    )
    _ensure_column(conn, "legacy_table", "note", "TEXT")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(legacy_table)").fetchall()}
    assert "note" in columns

    # Calling it again with the column already present is a no-op, not an error.
    _ensure_column(conn, "legacy_table", "note", "TEXT")
