"""Lexical-retrieval stage of the relevance funnel (section 11).

Pure string matching, no network/LLM calls -- this is the cheap first cut
that keeps the LLM classifier from ever seeing the full discovered-papers
pool (section 28: "100-1000+ discovered papers -> tens-hundreds of
candidates" before anything expensive runs).
"""

from __future__ import annotations

import re

from litagent.config import settings
from litagent.db.models import ResearchDirection
from litagent.discovery.base import DiscoveredPaper

# Excluded terms are a much stronger signal than included ones -- a paper
# matching "LLM training systems" (excluded) shouldn't survive just because
# it also mentions "scheduling" (included) in passing.
_EXCLUDED_PENALTY = 3


def _terms(direction: ResearchDirection) -> tuple[list[str], list[str]]:
    included = [
        *direction.scope.included,
        *direction.topics,
        *direction.priority.core,
        *direction.priority.interesting,
    ]
    excluded = list(direction.scope.excluded)
    return included, excluded


def _count_matches(text: str, terms: list[str]) -> int:
    count = 0
    for term in terms:
        pattern = re.escape(term.lower())
        count += len(re.findall(pattern, text))
    return count


def score_lexical(direction: ResearchDirection, paper: DiscoveredPaper) -> int:
    """Included-term matches minus a penalty per excluded-term match."""
    text = f"{paper.title}\n{paper.abstract or ''}".lower()
    included, excluded = _terms(direction)
    return _count_matches(text, included) - _EXCLUDED_PENALTY * _count_matches(text, excluded)


def filter_lexical(
    direction: ResearchDirection, candidates: list[DiscoveredPaper], *, limit: int | None = None
) -> list[DiscoveredPaper]:
    """Keep the best-scoring candidates, dropping anything with a non-positive score.

    A non-positive score means no included term matched at all, or excluded
    terms dominated -- neither is worth an embedding call.
    """
    limit = limit if limit is not None else settings.lexical_candidate_limit
    scored = [(paper, score_lexical(direction, paper)) for paper in candidates]
    scored = [(paper, score) for paper, score in scored if score > 0]
    scored.sort(key=lambda item: -item[1])
    return [paper for paper, _ in scored[:limit]]
