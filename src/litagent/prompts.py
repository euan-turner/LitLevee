"""Loads and templates the `{{PLACEHOLDER}}`-style prompts in `prompts/`.

Prompts are version-controlled text, not code (new_design.md section 17),
so they live in their own top-level directory and are loaded at call time
rather than embedded as Python string literals -- editing prompt wording
never requires touching pipeline code.
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def render_prompt(name: str, **values: str) -> str:
    """Load `prompts/<name>` and replace each `{{KEY}}` with `values["KEY"]`."""
    text = (PROMPTS_DIR / name).read_text()
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
