"""CLI entrypoint for one-time landscape discovery (section 6, 32).

    uv run python scripts/run_landscape.py --direction agentic-inference

Persists the result (`db.repository.replace_landscape`) and prints it so the
user can review/correct it (section 6: "The user must be able to review and
correct this landscape") by editing the direction's YAML and re-running.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from litagent.config import settings
from litagent.db.connection import get_connection
from litagent.db.models import LandscapeEntry
from litagent.db.repository import (
    replace_landscape,
    upsert_paper,
    upsert_research_direction,
)
from litagent.directions import load_direction
from litagent.landscape import discover_landscape


async def _run(direction_id: str) -> None:
    direction = load_direction(direction_id)
    conn = get_connection(settings.database_path)
    upsert_research_direction(conn, direction)

    print(f"Discovering literature landscape for {direction.name!r}...")
    by_category = await discover_landscape(direction)

    entries = []
    for category, hits in by_category.items():
        print(f"\n## {category.value}\n")
        for rank, hit in enumerate(hits, start=1):
            paper, _ = upsert_paper(conn, hit.paper)
            entries.append(
                LandscapeEntry(
                    direction_id=direction.id,
                    category=category,
                    paper_id=paper.id,
                    rank=rank,
                    signal_summary=hit.signal_summary,
                    created_at=datetime.now(UTC),
                )
            )
            print(f"{rank}. {hit.paper.title}")
            if hit.signal_summary:
                print(f"   {hit.signal_summary}")

    replace_landscape(conn, direction.id, entries)
    conn.commit()
    print(f"\nSaved {len(entries)} landscape entries for {direction.id}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-time landscape discovery for a direction.")
    parser.add_argument("--direction", required=True, dest="direction_id")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run(args.direction_id))


if __name__ == "__main__":
    main()
