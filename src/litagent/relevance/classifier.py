"""LLM relevance classifier (section 12).

The last and most expensive stage of the funnel: only the candidates that
survived lexical + embedding filtering ever reach here.
"""

from __future__ import annotations

from litagent.db.models import RelevanceJudgement, ResearchDirection
from litagent.discovery.base import DiscoveredPaper
from litagent.llm import LLMClient, OpenAILLMClient
from litagent.prompts import render_prompt

_SYSTEM_PROMPT = (
    "You are a precise, skeptical research-relevance classifier for a "
    "working ML systems researcher. Do not be generous: an abstract that "
    "merely uses similar vocabulary to the research direction is not "
    "automatically relevant."
)


def _list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "(none)"


async def classify_relevance(
    direction: ResearchDirection,
    paper: DiscoveredPaper,
    *,
    client: LLMClient | None = None,
) -> RelevanceJudgement:
    client = client or OpenAILLMClient()
    prompt = render_prompt(
        "relevance.md",
        DIRECTION_NAME=direction.name,
        RESEARCH_QUESTION=direction.research_question,
        SCOPE_INCLUDED=_list(direction.scope.included),
        SCOPE_EXCLUDED=_list(direction.scope.excluded),
        TOPICS=_list(direction.topics),
        ADJACENT=_list(direction.adjacent),
        POSITIVE_SEEDS=_list(direction.seeds.positive),
        NEGATIVE_SEEDS=_list(direction.seeds.negative),
        VENUES=_list(direction.venues.primary + direction.venues.secondary),
        TITLE=paper.title,
        AUTHORS=", ".join(paper.authors) or "(unknown)",
        VENUE="(unknown)",
        ABSTRACT=paper.abstract or "(no abstract available)",
    )
    judgement = await client.structured(
        system=_SYSTEM_PROMPT, prompt=prompt, response_model=RelevanceJudgement
    )
    return judgement.model_copy(update={"direction": direction.id})
