"""The daily monitoring pipeline (section 7's 13 steps).

    1-3  discover, normalize, deduplicate  -> discover_for_direction + upsert_paper
    4-7  metadata/lexical/embedding/LLM funnel -> relevance.funnel.run_funnel
    8    detailed analysis                 -> analysis.analyse.analyse_paper
    9-10 author/institution + direction/subtopic tagging -> already attached
         to the paper_directions row by the funnel + repository.link_authors_
         and_institutions
    11   update database                   -> db.repository
    12-13 generate + post digest           -> digest.build_digest, slack.post_digest

Every paper is processed in its own try/except (section 29): one failure
never aborts the run, and the `runs` row records what happened.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from litagent.analysis.analyse import analyse_paper
from litagent.config import settings
from litagent.db.connection import get_connection
from litagent.db.models import (
    DIGESTIBLE_CATEGORIES,
    Paper,
    PaperDirectionMatch,
    ResearchDirection,
    Run,
    RunStatus,
)
from litagent.db.repository import (
    create_run,
    finish_run,
    get_paper_direction_match,
    institutions_for_paper,
    link_authors_and_institutions,
    mark_digested,
    mark_landscape_delivered,
    store_paper_direction_match,
    undelivered_landscape_entries,
    undigested_matches,
    upsert_paper,
    upsert_research_direction,
)
from litagent.digest import build_digest, build_landscape_digest, sort_for_digest
from litagent.directions import load_all_directions, load_direction, search_queries
from litagent.discovery.arxiv import ArxivSource
from litagent.discovery.base import DiscoveredPaper
from litagent.discovery.openalex import OpenAlexSource
from litagent.discovery.semantic_scholar import SemanticScholarSource
from litagent.relevance.funnel import run_funnel
from litagent.slack import post_digest

logger = logging.getLogger(__name__)

_PROVIDERS = ("arxiv", "openalex", "semantic_scholar")


async def discover_for_direction(direction: ResearchDirection) -> list[DiscoveredPaper]:
    """Query every source for `direction`'s recent publications.

    Every source here requires every word of a query to actually co-occur
    (arXiv's quoted phrase match, OpenAlex's stemmed AND match) -- so each
    topic is queried separately and the results merged, rather than joining
    all topics into one query that then matches nothing (see
    `directions.search_queries`). One query/provider failure never blocks
    the others (section 29); duplicate papers across topics/providers are
    collapsed later by `db.repository.upsert_paper`.
    """
    since = datetime.now(UTC) - timedelta(hours=direction.monitoring.publication_window_hours)
    results: list[DiscoveredPaper] = []
    for query in search_queries(direction):
        for name, coro in (
            ("arxiv", ArxivSource().search(query, max_results=50, sort_by="recency")),
            ("openalex", OpenAlexSource().works_published_since(query, since=since.date(), limit=50)),
            ("semantic_scholar", SemanticScholarSource().search_since(query, since=since.date())),
        ):
            try:
                papers = await coro
            except Exception:
                logger.exception(
                    "Discovery source %s failed for direction %s (query %r)", name, direction.id, query
                )
                continue
            results.extend(papers)
    return results


async def run_daily(
    direction_ids: list[str] | None = None, *, dry_run: bool = False
) -> Run:
    conn = get_connection(settings.database_path)
    directions = (
        [load_direction(d) for d in direction_ids]
        if direction_ids
        else [d for d in load_all_directions() if d.monitoring.enabled]
    )

    run = Run(
        id=uuid.uuid4().hex,
        started_at=datetime.now(UTC),
        status=RunStatus.RUNNING,
        direction_ids=[d.id for d in directions],
        providers_queried=list(_PROVIDERS),
    )
    create_run(conn, run)
    conn.commit()

    had_failure = False
    for direction in directions:
        try:
            await _process_direction(conn, direction, run, dry_run=dry_run)
        except Exception:
            logger.exception("Pipeline failed for direction %s", direction.id)
            had_failure = True
        conn.commit()

    run.completed_at = datetime.now(UTC)
    run.status = RunStatus.PARTIAL_FAILURE if had_failure else RunStatus.SUCCESS
    finish_run(conn, run)
    conn.commit()
    return run


async def _process_direction(
    conn, direction: ResearchDirection, run: Run, *, dry_run: bool
) -> None:
    upsert_research_direction(conn, direction)

    all_sent = await _deliver_landscape(conn, direction, run, dry_run=dry_run)

    discovered = await discover_for_direction(direction)
    run.papers_discovered += len(discovered)

    stored: list[tuple[Paper, DiscoveredPaper]] = []
    seen_paper_ids: set[str] = set()
    for candidate in discovered:
        try:
            paper, created = upsert_paper(conn, candidate)
            link_authors_and_institutions(conn, paper.id, paper.authors, candidate.institutions)
            if created:
                run.papers_deduplicated += 1
            # Only feed the (expensive) funnel candidates this direction
            # hasn't already judged -- arXiv's search has no date filter, so
            # the same old paper can be rediscovered every run otherwise,
            # burning an LLM call on a paper already accepted or rejected.
            # `seen_paper_ids` catches the same paper turning up twice
            # *within* this run (e.g. via two different topic queries, or
            # two different providers) before any paper_directions row
            # exists yet to dedupe against -- confirmed live: the same DOI
            # was fetched and analysed twice in one run without this check.
            if paper.id not in seen_paper_ids and get_paper_direction_match(conn, paper.id, direction.id) is None:
                stored.append((paper, candidate))
                seen_paper_ids.add(paper.id)
        except Exception:
            logger.exception("Failed to store candidate %r", candidate.title)

    paper_by_candidate_id = {id(candidate): paper for paper, candidate in stored}
    funnel_results = await run_funnel(direction, [candidate for _, candidate in stored])

    for result in funnel_results:
        paper = paper_by_candidate_id[id(result.paper)]
        match = PaperDirectionMatch(
            paper_id=paper.id,
            direction_id=direction.id,
            relevance_score=result.score,
            relevance_category=result.category,
            reason=result.reason,
            subtopics=result.subtopics,
            stage_reached=result.stage_reached,
            analysed=False,
            created_at=datetime.now(UTC),
        )
        if result.category in DIGESTIBLE_CATEGORIES:
            try:
                analysis = await analyse_paper(
                    paper, direction, institutions=institutions_for_paper(conn, paper.id)
                )
                match = match.model_copy(update={"analysed": True, "analysis": analysis})
                run.papers_analysed += 1
            except Exception:
                logger.exception("Analysis failed for %r -- kept as unanalysed", paper.title)
        else:
            run.papers_rejected += 1
        store_paper_direction_match(conn, match)

    digest_matches = undigested_matches(
        conn, direction.id, tuple(c.value for c in DIGESTIBLE_CATEGORIES)
    )
    entries = sort_for_digest(
        [(paper, match, institutions_for_paper(conn, paper.id)) for paper, match in digest_matches]
    )
    run.papers_surfaced += len(entries)
    text = build_digest(direction.name, entries)

    if dry_run:
        print(f"--- dry run digest for {direction.id} ---\n{text}\n")
        return

    ok = await post_digest(text)
    if ok:
        for paper, match, _ in entries:
            mark_digested(conn, paper.id, direction.id)
    run.slack_status = "sent" if (all_sent and ok) else "failed"


async def _deliver_landscape(conn, direction: ResearchDirection, run: Run, *, dry_run: bool) -> bool:
    """Post any not-yet-shown landscape entries (section 6) as their own
    message, first, before the day's regular digest. Landscape entries were
    never run through `analysis.analyse_paper` (their `signal_summary`
    already explains the paper -- see `digest.build_landscape_digest`), so
    this needs no LLM/analysis call, just a DB read and a Slack post.

    Returns whether delivery succeeded (`True` if there was nothing to
    deliver, or nothing was attempted because this is a dry run).
    """
    pending = undelivered_landscape_entries(conn, direction.id)
    if not pending:
        return True

    entries = [(paper, entry, institutions_for_paper(conn, paper.id)) for paper, entry in pending]
    text = build_landscape_digest(direction.name, entries)
    run.papers_surfaced += len(entries)

    if dry_run:
        print(f"--- dry run landscape digest for {direction.id} ---\n{text}\n")
        return True

    ok = await post_digest(text)
    if ok:
        mark_landscape_delivered(conn, [entry.id for _, entry, _ in entries if entry.id is not None])
    return ok
