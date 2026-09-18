"""Unit tests for the lexical-retrieval stage (section 11)."""

from __future__ import annotations

from litagent.db.models import ResearchDirection, Scope
from litagent.discovery.base import DiscoveredPaper
from litagent.relevance.lexical import filter_lexical, score_lexical

_DIRECTION = ResearchDirection(
    id="mlsys-llm-serving",
    name="ML Systems for Efficient LLM Inference",
    research_question="How should inference systems serve LLM workloads?",
    scope=Scope(
        included=["LLM serving", "prefill-decode disaggregation", "scheduling"],
        excluded=["LLM training systems"],
    ),
    topics=["scaling"],
)


def _paper(title: str, abstract: str) -> DiscoveredPaper:
    return DiscoveredPaper(title=title, abstract=abstract, source="test")


def test_relevant_paper_scores_positive() -> None:
    paper = _paper(
        "DistServe",
        "Disaggregating prefill and decoding for goodput-optimized LLM serving with scheduling.",
    )
    assert score_lexical(_DIRECTION, paper) > 0


def test_excluded_terms_dominate_included_ones() -> None:
    paper = _paper(
        "Scaling LLM training systems",
        "A new approach to LLM training systems with better scaling and scheduling of jobs.",
    )
    assert score_lexical(_DIRECTION, paper) <= 0


def test_unrelated_paper_scores_zero() -> None:
    paper = _paper("Ferroptosis in cancer therapy", "A biology paper about cell death pathways.")
    assert score_lexical(_DIRECTION, paper) == 0


def test_filter_lexical_drops_non_positive_scores() -> None:
    relevant = _paper("LLM serving", "A paper about LLM serving and scheduling.")
    irrelevant = _paper("Ferroptosis", "A biology paper.")
    assert filter_lexical(_DIRECTION, [relevant, irrelevant]) == [relevant]


def test_filter_lexical_respects_limit() -> None:
    papers = [_paper(f"LLM serving {i}", "LLM serving and scheduling.") for i in range(5)]
    assert len(filter_lexical(_DIRECTION, papers, limit=2)) == 2
