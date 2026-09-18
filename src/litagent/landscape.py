"""One-time literature landscape discovery (section 6).

Distinct workload from daily monitoring: searches broadly and historically
(not just the recent-publication window) and ranks by multiple influence
signals rather than a relevance threshold. Adapted from what used to be
`ranking/literature.py`'s `/papers` search -- same OpenAlex-based
citation/velocity ranking and LLM on-topic filter, restructured into the
four section-6 categories and persisted (`db.repository.replace_landscape`)
instead of returned to a Slack command.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from litagent.db.models import LandscapeCategory, ResearchDirection
from litagent.directions import search_queries
from litagent.discovery.base import DiscoveredPaper
from litagent.discovery.openalex import OpenAlexSource
from litagent.llm import LLMClient, OpenAILLMClient
from litagent.prompts import render_prompt
from litagent.relevance.embedding import EmbeddingClient, filter_by_embedding

logger = logging.getLogger(__name__)

_CANDIDATE_POOL = 150
_PER_CATEGORY = 8
_OVERSELECT = 3
_RECENT_YEARS = 3


class LandscapeNote(BaseModel):
    on_topic: bool = Field(description="Whether this paper genuinely belongs in the category")
    summary: str = Field(description="At most 30 words: what this paper contributes")


@dataclass
class LandscapeHit:
    paper: DiscoveredPaper
    signal_summary: str


async def discover_landscape(
    direction: ResearchDirection,
    *,
    source: OpenAlexSource | None = None,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
) -> dict[LandscapeCategory, list[LandscapeHit]]:
    source = source or OpenAlexSource()
    llm_client = llm_client or OpenAILLMClient()

    core_shortlist = await _shortlist(direction, search_queries(direction), source, embedding_client)

    current_year = datetime.now(UTC).year
    by_citations = sorted(core_shortlist, key=lambda p: -(p.citation_count or 0))

    foundations = await _select(
        direction, LandscapeCategory.FOUNDATIONS, by_citations, _PER_CATEGORY, llm_client
    )
    used = {_key(hit.paper) for hit in foundations}

    remaining_by_citations = [p for p in by_citations if _key(p) not in used]
    major_approaches = await _select(
        direction,
        LandscapeCategory.MAJOR_APPROACHES,
        remaining_by_citations,
        _PER_CATEGORY,
        llm_client,
    )
    used |= {_key(hit.paper) for hit in major_approaches}

    recent_cutoff = current_year - _RECENT_YEARS
    by_velocity = sorted(
        (p for p in core_shortlist if _year(p) and _year(p) > recent_cutoff and _key(p) not in used),
        key=lambda p: -_citations_per_year(p, current_year),
    )
    recent_work = await _select(
        direction, LandscapeCategory.RECENT_WORK, by_velocity, _PER_CATEGORY, llm_client
    )

    adjacent_hits: list[LandscapeHit] = []
    if direction.adjacent:
        adjacent_shortlist = await _shortlist(direction, direction.adjacent, source, embedding_client)
        adjacent_shortlist = [p for p in adjacent_shortlist if _key(p) not in used]
        by_citations_adjacent = sorted(adjacent_shortlist, key=lambda p: -(p.citation_count or 0))
        adjacent_hits = await _select(
            direction, LandscapeCategory.ADJACENT, by_citations_adjacent, _PER_CATEGORY, llm_client
        )

    return {
        LandscapeCategory.FOUNDATIONS: foundations,
        LandscapeCategory.MAJOR_APPROACHES: major_approaches,
        LandscapeCategory.RECENT_WORK: recent_work,
        LandscapeCategory.ADJACENT: adjacent_hits,
    }


async def _shortlist(
    direction: ResearchDirection,
    queries: list[str],
    source: OpenAlexSource,
    embedding_client: EmbeddingClient | None,
) -> list[DiscoveredPaper]:
    """Search OpenAlex once per query and merge the pools.

    OpenAlex's `title_and_abstract.search` requires every word of a query to
    co-occur (stemmed AND, not a phrase or an OR -- see
    `discovery.openalex.OpenAlexSource.search_works`), so a single query
    built by joining every topic together returns nothing; querying one
    topic at a time and merging is what actually works.
    """
    pool_per_query = max(20, _CANDIDATE_POOL // max(1, len(queries)))
    candidates: list[DiscoveredPaper] = []
    for query in queries:
        candidates.extend(await source.search_works(query, limit=pool_per_query))
    candidates = _dedupe(candidates)
    if not candidates:
        return []
    ranked = await filter_by_embedding(
        direction, candidates, limit=len(candidates), threshold=0.15, client=embedding_client
    )
    return [paper for paper, _ in ranked]


async def _select(
    direction: ResearchDirection,
    category: LandscapeCategory,
    ranked: list[DiscoveredPaper],
    limit: int,
    llm_client: LLMClient,
) -> list[LandscapeHit]:
    if not ranked:
        return []
    candidates = ranked[: limit + _OVERSELECT]
    notes = await asyncio.gather(
        *(_note(llm_client, direction, category, paper) for paper in candidates),
        return_exceptions=True,
    )
    hits: list[LandscapeHit] = []
    for paper, note in zip(candidates, notes, strict=True):
        if isinstance(note, BaseException):
            logger.warning("Could not categorize %r: %s", paper.title, note)
            hits.append(LandscapeHit(paper=paper, signal_summary=""))
        elif note.on_topic:
            hits.append(LandscapeHit(paper=paper, signal_summary=note.summary))
    return hits[:limit]


async def _note(
    client: LLMClient, direction: ResearchDirection, category: LandscapeCategory, paper: DiscoveredPaper
) -> LandscapeNote:
    prompt = render_prompt(
        "landscape.md",
        DIRECTION_NAME=direction.name,
        RESEARCH_QUESTION=direction.research_question,
        CATEGORY=category.value,
        TITLE=paper.title,
        YEAR=str(_year(paper) or "unknown"),
        CITATION_COUNT=str(paper.citation_count if paper.citation_count is not None else "unknown"),
        ABSTRACT=paper.abstract or "(no abstract available)",
    )
    return await client.structured(
        system="You are a precise research librarian categorizing literature for a field overview.",
        prompt=prompt,
        response_model=LandscapeNote,
    )


def _year(paper: DiscoveredPaper) -> int | None:
    return paper.published_at.year if paper.published_at else None


def _citations_per_year(paper: DiscoveredPaper, current_year: int) -> float:
    year = _year(paper)
    age = max(1, current_year - year + 1) if year else 1
    return (paper.citation_count or 0) / age


def _key(paper: DiscoveredPaper) -> str:
    """Identity for dedup: the title, not the ID (OpenAlex splits citations
    across a preprint and its published version, each with its own ID)."""
    return " ".join(paper.title.lower().split())


def _dedupe(papers: list[DiscoveredPaper]) -> list[DiscoveredPaper]:
    best: dict[str, DiscoveredPaper] = {}
    for paper in papers:
        key = _key(paper)
        if key not in best or (paper.citation_count or 0) > (best[key].citation_count or 0):
            best[key] = paper
    return list(best.values())
