"""Deterministic fixture-mode test of the relevance funnel (section 31):
external APIs and the LLM are replaced by test doubles.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from litagent.db.models import (
    RelevanceCategory,
    RelevanceJudgement,
    ResearchDirection,
    Scope,
)
from litagent.discovery.base import DiscoveredPaper
from litagent.relevance.funnel import run_funnel

_DIRECTION = ResearchDirection(
    id="mlsys-llm-serving",
    name="ML Systems for Efficient LLM Inference",
    research_question="How should inference systems serve LLM workloads?",
    scope=Scope(included=["LLM serving", "scheduling"], excluded=["LLM training"]),
    topics=["scaling"],
)


class _FakeEmbeddingClient:
    """Returns an identical vector for every text, so cosine similarity is always 1.0."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _FakeLLMClient:
    def __init__(self, *, score: float = 0.9, category: RelevanceCategory = RelevanceCategory.CORE) -> None:
        self.score = score
        self.category = category

    async def generate(self, *, system: str, prompt: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        return RelevanceJudgement(
            relevant=True,
            score=self.score,
            direction=_DIRECTION.id,
            subtopics=["scaling"],
            category=self.category,
            reason="Directly addresses LLM serving scheduling.",
        )


def _paper(title: str) -> DiscoveredPaper:
    return DiscoveredPaper(title=title, abstract="LLM serving and scheduling.", source="test")


@pytest.mark.asyncio
async def test_funnel_rejects_lexically_irrelevant_papers() -> None:
    paper = DiscoveredPaper(title="Ferroptosis", abstract="Cell biology.", source="test")
    results = await run_funnel(
        _DIRECTION, [paper], embedding_client=_FakeEmbeddingClient(), llm_client=_FakeLLMClient()
    )
    assert len(results) == 1
    assert results[0].category == RelevanceCategory.IRRELEVANT
    assert results[0].stage_reached.value == "lexical"


@pytest.mark.asyncio
async def test_funnel_classifies_survivors_with_llm() -> None:
    paper = _paper("Relevant Serving System")
    results = await run_funnel(
        _DIRECTION, [paper], embedding_client=_FakeEmbeddingClient(), llm_client=_FakeLLMClient()
    )
    assert len(results) == 1
    assert results[0].category == RelevanceCategory.CORE
    assert results[0].stage_reached.value == "llm"
    assert results[0].subtopics == ["scaling"]


@pytest.mark.asyncio
async def test_funnel_demotes_low_confidence_core_to_irrelevant() -> None:
    paper = _paper("Relevant Serving System")
    llm_client = _FakeLLMClient(score=0.1, category=RelevanceCategory.CORE)
    results = await run_funnel(
        _DIRECTION, [paper], embedding_client=_FakeEmbeddingClient(), llm_client=llm_client
    )
    assert len(results) == 1
    assert results[0].category == RelevanceCategory.IRRELEVANT
    assert results[0].stage_reached.value == "llm"
    assert "demoted" in results[0].reason


@pytest.mark.asyncio
async def test_funnel_keeps_category_at_or_above_threshold() -> None:
    from litagent.config import settings

    paper = _paper("Relevant Serving System")
    llm_client = _FakeLLMClient(score=settings.relevance_score_threshold, category=RelevanceCategory.INTERESTING)
    results = await run_funnel(
        _DIRECTION, [paper], embedding_client=_FakeEmbeddingClient(), llm_client=llm_client
    )
    assert len(results) == 1
    assert results[0].category == RelevanceCategory.INTERESTING
