"""Orchestrates the full relevance funnel (section 11):

    metadata filtering -> lexical retrieval -> embedding retrieval
        -> LLM relevance classifier

Every candidate gets a `FunnelResult`, including ones rejected early --
`stage_reached` records how far it got, so a rejection is always
inspectable (section 33) rather than only visible in a log line.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from litagent.config import settings
from litagent.db.models import FunnelStage, RelevanceCategory, ResearchDirection
from litagent.discovery.base import DiscoveredPaper
from litagent.llm import LLMClient
from litagent.relevance.classifier import classify_relevance
from litagent.relevance.embedding import EmbeddingClient, filter_by_embedding
from litagent.relevance.lexical import filter_lexical

logger = logging.getLogger(__name__)


@dataclass
class FunnelResult:
    paper: DiscoveredPaper
    stage_reached: FunnelStage
    category: RelevanceCategory
    score: float | None
    subtopics: list[str]
    reason: str


def _rejected(paper: DiscoveredPaper, stage: FunnelStage, reason: str) -> FunnelResult:
    return FunnelResult(
        paper=paper,
        stage_reached=stage,
        category=RelevanceCategory.IRRELEVANT,
        score=None,
        subtopics=[],
        reason=reason,
    )


async def run_funnel(
    direction: ResearchDirection,
    candidates: list[DiscoveredPaper],
    *,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
) -> list[FunnelResult]:
    results: list[FunnelResult] = []

    lexical_survivors = filter_lexical(direction, candidates)
    lexical_survivor_ids = {id(p) for p in lexical_survivors}
    for paper in candidates:
        if id(paper) not in lexical_survivor_ids:
            results.append(
                _rejected(paper, FunnelStage.LEXICAL, "No included-scope terms matched.")
            )

    embedding_survivors = await filter_by_embedding(
        direction, lexical_survivors, client=embedding_client
    )
    embedding_survivor_ids = {id(paper) for paper, _ in embedding_survivors}
    for paper in lexical_survivors:
        if id(paper) not in embedding_survivor_ids:
            results.append(
                _rejected(
                    paper,
                    FunnelStage.EMBEDDING,
                    "Below the embedding-similarity threshold for this direction.",
                )
            )

    # The LLM stage is the expensive one (section 28), so it's additionally
    # capped even after the embedding filter already thinned the pool.
    shortlist = [paper for paper, _ in embedding_survivors[: settings.llm_classify_limit]]
    overflow = [paper for paper, _ in embedding_survivors[settings.llm_classify_limit :]]
    for paper in overflow:
        results.append(
            _rejected(
                paper,
                FunnelStage.EMBEDDING,
                "Embedding-ranked below the daily LLM-classification cap.",
            )
        )

    for paper in shortlist:
        try:
            judgement = await classify_relevance(direction, paper, client=llm_client)
        except Exception:
            logger.exception("Relevance classification failed for %r", paper.title)
            results.append(_rejected(paper, FunnelStage.EMBEDDING, "LLM classification failed."))
            continue
        category, reason = judgement.category, judgement.reason
        if (
            category in (RelevanceCategory.CORE, RelevanceCategory.INTERESTING)
            and judgement.score < settings.relevance_score_threshold
        ):
            # The LLM's own category label is trusted only down to a minimum
            # confidence (config.relevance_score_threshold) -- otherwise a
            # borderline "interesting" call with a low score still reaches
            # the digest just because the label itself wasn't "irrelevant".
            category = RelevanceCategory.IRRELEVANT
            reason = f"{reason} (demoted: score {judgement.score:.2f} below threshold)"
        results.append(
            FunnelResult(
                paper=paper,
                stage_reached=FunnelStage.LLM,
                category=category,
                score=judgement.score,
                subtopics=judgement.subtopics,
                reason=reason,
            )
        )

    return results
