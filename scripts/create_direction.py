"""CLI entrypoint for research-direction onboarding (functional requirement
3.1, section 32).

    uv run python scripts/create_direction.py --description "..."

Drafts a structured `ResearchDirection` from a natural-language description
and writes it to `directions/<id>.yaml` with `monitoring.enabled: false` --
the design doc requires the proposal be presented for refinement before
monitoring activates (section 3.1), so the user edits the file and flips
that flag on themselves once satisfied. Follow up with
`scripts/run_landscape.py --direction <id>` to seed the initial literature
landscape.
"""

from __future__ import annotations

import argparse
import asyncio

from pydantic import BaseModel, Field

from litagent.db.models import Priority, ResearchDirection, Scope, VenuePriority
from litagent.directions import save_direction
from litagent.llm import LLMClient, OpenAILLMClient
from litagent.prompts import render_prompt

_SYSTEM_PROMPT = (
    "You turn a researcher's informal description of a research direction "
    "into a specific, well-scoped structured research profile."
)


class DirectionDraft(BaseModel):
    id: str
    name: str
    research_question: str
    scope: Scope = Field(default_factory=Scope)
    topics: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    priority: Priority = Field(default_factory=Priority)
    venues: VenuePriority = Field(default_factory=VenuePriority)


async def draft_direction(description: str, *, client: LLMClient | None = None) -> ResearchDirection:
    client = client or OpenAILLMClient()
    prompt = render_prompt("direction_extraction.md", DESCRIPTION=description)
    draft = await client.structured(system=_SYSTEM_PROMPT, prompt=prompt, response_model=DirectionDraft)
    return ResearchDirection(**draft.model_dump())  # seeds empty, monitoring defaults (enabled=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a new research direction from a description.")
    parser.add_argument("--description", required=True)
    args = parser.parse_args()

    direction = asyncio.run(draft_direction(args.description))
    # Require explicit review before the daily pipeline picks this up.
    direction.monitoring.enabled = False
    path = save_direction(direction)
    print(f"Wrote {path} (monitoring disabled -- review it, then set monitoring.enabled: true).")
    print(f"Next: uv run python scripts/run_landscape.py --direction {direction.id}")


if __name__ == "__main__":
    main()
