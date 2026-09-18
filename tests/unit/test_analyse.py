"""Unit test for paper analysis prompt assembly (LLM call replaced by a fake)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from litagent.analysis.analyse import analyse_paper
from litagent.db.models import (
    AnalysisContext,
    Evaluation,
    Paper,
    PaperAnalysis,
    ResearchDirection,
    Scope,
)

_DIRECTION = ResearchDirection(
    id="mlsys-llm-serving",
    name="ML Systems for Efficient LLM Inference",
    research_question="How should inference systems serve LLM workloads?",
    scope=Scope(included=["LLM serving"], excluded=[]),
)

_PAPER = Paper(
    id="p1",
    title="DistServe",
    abstract="Disaggregating prefill and decoding.",
    authors=["A. Author"],
    source="arxiv",
    content_hash="hash",
    first_seen_at=datetime.now(UTC),
    last_updated_at=datetime.now(UTC),
)


class _FakeLLMClient:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    async def generate(self, *, system: str, prompt: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.last_prompt = prompt
        return PaperAnalysis(
            context=AnalysisContext(
                why_relevant="Directly relevant.", research_direction=_DIRECTION.id, subtopics=[]
            ),
            objectives=["Reduce latency"],
            challenges=["Contention between prefill and decode"],
            contributions=["Phase disaggregation"],
            evaluation=Evaluation(baselines=["vLLM"], results=[], summary="Improves goodput."),
        )


@pytest.mark.asyncio
async def test_analyse_paper_falls_back_to_abstract_without_pdf() -> None:
    client = _FakeLLMClient()
    analysis = await analyse_paper(_PAPER, _DIRECTION, client=client)
    assert analysis.context.why_relevant == "Directly relevant."
    assert client.last_prompt is not None
    assert "DistServe" in client.last_prompt
    assert "Disaggregating prefill and decoding" in client.last_prompt
