"""Detailed paper analysis (section 14), using `agent_seed`'s canonical
prompt/schema (`prompts/analysis.md`, `db.models.PaperAnalysis`).

Deliberately decoupled from discovery/relevance -- this module only needs a
`Paper`-shaped record and a `ResearchDirection`, so the analysis
prompt/schema can change without touching either (section 14: "The analysis
workflow itself should be defined separately from the retrieval system").
"""

from __future__ import annotations

from litagent.analysis.pdf_text import fetch_pdf_text
from litagent.db.models import Paper, PaperAnalysis, ResearchDirection
from litagent.llm import LLMClient, OpenAILLMClient
from litagent.prompts import render_prompt

_SYSTEM_PROMPT = (
    "You produce precise, technically dense structured analyses of research "
    "papers for an expert reader who has not yet read the paper."
)


def _research_profile_text(direction: ResearchDirection) -> str:
    return "\n".join(
        [
            f"Direction: {direction.name} ({direction.id})",
            f"Research question: {direction.research_question}",
            "Included scope: " + ", ".join(direction.scope.included),
            "Excluded scope: " + ", ".join(direction.scope.excluded),
            "Topics: " + ", ".join(direction.topics),
            "Adjacent areas: " + ", ".join(direction.adjacent),
        ]
    )


def _metadata_text(paper: Paper, institutions: list[str]) -> str:
    return "\n".join(
        [
            f"Venue: {paper.venue or '(unknown)'}",
            f"Publication date: {paper.publication_date.date() if paper.publication_date else '(unknown)'}",
            f"Citation count: {paper.citation_count if paper.citation_count is not None else '(unknown)'}",
            f"Institutions: {', '.join(institutions) or '(unknown)'}",
            f"URL: {paper.url or '(unknown)'}",
        ]
    )


async def analyse_paper(
    paper: Paper,
    direction: ResearchDirection,
    *,
    institutions: list[str] | None = None,
    client: LLMClient | None = None,
) -> PaperAnalysis:
    client = client or OpenAILLMClient()
    paper_text = await fetch_pdf_text(paper.pdf_url)
    if not paper_text:
        paper_text = f"Title: {paper.title}\n\nAbstract: {paper.abstract or '(no abstract available)'}"

    prompt = render_prompt(
        "analysis.md",
        RESEARCH_PROFILE=_research_profile_text(direction),
        TITLE=paper.title,
        AUTHORS=", ".join(paper.authors) or "(unknown)",
        METADATA=_metadata_text(paper, institutions or []),
        PAPER_TEXT=paper_text,
    )
    return await client.structured(system=_SYSTEM_PROMPT, prompt=prompt, response_model=PaperAnalysis)
