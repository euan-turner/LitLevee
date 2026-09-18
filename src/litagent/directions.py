"""Loading/saving research-direction YAML files (`directions/*.yaml`).

Research directions are version-controlled configuration (new_design.md
section 2.1, 17), not database rows -- the database only stores the
*monitoring state* derived from them (`research_directions.config` is a
cached copy for joins/display, refreshed from the YAML on every run).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from litagent.db.models import ResearchDirection

DIRECTIONS_DIR = Path(__file__).resolve().parents[2] / "directions"


def load_direction(direction_id: str, *, directory: Path = DIRECTIONS_DIR) -> ResearchDirection:
    path = directory / f"{direction_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No research direction file at {path}")
    return ResearchDirection.model_validate(yaml.safe_load(path.read_text()))


def load_all_directions(*, directory: Path = DIRECTIONS_DIR) -> list[ResearchDirection]:
    if not directory.exists():
        return []
    directions = []
    for path in sorted(directory.glob("*.yaml")):
        directions.append(ResearchDirection.model_validate(yaml.safe_load(path.read_text())))
    return directions


def search_queries(direction: ResearchDirection) -> list[str]:
    """One search query per topic (falling back to the research question).

    Every discovery/landscape source in this codebase (arXiv's quoted
    `all:"..."` phrase match, OpenAlex's `title_and_abstract.search`
    stemmed AND match) requires every word in a query to actually co-occur,
    so a single query built by concatenating a direction's whole topic list
    returns zero results in practice (verified against both APIs) --
    querying once per topic and merging the results is what these sources
    can actually answer.
    """
    return list(direction.topics) or [direction.research_question]


def save_direction(direction: ResearchDirection, *, directory: Path = DIRECTIONS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{direction.id}.yaml"
    # `exclude_none`/default ordering keeps the file close to how a human
    # would hand-author it (section 4's example), rather than however
    # Pydantic happens to serialize.
    path.write_text(yaml.safe_dump(direction.model_dump(mode="json"), sort_keys=False))
    return path
