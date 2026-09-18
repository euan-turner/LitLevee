"""CLI entrypoint for the daily monitoring pipeline (section 32).

    uv run python scripts/run_daily.py [--direction ID ...] [--dry-run]

`--dry-run` performs discovery/filtering/analysis but does not post to
Slack or mark papers as digested (it still writes the run/paper rows to the
database, since inspecting what the funnel decided is the point of a dry
run -- see `PaperAnalysis`/`paper_directions` -- but never mutates Slack or
`digested_at`).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from litagent.pipeline import run_daily


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the daily literature monitoring pipeline.")
    parser.add_argument(
        "--direction",
        action="append",
        dest="directions",
        help="Research direction id to run (repeatable). Defaults to all directions with "
        "monitoring.enabled: true.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover/filter/analyse but do not post to Slack or mark papers as digested.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    run = asyncio.run(run_daily(args.directions, dry_run=args.dry_run))
    print(
        f"run {run.id}: status={run.status.value} discovered={run.papers_discovered} "
        f"new={run.papers_deduplicated} analysed={run.papers_analysed} "
        f"surfaced={run.papers_surfaced} slack={run.slack_status}"
    )
    if run.status.value == "failure":
        sys.exit(1)


if __name__ == "__main__":
    main()
