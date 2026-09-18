"""LLM client abstraction.

The provider is abstracted behind `LLMClient` (design doc section 7) so the
ranking/analysis/synthesis pipelines can change model/provider without
modifying their logic. Lives at the top level (not under `ranking/` or
`analysis/`) since both packages depend on it.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from litagent.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    async def generate(self, *, system: str, prompt: str) -> str:
        """Free-text generation."""
        ...

    async def structured(self, *, system: str, prompt: str, response_model: type[T]) -> T:
        """Generation constrained to `response_model`'s schema."""
        ...


class OpenAILLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key or settings.llm_api_key)
        self.model = model or settings.llm_model

    async def generate(self, *, system: str, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    async def structured(self, *, system: str, prompt: str, response_model: type[T]) -> T:
        response = await self._client.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format=response_model,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM did not return a parseable structured response")
        return parsed
