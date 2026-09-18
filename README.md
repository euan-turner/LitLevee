# Literature Review Agent

A personal literature-review agent that continuously monitors newly
published research relevant to your research directions, filters
irrelevant papers, produces structured overviews of relevant ones, and
delivers a daily digest to Slack.

Architecture: **GitHub Actions + SQLite + Python + a `chat:write`-only
Slack bot**. There is no always-on server -- see `new_design.md` for the
full design and `CLAUDE.md` for implementation notes and decision history.

## Status

Following `new_design.md`'s V1 milestones (section 37). Implemented:
research-direction YAML profiles, arXiv/OpenAlex/Semantic Scholar
discovery, a lexical -> embedding -> LLM relevance funnel, structured paper
analysis (author/institution tagging included), one-time landscape
discovery, the daily Slack digest, and the GitHub Actions workflow.
Interactive Slack functionality (feedback buttons, `/literature`) is
deliberately V2 -- not yet built (section 24, gated on a manual evaluation
period per section 37 milestone 8).

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- A Slack workspace where you can create an app
- No database server, no Docker -- the whole database is a single SQLite
  file (`litagent.db`)

## Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Copy the environment template and fill in secrets:

   ```bash
   cp .env.example .env
   ```

3. Create a Slack app (below) and fill in `SLACK_BOT_TOKEN` and
   `SLACK_CHANNEL_ID`. Fill in an OpenAI key for both `LLM_API_KEY` and
   `EMBEDDING_API_KEY` (currently both backed by OpenAI).

### Creating the Slack app

Only `chat:write` is needed for V1 (section 22) -- no Socket Mode, no
slash commands, no broad message-reading permission.

1. Go to <https://api.slack.com/apps> and create a new app ("From scratch").
2. Under **OAuth & Permissions**, add the `chat:write` Bot Token Scope and
   install the app to your workspace. Copy the **Bot User OAuth Token**
   into `SLACK_BOT_TOKEN` (starts with `xoxb-`).
3. In Slack, create a private channel, e.g. `#literature-euan`, and invite
   the bot to it (`/invite @your-bot-name`). Copy the channel ID (from the
   channel details / "Copy link", the ID is the last path segment) into
   `SLACK_CHANNEL_ID`.

## Creating a research direction

A research direction is a YAML file in `directions/` (see `new_design.md`
section 4), not something configured through Slack -- it's the persistent
object the whole pipeline runs against (section 2.1).

Draft one from a plain-language description (functional requirement 3.1):

```bash
uv run python scripts/create_direction.py \
    --description "I'm interested in systems and architecture for efficient
    inference of agentic AI workloads, particularly state management,
    scheduling, memory and heterogeneous execution."
```

This writes `directions/<id>.yaml` with `monitoring.enabled: false`.
**Review and edit the file** (scope, excluded topics, seeds, venues) before
enabling it -- the design doc requires this refinement step happen before
monitoring activates. When you're happy with it, set
`monitoring.enabled: true`.

Then seed its initial literature landscape (section 6) -- the foundational
papers, major approaches, recent influential work, and adjacent areas, so
you're not starting from nothing:

```bash
uv run python scripts/run_landscape.py --direction <id>
```

This is a one-time (or occasionally re-run) discovery pass, distinct from
daily monitoring -- it searches broadly and historically rather than just
the recent-publication window (section 2.2).

`directions/mlsys-llm-serving.yaml` ships as a real starter example.

## Running the daily pipeline

```bash
uv run python scripts/run_daily.py [--direction ID ...] [--dry-run]
```

Runs discovery (arXiv + OpenAlex + Semantic Scholar) -> dedup -> the
relevance funnel -> analysis of Core/Interesting papers -> a Slack digest,
for every direction with `monitoring.enabled: true` (or just the ones
named with `--direction`). `--dry-run` prints the digest instead of
posting it, and never marks papers as already-digested.

In production this runs once a day via
`.github/workflows/daily-literature.yml` (cron + manual `workflow_dispatch`
with a `dry_run` input) -- see that file for the GitHub Actions secrets it
needs (`SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `OPENAI_API_KEY`, optionally
`SEMANTIC_SCHOLAR_API_KEY`/`OPENALEX_API_KEY`).

### Persisting the database across runs

The workflow keeps `litagent.db` on a dedicated orphan `state` branch
(section 20), committing the updated file back after each run. One-time
setup, from a clone of this repo -- **push your existing local `litagent.db`
if you already have one with real data (discovered papers, delivered
landscape entries, etc.) rather than starting from empty**:

```bash
git checkout --orphan state
git rm -rf .
git add -f litagent.db   # -f: litagent.db is gitignored on main, deliberately
git commit -m "Initialize litagent state"
git push -u origin state
git checkout main
```

If you're starting fresh with no local `litagent.db` yet, create an empty
one first: `uv run python -c "from litagent.db.connection import
get_connection; get_connection('litagent.db')"`.

## Testing

```bash
uv run pytest -q
```

All tests are unit tests -- no Docker, database server, or network access
required (SQLite tests just use a `tmp_path` file; APIs and the LLM are
replaced by fixtures/fakes per section 31).

## Linting

```bash
uv run ruff check .
```

## Repository layout

See `CLAUDE.md`'s "Repository layout" section.
