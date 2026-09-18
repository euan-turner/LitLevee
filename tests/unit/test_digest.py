"""Unit tests for digest text formatting (section 23)."""

from __future__ import annotations

from datetime import UTC, datetime

from litagent.db.models import (
    AnalysisContext,
    Evaluation,
    EvaluationResult,
    LandscapeCategory,
    LandscapeEntry,
    Paper,
    PaperAnalysis,
    PaperDirectionMatch,
    RelevanceCategory,
)
from litagent.digest import build_digest, build_landscape_digest, sort_for_digest

_NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _paper(title: str) -> Paper:
    return Paper(
        id="p1",
        title=title,
        authors=["A. Author", "B. Author"],
        url="https://arxiv.org/abs/1234.5678",
        source="arxiv",
        content_hash="h",
        first_seen_at=_NOW,
        last_updated_at=_NOW,
    )


def _match(category: RelevanceCategory, score: float) -> PaperDirectionMatch:
    return PaperDirectionMatch(
        paper_id="p1",
        direction_id="d1",
        relevance_score=score,
        relevance_category=category,
        reason="Matches scheduling work.",
        subtopics=["scheduling"],
        stage_reached="llm",
        analysed=True,
        analysis=PaperAnalysis(
            context=AnalysisContext(why_relevant="Because X.", research_direction="d1", subtopics=[]),
            evaluation=Evaluation(
                results=[EvaluationResult(metric="Goodput", improvement="2x", comparison="vs vLLM")],
                summary="Improves goodput.",
            ),
            contributions=["Disaggregates prefill and decode."],
        ),
        created_at=_NOW,
    )


def test_build_digest_empty() -> None:
    text = build_digest("Direction", [], as_of=_NOW)
    assert "No papers passed" in text


def test_build_digest_includes_paper_content() -> None:
    entries = [(_paper("DistServe"), _match(RelevanceCategory.CORE, 0.9), ["UC Berkeley"])]
    text = build_digest("Direction", entries, as_of=_NOW)
    assert "[CORE]" in text
    assert "DistServe" in text
    assert "Because X." in text
    assert "Goodput: 2x (vs vLLM)" in text
    assert "1 paper worth reading" in text


def test_sort_for_digest_orders_core_before_interesting() -> None:
    core = (_paper("Core paper"), _match(RelevanceCategory.CORE, 0.5), [])
    interesting = (_paper("Interesting paper"), _match(RelevanceCategory.INTERESTING, 0.99), [])
    assert sort_for_digest([interesting, core]) == [core, interesting]


def _landscape_entry(category: LandscapeCategory) -> LandscapeEntry:
    return LandscapeEntry(
        direction_id="d1",
        category=category,
        paper_id="p1",
        rank=1,
        signal_summary="Introduced the canonical approach.",
        created_at=_NOW,
    )


def test_build_landscape_digest_empty() -> None:
    text = build_landscape_digest("Direction", [])
    assert "run scripts/run_landscape.py" in text


def test_build_landscape_digest_includes_category_label_and_summary() -> None:
    entries = [
        (_paper("Attention Is All You Need"), _landscape_entry(LandscapeCategory.FOUNDATIONS), ["Google"])
    ]
    text = build_landscape_digest("Direction", entries)
    assert "[FOUNDATIONAL]" in text
    assert "Attention Is All You Need" in text
    assert "Introduced the canonical approach." in text
    assert "1 paper to get you oriented" in text
