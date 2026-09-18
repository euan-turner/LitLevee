def main() -> None:
    """Console-script entrypoint: `uv run litagent` runs the daily pipeline
    with default arguments. For flags (`--direction`, `--dry-run`), use
    `uv run python scripts/run_daily.py` directly.
    """
    import asyncio

    from litagent.pipeline import run_daily

    run = asyncio.run(run_daily())
    print(f"run {run.id}: status={run.status.value} surfaced={run.papers_surfaced}")
