"""End-to-end smoke test of the daily pipeline, in fixture mode (section 31):
every external call (discovery, funnel, analysis, Slack) is replaced by a
test double so this never touches the network or a real API key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import litagent.pipeline as pipeline_module
from litagent.db.connection import get_connection
from litagent.db.models import (
    AnalysisContext,
    Evaluation,
    FunnelStage,
    LandscapeCategory,
    LandscapeEntry,
    Monitoring,
    PaperAnalysis,
    RelevanceCategory,
    ResearchDirection,
    Scope,
)
from litagent.db.repository import (
    undelivered_landscape_entries,
    upsert_paper,
    upsert_research_direction,
)
from litagent.directions import save_direction
from litagent.discovery.base import DiscoveredPaper
from litagent.relevance.funnel import FunnelResult


def _direction(directory: Path) -> ResearchDirection:
    direction = ResearchDirection(
        id="test-direction",
        name="Test Direction",
        research_question="A test question.",
        scope=Scope(included=["testing"]),
        monitoring=Monitoring(enabled=True, publication_window_hours=48),
    )
    save_direction(direction, directory=directory)
    return direction


@pytest.mark.asyncio
async def test_run_daily_dry_run_end_to_end(tmp_path, monkeypatch) -> None:
    directions_dir = tmp_path / "directions"
    _direction(directions_dir)

    from litagent.config import settings

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))

    candidate = DiscoveredPaper(title="A Testing Paper", abstract="About testing.", source="arxiv")

    async def fake_discover(direction):
        return [candidate]

    async def fake_run_funnel(direction, candidates, **kwargs):
        return [
            FunnelResult(
                paper=candidates[0],
                stage_reached=FunnelStage.LLM,
                category=RelevanceCategory.CORE,
                score=0.9,
                subtopics=["testing"],
                reason="Directly about testing.",
            )
        ]

    async def fake_analyse_paper(paper, direction, **kwargs):
        return PaperAnalysis(
            context=AnalysisContext(why_relevant="It's about testing.", research_direction=direction.id),
            evaluation=Evaluation(summary="Works well."),
        )

    posted = []

    async def fake_post_digest(text, **kwargs):
        posted.append(text)
        return True

    monkeypatch.setattr(pipeline_module, "discover_for_direction", fake_discover)
    monkeypatch.setattr(pipeline_module, "run_funnel", fake_run_funnel)
    monkeypatch.setattr(pipeline_module, "analyse_paper", fake_analyse_paper)
    monkeypatch.setattr(pipeline_module, "post_digest", fake_post_digest)

    # Redirect directions.load_all_directions used inside pipeline module.
    import litagent.directions as directions_module

    monkeypatch.setattr(
        pipeline_module,
        "load_all_directions",
        lambda: directions_module.load_all_directions(directory=directions_dir),
    )

    run = await pipeline_module.run_daily(dry_run=True)

    assert run.papers_discovered == 1
    assert run.papers_analysed == 1
    assert run.papers_surfaced == 1
    assert posted == []  # dry run never posts
    assert run.status.value in ("success", "partial_failure")


@pytest.mark.asyncio
async def test_run_daily_posts_digest_when_not_dry_run(tmp_path, monkeypatch) -> None:
    directions_dir = tmp_path / "directions"
    _direction(directions_dir)

    from litagent.config import settings

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))

    candidate = DiscoveredPaper(title="A Testing Paper", abstract="About testing.", source="arxiv")

    async def fake_discover(direction):
        return [candidate]

    async def fake_run_funnel(direction, candidates, **kwargs):
        return [
            FunnelResult(
                paper=candidates[0],
                stage_reached=FunnelStage.LLM,
                category=RelevanceCategory.CORE,
                score=0.9,
                subtopics=["testing"],
                reason="Directly about testing.",
            )
        ]

    async def fake_analyse_paper(paper, direction, **kwargs):
        return PaperAnalysis(
            context=AnalysisContext(why_relevant="It's about testing.", research_direction=direction.id),
            evaluation=Evaluation(summary="Works well."),
        )

    posted = []

    async def fake_post_digest(text, **kwargs):
        posted.append(text)
        return True

    import litagent.directions as directions_module

    monkeypatch.setattr(pipeline_module, "discover_for_direction", fake_discover)
    monkeypatch.setattr(pipeline_module, "run_funnel", fake_run_funnel)
    monkeypatch.setattr(pipeline_module, "analyse_paper", fake_analyse_paper)
    monkeypatch.setattr(pipeline_module, "post_digest", fake_post_digest)
    monkeypatch.setattr(
        pipeline_module,
        "load_all_directions",
        lambda: directions_module.load_all_directions(directory=directions_dir),
    )

    run = await pipeline_module.run_daily(dry_run=False)

    assert len(posted) == 1
    assert "A Testing Paper" in posted[0]
    assert run.slack_status == "sent"


@pytest.mark.asyncio
async def test_run_daily_delivers_undelivered_landscape_first(tmp_path, monkeypatch) -> None:
    directions_dir = tmp_path / "directions"
    direction = _direction(directions_dir)

    from litagent.config import settings

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))

    # Seed an undelivered landscape entry directly, as scripts/run_landscape.py would.
    conn = get_connection(db_path)
    upsert_research_direction(conn, direction)
    landscape_paper, _ = upsert_paper(
        conn, DiscoveredPaper(title="Attention Is All You Need", source="arxiv")
    )
    from datetime import UTC, datetime

    from litagent.db.repository import replace_landscape

    replace_landscape(
        conn,
        direction.id,
        [
            LandscapeEntry(
                direction_id=direction.id,
                category=LandscapeCategory.FOUNDATIONS,
                paper_id=landscape_paper.id,
                rank=1,
                signal_summary="The canonical Transformer paper.",
                created_at=datetime.now(UTC),
            )
        ],
    )
    conn.commit()

    async def fake_discover(direction):
        return []  # no new candidates this run -- isolate the landscape-delivery behavior

    posted = []

    async def fake_post_digest(text, **kwargs):
        posted.append(text)
        return True

    import litagent.directions as directions_module

    monkeypatch.setattr(pipeline_module, "discover_for_direction", fake_discover)
    monkeypatch.setattr(pipeline_module, "post_digest", fake_post_digest)
    monkeypatch.setattr(
        pipeline_module,
        "load_all_directions",
        lambda: directions_module.load_all_directions(directory=directions_dir),
    )

    run = await pipeline_module.run_daily(dry_run=False)

    assert len(posted) == 2
    assert "Attention Is All You Need" in posted[0]
    assert "[FOUNDATIONAL]" in posted[0]
    assert "No papers passed" in posted[1]  # the regular digest, empty this run
    assert run.slack_status == "sent"

    conn = get_connection(db_path)
    assert undelivered_landscape_entries(conn, direction.id) == []


@pytest.mark.asyncio
async def test_run_daily_dry_run_does_not_mark_landscape_delivered(tmp_path, monkeypatch) -> None:
    directions_dir = tmp_path / "directions"
    direction = _direction(directions_dir)

    from datetime import UTC, datetime

    from litagent.config import settings
    from litagent.db.repository import replace_landscape

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))

    conn = get_connection(db_path)
    upsert_research_direction(conn, direction)
    landscape_paper, _ = upsert_paper(conn, DiscoveredPaper(title="Attention Is All You Need", source="arxiv"))
    replace_landscape(
        conn,
        direction.id,
        [
            LandscapeEntry(
                direction_id=direction.id,
                category=LandscapeCategory.FOUNDATIONS,
                paper_id=landscape_paper.id,
                rank=1,
                created_at=datetime.now(UTC),
            )
        ],
    )
    conn.commit()

    async def fake_discover(direction):
        return []

    posted = []

    async def fake_post_digest(text, **kwargs):
        posted.append(text)
        return True

    import litagent.directions as directions_module

    monkeypatch.setattr(pipeline_module, "discover_for_direction", fake_discover)
    monkeypatch.setattr(pipeline_module, "post_digest", fake_post_digest)
    monkeypatch.setattr(
        pipeline_module,
        "load_all_directions",
        lambda: directions_module.load_all_directions(directory=directions_dir),
    )

    await pipeline_module.run_daily(dry_run=True)

    assert posted == []
    conn = get_connection(db_path)
    assert len(undelivered_landscape_entries(conn, direction.id)) == 1


@pytest.mark.asyncio
async def test_run_daily_dedupes_same_paper_discovered_twice_in_one_run(tmp_path, monkeypatch) -> None:
    """The same paper can turn up via two different topic queries/providers
    in one run, before any paper_directions row exists yet to dedupe
    against -- it must still only go through the (expensive) funnel once."""
    directions_dir = tmp_path / "directions"
    _direction(directions_dir)

    from litagent.config import settings

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))

    # Two distinct DiscoveredPaper objects that upsert_paper will still
    # collapse to the same stored paper (same arxiv_id).
    duplicate_a = DiscoveredPaper(title="A Testing Paper", arxiv_id="1234.5678", source="arxiv")
    duplicate_b = DiscoveredPaper(title="A Testing Paper", arxiv_id="1234.5678", source="openalex")

    async def fake_discover(direction):
        return [duplicate_a, duplicate_b]

    funnel_calls = []

    async def fake_run_funnel(direction, candidates, **kwargs):
        funnel_calls.append(candidates)
        return [
            FunnelResult(
                paper=candidates[0],
                stage_reached=FunnelStage.LLM,
                category=RelevanceCategory.IRRELEVANT,
                score=0.1,
                subtopics=[],
                reason="Not relevant.",
            )
        ] if candidates else []

    import litagent.directions as directions_module

    monkeypatch.setattr(pipeline_module, "discover_for_direction", fake_discover)
    monkeypatch.setattr(pipeline_module, "run_funnel", fake_run_funnel)
    monkeypatch.setattr(
        pipeline_module,
        "load_all_directions",
        lambda: directions_module.load_all_directions(directory=directions_dir),
    )

    run = await pipeline_module.run_daily(dry_run=True)

    assert run.papers_discovered == 2
    assert len(funnel_calls) == 1
    assert len(funnel_calls[0]) == 1  # deduped down to one candidate
