"""Embedding-retrieval stage of the relevance funnel (section 11).

Cheaper than the LLM classifier but still needs an API call, so it only
ever runs on the (already lexically-filtered) candidate pool, in one
batched request.
"""

from __future__ import annotations

import math
from typing import Protocol

from openai import AsyncOpenAI

from litagent.config import settings
from litagent.db.models import ResearchDirection
from litagent.discovery.base import DiscoveredPaper


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key or settings.embedding_api_key)
        self.model = model or settings.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def paper_embedding_text(paper: DiscoveredPaper) -> str:
    return f"{paper.title}\n\n{paper.abstract or ''}"


def direction_embedding_text(direction: ResearchDirection) -> str:
    parts = [
        direction.research_question,
        "Included: " + ", ".join(direction.scope.included),
        "Topics: " + ", ".join(direction.topics),
    ]
    return "\n".join(p for p in parts if p)


async def filter_by_embedding(
    direction: ResearchDirection,
    candidates: list[DiscoveredPaper],
    *,
    limit: int | None = None,
    threshold: float | None = None,
    client: EmbeddingClient | None = None,
) -> list[tuple[DiscoveredPaper, float]]:
    """Rank `candidates` by cosine similarity to `direction`, best first.

    Drops anything below `threshold` and caps the result at `limit` -- both
    default to the configured funnel thresholds (section 11: "the precise
    thresholds should be configurable").
    """
    if not candidates:
        return []
    limit = limit if limit is not None else settings.embedding_candidate_limit
    threshold = threshold if threshold is not None else settings.embedding_similarity_threshold
    client = client or OpenAIEmbeddingClient()

    texts = [paper_embedding_text(p) for p in candidates]
    direction_vector, *vectors = await client.embed([direction_embedding_text(direction), *texts])

    scored = [
        (paper, cosine_similarity(direction_vector, vector))
        for paper, vector in zip(candidates, vectors, strict=True)
    ]
    scored.sort(key=lambda item: -item[1])
    return [(paper, score) for paper, score in scored[:limit] if score >= threshold]
