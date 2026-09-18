# CLAUDE.md

Guidance for working on this codebase, and a record of the design decisions
made while implementing it. **As of the redesign below, `new_design.md` is
the design spec this implementation follows** (superseding
`lit_review_agent_design.md`, kept for history -- its milestone log below
this point predates the redesign and describes an architecture that no
longer exists). This file records *how* we followed the spec and *why*
deviations (if any) were made.

## Project

Literature Review Agent: continuously monitors newly published research
against one or more persistent, YAML-defined research directions, filters
and analyses relevant papers through a cost-conscious funnel, and delivers
a daily digest to Slack. Runs as a GitHub Actions batch job, not an
always-on service. SQLite (a single file, persisted on a dedicated `state`
branch) is the persistent research memory; Slack is `chat:write`-only --
output, not an interface.

## Tooling

- Python 3.12+, managed with `uv` (not pip/poetry/conda).
- Run anything with `uv run <command>` so it uses the project's `.venv`.
- Add dependencies with `uv add <pkg>` / `uv add --dev <pkg>`. Don't hand-edit
  `pyproject.toml` dependency lists or `uv.lock`.
- Lint/format with `ruff` (`uv run ruff check .`).
- Tests with `pytest` (`uv run pytest`). All tests are unit tests: SQLite
  needs no server (a `tmp_path` file is enough), and external APIs/the LLM
  are replaced by fixtures/fakes (section 31) -- no Docker, no network
  access required to run the suite.

## Repository layout

Follows the structure specified in `new_design.md` section 18, with the
Python package kept under `src/litagent/` (see the redesign entry below for
why, and CLAUDE.md's now-historical milestone log for the layout this
replaced):

```
src/litagent/
  config.py       - all environment/config access goes through here
  db/             - schema.sql (raw SQLite, no ORM), models.py (Pydantic),
                    repository.py (plain functions), connection.py
  directions.py   - load/save directions/*.yaml <-> ResearchDirection
  discovery/      - PaperSource implementations (arXiv, OpenAlex, Semantic Scholar)
  relevance/      - the funnel: lexical.py, embedding.py, classifier.py, funnel.py
  analysis/       - structured paper analysis (analyse.py, pdf_text.py)
  landscape.py    - one-time literature landscape discovery
  digest.py       - daily Slack digest text
  slack.py        - chat:write-only posting
  pipeline.py     - orchestrates the full daily run
  llm.py          - LLMClient abstraction (OpenAI)
  prompts.py      - loads/templates prompts/*.md

directions/       - research-direction YAML (version-controlled, not DB rows)
prompts/          - direction_extraction.md, relevance.md, landscape.md, analysis.md
scripts/          - run_daily.py, run_landscape.py, create_direction.py
.github/workflows/ - daily-literature.yml (cron + workflow_dispatch)
```

Nothing outside `config.py` should call `os.environ` directly.

## Design decisions log

### Redesign — migration to `new_design.md` (GitHub Actions + SQLite)

User-directed full redesign, following `new_design.md` and seeded with
`agent_seed.zip` (canonical `paper_analysis` prompt/schema, a first real
research direction `mlsys-llm-serving`, and a relevance fixture set).
Everything below this entry describes the milestone-by-milestone build of
the *previous* architecture (Postgres, an always-on Slack Bolt Socket Mode
service, DB-managed topics, interactive feedback buttons, followed-academic
monitoring, feedback-driven topic-weight personalisation) and is kept only
as history -- none of that code survived the redesign; it was deleted
rather than adapted, per explicit user go-ahead, since the new design's
constraints (no always-on server, SQLite not Postgres, `chat:write`-only
Slack) make most of it structurally incompatible rather than reusable.

- **`src/litagent/` package kept**, rather than moving to the bare
  top-level `agent/`/`integrations/`/`db/` layout `new_design.md` section 18
  shows literally -- user's explicit choice. Non-code assets the doc also
  puts at top level (`directions/`, `prompts/`, `scripts/`,
  `.github/workflows/`) do live at the repo root, since they aren't Python
  package internals.
- **Raw `sqlite3` + a committed `schema.sql`, not an ORM** -- user's
  explicit choice, matching the doc's tech table ("Models:
  Pydantic/dataclasses", no ORM listed) and section 18's
  `db/schema.sql` + `db/repository.py` shape. `db/repository.py` is plain
  functions taking a `sqlite3.Connection`, same "no repository base class"
  convention as the old codebase. The whole database is one file living on
  the `state` branch, so there's no separate migration story to run --
  `schema.sql` is applied via `CREATE TABLE IF NOT EXISTS` on every
  connection open (`db/connection.py`), which is sufficient because the
  file *is* the schema's current state, not a target migrations converge
  towards.
- **PDF text fetched for analysed papers only, not every candidate** --
  user's explicit choice. Section 36 excludes "automatic PDF downloading
  for every candidate" and a full OCR pipeline, but the analysed set is
  only ~5-15 papers/day (section 28), not every candidate, so
  `analysis/pdf_text.py` downloads + extracts text (via `pypdf`) only for
  papers that survive the relevance funnel, falling back to abstract-only
  on any fetch/parse failure (never fails the paper -- section 29).
- **`litagent.db` persisted on a dedicated orphan `state` branch, not a
  GitHub Actions artifact** -- user's explicit choice, and the only
  durable option of the two: artifacts expire (90 days by default) and the
  database is meant to accumulate indefinitely. `.github/workflows/
  daily-literature.yml` checks it out alongside `main`, restores it,
  reads/writes it locally, and pushes it back after a successful
  (non-dry-run) pass.
- **Everything not called for by `new_design.md` was deleted, not
  adapted**: `slack-bolt`/Socket Mode/slash commands/feedback buttons
  (section 24 explicitly defers all Slack interactivity to V2, gated on a
  manual evaluation period per section 37 milestone 8 that hasn't
  happened); `jobs/scheduler.py` (APScheduler -- GitHub Actions cron
  replaces it entirely, section 36 excludes "continuously running agent");
  `memory/personalization.py` and the feedback-driven topic-weight loop
  (no interactive feedback UI exists to drive it); the followed-academics
  feature (`FollowedAuthor`, `/authors`, the `+w_a*A` ranking term) -- not
  part of the new design's scope, which models interests purely through
  YAML-defined research directions and seed papers; `ranking/ranker.py`'s
  weighted-sum `S(p)` scoring -- replaced by section 12's four-way
  core/interesting/peripheral/irrelevant category, which is what the
  digest and `paper_directions.relevance_category` now key off.
- **`RelevanceCategory` (core/interesting/peripheral/irrelevant) replaces
  the old five-dimension weighted score** as the funnel's terminal
  judgement (section 12). `relevance/classifier.py` still returns a
  0.0-1.0 `score` alongside the category (used for digest ordering within
  a category, and as `undigested_matches`'s `ORDER BY`), but nothing
  combines it with other scored dimensions any more -- there's only one
  LLM judgement now, not five.
- **Every candidate the funnel considers gets a `paper_directions` row,
  including outright rejections**, with `stage_reached` recording how far
  it got (`metadata`/`lexical`/`embedding`/`llm`). This is what makes
  section 33 ("why was paper X rejected?") a query instead of a log grep --
  the old codebase never persisted rejections at all.
- **Author/institution tagging (section 15) is genuinely new**, not
  carried over: `authors`/`institutions`/`paper_authors`/
  `paper_institutions` join tables, populated from whichever source
  reports affiliations (OpenAlex's per-authorship `institutions`; arXiv and
  Semantic Scholar leave `DiscoveredPaper.institutions` empty, which never
  blocks storage per section 15's explicit requirement).
- **`pipeline.py` only runs the relevance funnel on candidates this
  direction hasn't already judged** (`get_paper_direction_match` is
  `None`), not every discovered candidate. arXiv's search API has no date
  filter, so without this a paper already accepted/rejected yesterday gets
  rediscovered and pushed through the (expensive) LLM classifier again
  every single run -- caught via reasoning through the pipeline rather than
  a failing test, since a fixture-mode test with one candidate can't
  exercise "the same paper discovered twice across two days."
- **Landscape discovery (section 6) is `landscape.py`**, adapted from what
  used to be `ranking/literature.py`'s `/papers <query>` search (same
  OpenAlex candidate pool -> embedding filter -> LLM on-topic note
  pipeline, same title-based dedup rationale -- OpenAlex holds separate
  records per preprint/published-version pair). Restructured into section
  6's four categories (foundations/major_approaches/recent_work/adjacent)
  and persisted via `db.repository.replace_landscape` instead of returned
  to a Slack command -- there is no `/papers` command any more, only
  `scripts/run_landscape.py`.
  - **"Foundations" vs "major approaches" is a pragmatic, not principled,
    split**: both rank by raw all-time citation count; foundations takes
    the top tier, major approaches the next tier with foundations
    excluded. The design doc doesn't specify how to distinguish these
    categories algorithmically (section 6's signal list is one list across
    all categories), and distinguishing "foundational" from "an important
    approach built on a foundation" really requires citation-graph
    traversal (section 6 mentions "citation/reference relationships") that
    isn't implemented -- revisit if the two categories end up looking too
    similar in practice.

### OpenAlex/arXiv query fix + `mailto` -> API key (live-testing fix)

Live-testing the first real direction
(`directions/efficient-full-duplex-multimodal-inference.yaml`, 6 topics)
crashed `scripts/run_landscape.py` with an OpenAlex `400`: `"A filter value
contains an unescaped comma"`. Chasing it down found two separate bugs, one
of which was silent (would have returned empty results forever, not an
error):

- **`title_and_abstract.search` does a stemmed AND match of every word in
  the query, not a phrase and not an OR** -- verified directly against the
  API: a query built by concatenating a direction's research question and
  all its topics (13+ words) returns zero results, even for a direction
  with plenty of real matching literature (confirmed the individual topics
  return hundreds to hundreds-of-thousands of results each). arXiv's quoted
  `all:"..."` phrase search has the same failure mode for a long
  concatenated query. This means `landscape.py`'s original `core_query =
  research_question + " " + " ".join(topics)` and `pipeline.py`'s
  `discover_for_direction`'s `" ".join(topics)` were **both silently
  returning nothing** for any direction with more than a couple of topics
  -- the crash is what surfaced it, but the daily monitoring pipeline had
  the same bug and would never have errored, just never found anything.
  Fixed by adding `directions.search_queries()` (one query per topic,
  falling back to the research question only if there are no topics) and
  having every caller (`landscape.py`'s `_shortlist`, `pipeline.py`'s
  `discover_for_direction`) query once per topic/adjacent-area and merge
  the pools, rather than ever concatenating multiple topics into one query
  string. `OpenAlexSource`'s docstrings now say this explicitly, since nothing
  in OpenAlex's or arXiv's error responses hints at it for a moderate-length
  query (it only manifested as a crash once one particular topic happened
  to contain a comma).
- **The comma itself**: OpenAlex's filter parser splits on unescaped commas
  regardless of URL-encoding conventions (httpx's default query encoder
  leaves `,` unescaped, since it's a legal, non-reserved-for-encoding
  character per RFC 3986 -- OpenAlex's proxy just treats it specially
  anyway). Fixed defensively in `OpenAlexSource` itself
  (`_sanitize_filter_value`, strips `,` and `|`) rather than relying on
  every caller remembering to sanitize -- this is cheap insurance even
  though per-topic queries make a stray comma much less likely now.
- **`OPENALEX_MAILTO` -> `OPENALEX_API_KEY`**: OpenAlex has deprecated the
  `mailto` polite-pool query parameter in favour of an API key (user
  applied for and obtained one). `config.py`, `.env`/`.env.example`, and
  `OpenAlexSource._get` all send `api_key=` instead of `mailto=` now.
  Semantic Scholar's key application was still pending at the time of this
  fix -- `SemanticScholarSource` already goes through
  `settings.semantic_scholar_api_key` and degrades to the shared
  unauthenticated pool (very low rate limit, and it was seen returning 429
  almost immediately in manual testing) when it's unset, so nothing else
  needed to change there; expect discovery/landscape runs to under-use
  Semantic Scholar until that key lands.

### Semantic Scholar rate limiting persists even with an API key

Once the user's S2 key was approved, `run_daily` still failed every
`semantic_scholar` discovery call with `429`. Reproduced directly against
the live API (outside the app): a single request with the key succeeds,
but a second request immediately after -- or even ~1 second later --
returns `429` again, and repeated `429`s kept coming across tens of
seconds of waiting in manual testing. This doesn't match a simple "1
request/second" cap; it looks like a small token bucket that empties on
the first burst and refills slowly. **Root cause on Semantic Scholar's
side is unconfirmed** -- the `429` body still says "apply for a key for
higher rate limits" even with the key attached, which could mean the key
takes longer to fully activate, or that its granted tier is still low;
this wasn't something the client side could resolve, only work around.

Fixed in `discovery/semantic_scholar.py`:

- **Module-level throttle, not per-instance**: `pipeline.discover_for_direction`
  constructs a fresh `SemanticScholarSource()` per topic query (see the
  entry above -- each topic is now its own query), so any rate-limit state
  on the instance would reset every call and throttle nothing. `_last_request_at`
  and the lock guarding it are module-level globals instead, shared across
  every `SemanticScholarSource` in the process.
- **Retry-with-backoff on 429** inside `_get` (honouring a `Retry-After`
  header if S2 sends one, otherwise a growing fixed backoff), up to
  `_MAX_RETRIES` attempts, before finally raising -- which
  `pipeline.discover_for_direction`'s existing per-provider try/except
  (section 29) still catches, so a fully exhausted S2 still degrades to
  "this run proceeds without Semantic Scholar" rather than failing the
  direction.
- Tests (`tests/unit/test_semantic_scholar_throttle.py`) use
  `httpx.MockTransport` and patch `asyncio.sleep` to a recording no-op, so
  the retry/backoff/`Retry-After` logic is verified without actually
  waiting or hitting the network.

- **`create_direction.py` (functional requirement 3.1)**: drafts a
  `ResearchDirection` from a natural-language description via a dedicated
  `DirectionDraft` LLM response model (narrower than `ResearchDirection`
  itself -- seeds and monitoring config aren't things the LLM should
  invent), then forces `monitoring.enabled: false` on write. The doc
  requires the proposal be presented for refinement before monitoring
  activates; forcing the flag off is what makes that refinement step
  non-optional rather than trusting the user to remember to review before
  the next scheduled run picks the direction up.
- **`digest.py` never calls an LLM** -- `Why relevant`/`Core idea`/`Key
  result` are pulled straight out of the already-persisted `PaperAnalysis`
  (section 23 shows a fixed format, not generated prose), so there's no
  `prompts/digest.md`; that's a deviation from section 18's literal file
  list, recorded here rather than added as a dead prompt file nothing
  reads.
- **Integration-test/Docker-dependent test infrastructure is gone**:
  `tests/integration/`, `docker-compose.yml`, and the dev/test database
  isolation problem it existed to solve (see the old milestone log's final
  entry) don't apply any more -- SQLite tests are unit tests that use a
  `tmp_path` file, so the whole "don't collide with the real dev database"
  concern this section used to describe is structurally impossible now.

### Landscape delivery + relevance-score threshold (live-testing fixes)

First live digest surfaced two problems: `scripts/run_landscape.py`'s
output was invisible (persisted to `landscape_entries`, never shown in
Slack), and too many low-relevance papers were reaching the digest.
User decisions: deliver **all four** landscape categories (not just
foundations), in foundations -> major_approaches -> recent_work -> adjacent
order; a low-confidence core/interesting judgement demotes **straight to
irrelevant**. The feedback/marking mechanism (mark a paper relevant/
irrelevant) stays deferred to the always-on-VM phase (section 25 onwards)
-- explicitly not part of this change.

- **`relevance_score_threshold` was dead config** -- defined in
  `config.py` with the docstring "minimum score to avoid the irrelevant
  category" back when the funnel was first built, but `relevance/funnel.py`
  never actually read it; the LLM's own category label was trusted
  regardless of its confidence score. Fixed: a `core`/`interesting`
  judgement scoring below the threshold is now demoted to `irrelevant` in
  `run_funnel`, with a `" (demoted: score below threshold)"` note appended
  to `reason` so it's still inspectable (section 33), not silently dropped.
- **`landscape_entries.delivered_at`** (nullable, `db/schema.sql`) tracks
  what's been shown. Since `CREATE TABLE IF NOT EXISTS` never alters an
  existing table and the user's real `litagent.db` already had this table
  from the earlier landscape run, `db/connection.py` gained a small
  forward-only migration mechanism: `_ADDED_COLUMNS` + `_ensure_column`
  (checks `PRAGMA table_info`, runs `ALTER TABLE ... ADD COLUMN` if
  missing), applied on every `get_connection()`. This is now *the* pattern
  for adding a column to an existing table in this codebase -- append to
  `_ADDED_COLUMNS`, never remove an entry once shipped.
- **`pipeline._deliver_landscape`** runs first, before discovery, and posts
  undelivered landscape entries as their own Slack message (verified live:
  correctly delivered all 17 of a real direction's landscape entries,
  grouped and labelled by category). It's a separate message from the
  day's regular digest ("first part of a daily run" per the request, and
  keeps each message a sane size) and needs no LLM call -- landscape
  entries were never run through `analysis.analyse_paper`, and don't need
  to be: `LandscapeEntry.signal_summary` (from the landscape workflow's own
  on-topic note) already explains the paper, and `digest.
  build_landscape_digest` uses it directly.
- **Found via this verification run, fixed alongside it**: the same paper
  discovered twice in one run (e.g. via two different topic queries, or two
  different providers) went through the relevance funnel *and*
  `analyse_paper` twice -- confirmed live (the same DOI's PDF was fetched
  twice in one run's logs). The existing "already judged?" guard
  (`get_paper_direction_match(...) is None`) only protects against
  reprocessing across separate daily runs, since no `paper_directions` row
  exists yet for a paper discovered for the first time -- it doesn't catch
  a duplicate *within* the same run, before that row is written. Fixed
  with a `seen_paper_ids` set alongside it in `pipeline._process_direction`.

### Milestone 1 — Slack skeleton
- Used `slack-bolt` with **Socket Mode** exactly as specified, so no public
  HTTP endpoint/ingress is needed even in production.
- `config.py` uses `pydantic-settings` (`BaseSettings`) reading from `.env`.
  This gives validation and typed access instead of scattered `os.getenv`
  calls, and matches the Pydantic-heavy stack the design doc specifies.
- Slash command handlers in `slack/commands.py` are intentionally thin
  (parse input, call service layer, format response) with no business logic.
  Milestone 1 handlers are stubs returning a fixed "isn't implemented yet"
  message, matching the design doc's explicit guidance to first establish the
  interface only.
- `slack/events.py` and `slack/views.py` exist as empty placeholders; they'll
  gain content in later milestones (interactive feedback buttons, Block Kit
  digest formatting) rather than being scaffolded speculatively now.
- `create_app()` and `main()` are split so tests can construct/import the
  Bolt `App` without requiring `SLACK_APP_TOKEN` (only needed for the actual
  Socket Mode connection).

### Milestone 2 — Database
- PostgreSQL via `pgvector/pgvector:pg17` in `docker-compose.yml` (matches
  the design doc's stack even though pgvector itself isn't used until
  Milestone 4 — starting with the right image now avoids a data migration
  later).
- **Local dev uses host port 5433, not 5432** — this machine already has a
  system-level Postgres bound to 5432, so the compose file maps
  `5433:5432` to avoid clashing with it. `DATABASE_URL` in `.env`/`.env.example`
  and the default in `config.py` all point at 5433. On a fresh VM this
  wouldn't be necessary, but keep it consistent between dev and prod configs
  rather than special-casing.
- Only `Paper`, `Topic`, and `Feedback` models are implemented so far (see
  `db/models.py`). `PaperEmbedding`, `PaperSummary`, `ReadingHistory`,
  `ResearchQuestion`, `Claim`, and `Citation` (design doc section 9) are
  deliberately deferred to the milestones that actually need them.
- `Feedback.feedback_type` is a Python `enum.Enum` mapped to a Postgres
  `ENUM` type, giving DB-level validation of the five feedback kinds from
  design doc section 18, rather than a free-text column.
- A `UniqueConstraint` on `(user_id, paper_id, feedback_type)` plus
  `record_feedback()`'s existing-row check makes recording feedback
  idempotent — repeated clicks on the same Slack button don't create
  duplicate rows.
- Alembic is wired to `litagent.db.models.Base.metadata` for autogenerate,
  and `alembic/env.py` reads the DB URL from `litagent.config.settings`
  rather than from `alembic.ini`, so there's one source of truth for the
  connection string (env vars), not two.
- `db/database.py` exposes a single `session_scope()` context manager
  (commit on success, rollback on exception) rather than a DI framework —
  sufficient for a codebase this size.
- `db/repositories.py` holds plain functions, not a generic repository base
  class — add functions as callers need them.
- Integration tests (`tests/integration/`) run against the real Dockerised
  Postgres via a `db_session` fixture that creates tables and rolls back
  after each test. They require `docker compose up -d postgres` first.

### Milestone 3 — arXiv ingestion
- `discovery/base.py` defines `DiscoveredPaper` (a plain Pydantic model, not
  the SQLAlchemy `Paper`) and the `PaperSource` protocol. Keeping this
  separate from the ORM model means discovery sources never need to know
  about the database, and swapping/adding sources (Semantic Scholar,
  OpenAlex) never touches storage code.
- `discovery/arxiv.py` calls the public arXiv Atom API directly via `httpx`
  and parses XML with the standard library `xml.etree.ElementTree` — no
  extra parsing dependency needed for one well-defined feed format.
  - Uses **`https://export.arxiv.org`**, not `http://` — arXiv 301-redirects
    HTTP to HTTPS, which breaks `httpx`'s default `raise_for_status()` before
    the redirect is followed the way you'd want for an API call. Fixed by
    calling HTTPS directly rather than following redirects.
  - Search queries are wrapped in quotes (`all:"query"`) for a phrase match.
    Without quotes, arXiv's `all:` field does a broad OR-like match, which
    combined with date-sorting the discovery job wants, returned close-to-
    random recent papers instead of relevant ones.
  - `search()` takes a `sort_by: "relevance" | "recency"` parameter rather
    than hardcoding one: ad-hoc search (`/papers`) wants relevance-ranked
    results; the discovery job wants recency, since its job is to catch
    newly published papers on a standing topic, not the all-time most
    relevant ones.
- `db/repositories.py` gained `store_discovered_paper()`, which dedups by
  shared external ID (via `get_paper_by_external_id`) before inserting —
  this is the "deduplicate" step from design doc section 13.
- `jobs/discovery.py` is the pipeline runner: for each `Topic` in the DB,
  query each configured `PaperSource`, store new papers. Runnable directly
  with `uv run python -m litagent.jobs.discovery`. Embedding generation
  (also shown in the design doc's discovery diagram) is deferred to
  Milestone 4, once pgvector storage exists.
- `memory/interests.py` adds a minimal CLI (`add` / `list`) for manually
  configuring topics, since the discovery pipeline needs at least one Topic
  row to do anything. Per design doc section 11, learning topics from
  behaviour is a later milestone — this is intentionally just enough to
  drive the pipeline manually for now.

### Milestone 4 — embeddings + vector search
- Both the LLM and embedding provider are **OpenAI** (user decision — see
  `.env.example`, both `LLM_API_KEY`/`EMBEDDING_API_KEY` should currently be
  set to the same OpenAI key). The design doc's abstraction (`LLMClient`,
  and here `EmbeddingClient`) means this can change later without touching
  the ranking pipeline.
- `PaperEmbedding` (`db/models.py`) stores one `pgvector` embedding per
  paper (of `title + abstract`), overwritten on re-embed rather than
  versioned — only the latest embedding is ever useful for retrieval.
  `EMBEDDING_DIMENSIONS = 1536` matches `text-embedding-3-small`; changing
  the embedding model to one with a different dimensionality needs a new
  migration.
- The `paper_embeddings` migration runs `CREATE EXTENSION IF NOT EXISTS
  vector` itself — pgvector ships with the `pgvector/pgvector` Docker image
  but the extension still needs enabling per-database.
- `ranking/embeddings.py` defines `EmbeddingClient` (Protocol) and
  `OpenAIEmbeddingClient`. `db/repositories.py` gained
  `papers_missing_embeddings`, `upsert_embedding`, and `nearest_papers`
  (cosine distance via `pgvector`'s SQLAlchemy comparator).
- `jobs/discovery.py` now also runs `embed_new_papers()` after storing new
  papers, so every discovery pass leaves all papers embedded.
- `ranking/search.py` (`semantic_search()`) is a **separate module** from
  the Slack handler, purely so `/papers` can be unit-tested by monkeypatching
  one async function instead of needing a live OpenAI key + database in
  every test run. `slack/commands.py` calls `asyncio.run(semantic_search(...))`
  and wraps it in a `try/except` so a search failure degrades to a friendly
  Slack message instead of a stack trace.
- `/papers` currently does **embedding similarity search only** — no LLM
  reranking yet (that's Milestone 5). Verified live: results are already
  clearly on-topic (e.g. querying "reducing latency in autoregressive LLM
  inference" surfaced several real speculative-decoding papers).
- **Gotcha hit during testing**: don't run the bot (`python -m
  litagent.slack.app`) from more than one terminal/process at a time.
  Socket Mode lets multiple connections coexist, and Slack round-robins
  slash-command deliveries across all of them — so a stale process left
  running from earlier testing intercepted commands and served old/stub
  responses even after the code was updated. Always confirm only one
  instance is running (`ps aux | grep litagent.slack.app`) before testing
  live in Slack.

### Milestone 5 — LLM relevance ranking
- `llm.py` (top-level, not under `ranking/` or `analysis/`, since both need
  it) defines `LLMClient` (Protocol: `generate` + `structured`) and
  `OpenAILLMClient`, mirroring the `EmbeddingClient` abstraction. Structured
  output uses the OpenAI SDK's `chat.completions.parse(response_format=<pydantic
  model>)`, which directly returns a validated instance of the response
  model — no manual JSON-schema wrangling needed.
- `ranking/relevance.py` defines `PaperJudgement` (relevance / novelty /
  importance / technical_depth / topic_matches / reason, per design doc
  section 14 Stage 3) and `judge_relevance(paper, interest_context, ...)`.
  `interest_context` is a **free-text string**, not the `Topic` ORM model —
  this is what lets the same judgement logic serve both the digest pipeline
  (standing topics) and ad-hoc `/papers` search (the query itself), without
  the ranking code caring which one it's judging against.
- `ranking/ranker.py` implements Stage 4's `S(p) = w_r*R + w_n*N + w_i*I +
  w_d*D - w_x*X` in `score_judgement()`, with weights read from
  `config.settings` (`ranking_weight_*`) so they're tunable via `.env`
  without a code change, per the design doc's "exact weights should be
  configurable." **Redundancy (X) is hardcoded to 0 for every candidate** —
  computing it for real needs feedback-derived negative examples / near-
  duplicate detection, which is Milestone 9 (personalisation). The weight
  still exists so wiring it up later doesn't change this module's
  interface.
- `ranking/search.py` composes the full `/papers` pipeline from the design
  doc's section 5 diagram: `search_and_rank()` = embedding retrieval
  (`candidate_limit`, default 50) → LLM reranking via `rank_by_query()` →
  top N (`result_limit`, default 10). `semantic_search()` (Milestone 4,
  embeddings only) is kept as-is since `search_and_rank` calls it directly.
- `slack/commands.py`'s `/papers` handler now shows each result's score and
  the LLM's one-line reason, not just a title link — this is the first
  visible instance of the "why you should care" framing the design doc
  treats as the product's main differentiator (section 3.1/17), even though
  the full personalised-digest format comes later (Milestone 7).
- **Gotcha hit during testing**: `.env`'s `LLM_MODEL` still held
  `claude-sonnet-5` from before the OpenAI-vs-Anthropic decision was made
  (Milestone 4 only changed the default in `config.py`, not the value
  already written to `.env`). Symptom was an OpenAI 404 "model does not
  exist." Lesson: when a config default changes, check whether `.env`
  already overrides it with a stale value.

### Milestone 6 — paper analysis
- `PaperSummary` (`db/models.py`) persists the full structured analysis
  (design doc section 16: problem/core_idea/methodology/main_results/
  limitations/novelty/related_work/why_relevant) one row per paper,
  overwritten on re-analysis — same rationale as `PaperEmbedding`: this is
  what makes analysis a one-time cost per paper regardless of how many
  times it's surfaced afterwards.
- `analysis/summarise.py` defines `PaperAnalysis` (pydantic) and
  `analyse_paper()`, structurally identical in shape to
  `ranking/relevance.py`'s `judge_relevance()` (same `interest_context: str`
  pattern, same reason: works for both the personalised digest and ad-hoc
  `/paper` lookups without caring which).
- `analysis/pipeline.py` is the `/paper` command's backing logic, split out
  for the same testability reason as `ranking/search.py`:
  - `get_or_fetch_paper()` checks the DB first, and only calls the arXiv API
    (`ArxivSource.get_by_id`, added this milestone) if the paper hasn't been
    discovered yet — so `/paper` works for *any* arXiv paper, not just ones
    already surfaced by a topic search.
  - `get_or_create_analysis()` checks for a persisted `PaperSummary` before
    calling the LLM at all. Verified live: a fresh paper took ~8.8s
    (real LLM call), a repeat lookup of the same paper took ~3ms (DB read).
  - **Known limitation, not yet fixed**: the cached analysis is not
    invalidated if the user's topics change after it was first generated —
    `why_relevant` reflects whatever interest context was active at
    analysis time. Revisit this once Milestone 9 (personalisation) is in
    place, since that's when topic weights are expected to actually change
    over time.
- `discovery/arxiv.py` gained `normalize_arxiv_id()` after live user testing
  showed that requiring a bare arXiv ID (e.g. `1706.03762`) was a clunky
  interface — people naturally paste full URLs
  (`https://arxiv.org/abs/1706.03762` or the `/pdf/...` variant). This is
  applied in `get_or_fetch_paper()`, not in the Slack handler, so the same
  normalisation applies to any future caller (e.g. `/related` in a later
  milestone).
- `/paper`'s Slack response follows the design doc section 5 format
  (Problem / Core idea / Method / Results / Limitations / Novelty / Related
  work / Why you should care) as Block-free formatted text; richer Block
  Kit formatting (buttons, sections) is deferred to Milestone 8 (feedback
  buttons), which needs Block Kit anyway.

### Milestone 7 — automated daily digest
- `Paper.digested_at` (nullable timestamp) tracks which papers have already
  been through a digest. **Design decision**: `mark_digested()` is applied
  to *every* ranked candidate in a digest run, not just the ones that made
  the top-N cut. The alternative (only marking shown papers) would let the
  undigested backlog grow unbounded and mean the LLM re-judges the same
  low-scoring leftover papers every single day. The tradeoff is that a
  decent paper narrowly missing the cut on a busy day is gone for good, not
  reconsidered tomorrow -- acceptable for an MVP, worth revisiting once
  there's a backlog problem in practice.
- `jobs/digest.py`'s `run_digest()` reuses `rank_by_interest()`
  (Milestone 5) and `get_or_create_analysis()` (Milestone 6) directly against
  standing topics (not a search query) -- no new ranking/analysis logic
  needed, just gluing existing pieces together with `undigested_papers()` as
  the candidate source.
- `slack/views.py`'s `format_digest_message()` follows the design doc
  section 3.1 layout (emoji header per paper, "Why you might care" framing)
  but as plain `mrkdwn` text, not Block Kit -- interactive buttons need
  Block Kit `actions` blocks and are deferred to Milestone 8, which needs
  Block Kit anyway for the feedback buttons.
- `jobs/scheduler.py` wires `AsyncIOScheduler` with an `IntervalTrigger`
  (discovery, every `DISCOVERY_INTERVAL_HOURS`) and a `CronTrigger` (digest,
  daily at `DIGEST_HOUR_UTC`:00 UTC). **Gotcha**: `AsyncIOScheduler.start()`
  requires a *running* event loop (`asyncio.get_running_loop()` internally),
  so the whole entrypoint has to be `asyncio.run()`-wrapped, not just called
  from a sync `main()` with `loop.run_forever()` after the fact — that raised
  `RuntimeError: no running event loop`.
- **Live-testing feedback that changed the format**:
  - Slack was auto-unfurling every `<url|title>` link in the digest into a
    disruptive inline preview card. Fixed with `unfurl_links=False,
    unfurl_media=False` on `chat_postMessage` -- there's no reason to
    preview arXiv abstract pages inline when the title is already a link.
  - The user wanted publication date and author names shown per paper
    (originally only title + analysis was shown). Both come straight from
    the already-stored `Paper` row, so this was just adding fields to
    `_paper_block()`, not a new data source.
  - The user also wanted institution/PI per paper. **arXiv's API does not
    provide this at all** (verified directly against the API -- author
    entries are name-only, no `arxiv:affiliation`). Decided not to have the
    LLM guess it from the abstract (high hallucination risk, and
    affiliation is rarely stated there anyway). Deferred to when Semantic
    Scholar is added (Milestone 10), which does return author affiliations.

### Milestone 8 — Slack feedback buttons
- `slack/views.py` gained `build_digest_blocks()`, a Block Kit version of
  the digest with a `section`/`section`/.../`actions`/`divider` group per
  paper. `format_digest_message()` (plain text) is kept as the `text=`
  fallback Slack requires/recommends alongside `blocks=` for notifications
  and accessibility -- both are sent together in `jobs/digest.py`.
- Feedback buttons cover 4 of the 5 `FeedbackType` values (👍 Relevant, 👎
  Not Relevant, ⭐ Important, 🔖 Save). **READ is deliberately excluded**:
  the "Read Paper" link button already serves that purpose, and Slack has
  no callback for external link clicks, so there's no natural trigger point
  for it in the current UI.
- `slack/events.py` is new (it was scaffolded empty back in Milestone 1 but
  never actually created until now). `register_actions()` registers one
  Bolt action handler per feedback type, matched by `action_id` (e.g.
  `feedback_relevant`) -- the button's `value` carries the paper's UUID as
  a string, decoded in the handler.
- **Gotcha hit during live testing**: clicking a single feedback button
  made the *entire* digest message vanish -- all papers, not just the one
  clicked. Cause: Slack's `response_url` (which `respond()` posts to)
  defaults to `replace_original: true`. Every `respond()` call in
  `events.py` now explicitly passes `replace_original=False` so the
  confirmation is posted as a separate ephemeral message instead of
  overwriting the digest. This is easy to miss because it only shows up
  when testing against live Slack -- nothing in local unit tests catches a
  wrong `response_url` default.
- Slack app setup requires **Interactivity & Shortcuts** to be turned on
  (separate toggle from Slash Commands, both need a placeholder Request URL
  under Socket Mode) -- documented in `README.md`'s setup steps as step 4a.

### Milestone 9 — personalisation

Design doc section 19 lists what feedback should feed into: topic weights,
paper similarity, positive/negative examples, novelty, redundancy. This
milestone wires those into the existing pipeline rather than adding a
learned ranking model (explicitly deferred -- "can eventually support a
learned ranking model").

- **Topic weights were dead code before this milestone**: `Topic.weight`
  existed on the model and the `memory/interests.py` CLI since Milestone 2,
  but `topics_to_context()` never read it -- every topic was presented to
  the LLM as equally important regardless of configured or learned weight.
  Fixed by having `topics_to_context()` sort topics by weight (descending)
  and include the numeric weight in each line's text, so the LLM treats
  higher-weight topics as higher priority. There's no embedding-weighted
  retrieval stage in the digest pipeline (design doc Stage 2's `w_i` sum)
  to wire the weight into instead -- the digest ranks *all* undigested
  papers via LLM judgement directly (see Milestone 7's notes), so the
  prompt is the only lever available.
- **`db/models.py`** gained `PaperTopicMatch`, a join table
  (`paper_id`, `topic_id`) recording which topics a digest ranking judged a
  paper to match (`PaperJudgement.topic_matches`). This is what lets a
  later feedback event look up "which topics should this feedback affect"
  without re-running an LLM judgement at feedback time -- `jobs/digest.py`
  writes rows via `store_topic_matches()` right after `rank_by_interest()`
  runs (only against standing topics, not the ad-hoc `/papers` query
  context, since there's no persistent topic to attribute query-driven
  feedback to).
- **`memory/personalization.py`** (new) is `apply_feedback_to_topic_weights()`:
  given a feedback event, look up the paper's matched topics
  (`topics_for_paper`) and nudge each one's weight by a configured delta
  (`config.settings.topic_weight_delta_*`, clamped to
  `[topic_weight_min, topic_weight_max]`). RELEVANT/SAVE and IMPORTANT use
  different (positive) deltas -- IMPORTANT is a stronger signal than a
  plain thumbs-up. `slack/events.py` calls this after `record_feedback`,
  **only when `record_feedback` reports the row as newly created** (it now
  returns `(Feedback, bool)` instead of just `Feedback`) -- otherwise
  re-clicking an already-pressed button would double-adjust the weight,
  since `record_feedback` itself is intentionally idempotent (Milestone 2).
- **Redundancy (X)** in `ranker.py`'s `score_judgement()` was hardcoded to
  0 since Milestone 5. It's now computed per candidate as the max cosine
  similarity (`ranking/redundancy.py`, pure functions, no DB) to the
  embeddings of papers the user has previously reacted to positively
  (`db.repositories.POSITIVE_FEEDBACK_TYPES` = RELEVANT/IMPORTANT/SAVE, via
  `positive_feedback_embeddings()`). This directly implements design doc
  section 15's point that a highly-relevant paper reproducing something
  already liked shouldn't necessarily outrank a less-relevant-but-novel
  one. `ranker.py` stays DB-agnostic (matching how `judge_relevance`
  already keeps DB access out of ranking) -- callers precompute a
  `redundancy_by_paper: dict[paper_id, float]` and pass it into
  `rank_by_interest`/`rank_papers`/`rank_by_query`; `jobs/digest.py` does
  this via `_compute_redundancy()`. `/papers` search (`ranking/search.py`)
  doesn't compute redundancy yet -- ad-hoc search results benefit less from
  it (the point of a search is to find something specific, not to avoid an
  echo chamber the way a passive digest does), and it would need the same
  wiring if that judgement changes later.
- No new Alembic migration logic beyond the `paper_topic_matches` table --
  everything else (weight deltas, redundancy) reads/writes existing
  columns.

### Reworked `/papers` into a literature search (out of milestone sequence)

User feedback: "`/papers` seems to largely ignore the query I give and just
rely on the weighted topics." **That was accurate, and the cause was
architectural, not a ranking bug.** `ranking/search.py` retrieved candidates
with `nearest_papers()` -- i.e. from the local database, whose entire
contents are whatever topic discovery and the author scan happened to pull
in. Any query therefore returned the same topic-shaped papers, reordered.
The LLM reranking on top made this hard to spot, because every result came
with a plausible-sounding reason.

The fix separates the two workflows the user actually wants:

- **`/daily-papers`** (`slack/commands.handle_daily_papers`) runs the
  existing scheduled pipeline on demand: author scan -> topic discovery ->
  embeddings -> `run_digest()`. No new logic, just a manual trigger for
  testing without waiting for `DIGEST_HOUR_UTC`. It `respond()`s twice --
  once immediately, since the full pipeline takes minutes and Slack's
  3-second ack would otherwise look like a timeout.
- **`/papers <query>`** is now `ranking/literature.py`, which searches
  OpenAlex rather than the local corpus, and answers "what should I read to
  understand this?" with foundational + rising work.

`ranking/search.py` was **deleted**, not kept: `semantic_search()` and
`search_and_rank()` had no caller left, and local-corpus semantic search
has no user-facing entry point in the new design.

Decisions inside `ranking/literature.py`:

- **OpenAlex, because arXiv reports no citation counts** and influence is
  the entire question being asked. `DiscoveredPaper` gained
  `citation_count: int | None` (`None` = source doesn't report them, which
  is not the same as zero).
- **`title_and_abstract.search`, not OpenAlex's general `search`
  parameter.** Verified: `search=speculative decoding large language
  models` returned "The Mips R10000 superscalar microprocessor" (1996) and
  "Decoding ferroptosis for cancer therapy" in its top results, because it
  matches full text and metadata across the whole query loosely.
- **Three filtering stages, cheapest first.** Keyword pool (100) ->
  embedding similarity (one batched call, drops wording coincidences) ->
  LLM note with an `on_topic` flag on ~8 papers per section. Running the
  LLM over the full pool would be ~100 calls per search; running no LLM at
  all left a 2007 phylogenetics paper in the results for a scheduling
  query.
- **Foundational is ranked by raw citations, recent by citations per
  year.** Raw counts inherently favour old papers -- that is what
  "foundational" means, so it isn't corrected for. Velocity is the fair
  comparison among recent work, and is what makes a 2026 paper with 20
  citations able to outrank a 2024 one with 40.
- **The two sections are computed sequentially, not concurrently.** The
  first version ran both `_explain()` calls in `asyncio.gather` and
  excluded from "recent" anything in the *over-selected* foundational pool
  -- which, at small `result_limit`, swallowed the entire recent list. The
  exclusion set can only be the *final* foundational list, which isn't
  known until the off-topic filter has run.
- **Over-select then trim** (`_OVERSELECT = 3`): the LLM drops off-topic
  papers, so selecting exactly `result_limit` up front would return short
  lists.
- **Dedup is by normalised title, not ID.** OpenAlex holds separate records
  for a preprint and its published version, each with its own ID and DOI,
  so ID-based dedup showed "Scheduling for Next Generation Triggers" twice
  in live output. The most-cited record wins, since citations split
  unevenly across duplicates.
- **Results are not stored.** Running them through `store_discovered_paper`
  would leave them with `digested_at IS NULL`, so anything the user looked
  up would turn up in tomorrow's digest -- which is supposed to be about
  newly *published* work matching standing interests.
- A `JudgeablePaper` Protocol was added to `ranking/relevance.py` (so
  `judge_relevance` could take an unstored `DiscoveredPaper`) and then
  **reverted**: the one-line notes needed their own terse response model
  (`LiteratureNote`, ~25 words, plus the `on_topic` flag) because
  `PaperJudgement.reason` came back as 3-4 sentences per paper, which is
  unreadable across ten results. With that, nothing needed the widened
  type.

### Topic management from Slack (out of milestone sequence)

Companion to the followed-academics feature: topics were configurable only
through `memory/interests.py`'s CLI, which meant the single biggest lever
on what the digest surfaces was unreachable from the interface the user
actually lives in.

- **`/topics add|remove|weight|list`**, mirroring `/authors`' subcommand
  shape for the same reason (one slash command to register, not four).
- **`add` takes `<name> | <description> [| <weight>]`, and the description
  is required.** A pipe separator rather than positional parsing because
  descriptions are sentences with spaces. Requiring it is a deliberate bit
  of friction: `Topic.description` is what `topics_to_context()` feeds the
  ranking LLM, so a topic added as a bare keyword ranks measurably worse
  than one with a sentence explaining the interest behind it. Defaulting
  the description to the name would have hidden that.
- **`/topics weight` is new capability, not just a new interface.** Since
  Milestone 9 weights drift from feedback, but nothing could set one
  directly after creation -- so a topic the agent had learned to
  de-prioritise couldn't be manually rescued. `set_topic_weight()` clamps
  to the same `topic_weight_min/max` bounds as the feedback-driven
  `adjust_topic_weight()`, and the handler reports the *stored* value back,
  since a request for weight 9 lands as 3.0.
- **Adding a topic seeds it immediately** (`memory/interests.seed_topic` ->
  `run_discovery(topics=[topic])` + `embed_new_papers()`). Without this a
  new topic does nothing until the next scheduled pass hours later, which
  reads as the command having silently failed. `run_discovery()` gained an
  optional `topics=` argument for this rather than growing a parallel
  code path. Seeding is wrapped in its own try/except: an arXiv outage
  should not lose the topic the user just typed, so the topic is stored
  first and the seed failure is reported as a caveat.
- `get_topic_by_name()` matches case-insensitively -- names now arrive from
  free-typed Slack commands, where `/topics remove KV cache` should find a
  topic added as "kv cache".
- `memory/interests.add_topic()` now returns `(topic, created)` and goes
  through `db.repositories.create_topic()` instead of constructing a
  `Topic` inline, matching `add_followed_author()`. Adding a duplicate is
  now a friendly message rather than a unique-constraint stack trace.
- Integration-test isolation was fixed as part of this work -- see the
  entry below.

### Followed academics (out of milestone sequence)

User-requested feature, built between Milestone 9 and 10: "follow" specific
researchers so the daily scan starts with their new output before the
standing topic searches. It pulls the OpenAlex half of Milestone 10
forward, but only the author-facing parts of it -- OpenAlex is *not* wired
in as a general topic `PaperSource` yet.

- **Google Scholar IDs are deliberately not supported**, despite being the
  obvious identifier a user would reach for. Scholar has no public API and
  actively blocks scraping, so a Scholar profile ID cannot be used to fetch
  anything programmatically. **OpenAlex** is used instead: free, keyless,
  and it assigns every author a stable disambiguated ID, which is the
  thing that makes "watch this person" possible at all. `/authors add`
  accepts an OpenAlex ID, an ORCID, or a plain name (resolved via
  OpenAlex's author search). A `google_scholar_id` column was considered
  and rejected -- storing an identifier nothing can query is dead weight.
- **Name resolution refuses to guess.** `memory/authors.py`'s
  `resolve_author()` only auto-accepts a name when the top candidate has
  at least 4x the publication count of the runner-up (`_AMBIGUITY_RATIO`);
  otherwise it hands the candidate list back for the user to pick an ID
  from. Following the wrong namesake would quietly poison the digest with
  a stranger's papers, and that failure is silent and slow to notice.
- **Two sources per author, for different reasons.**
  `jobs/discovery.py`'s `discover_for_author()` queries OpenAlex by author
  *ID* (authoritative, but its index lags publication by weeks -- verified
  live: an author with four arXiv preprints in the last 45 days had none
  of them in OpenAlex yet) and arXiv by author *name* (ambiguous for
  common names, but preprints appear the day they're submitted).
  `store_discovered_paper`'s existing dedup collapses the overlap. Making
  this work needed `_arxiv_id_from_doi()` in `discovery/openalex.py`:
  arXiv preprints are indexed under a `10.48550/arXiv.<id>` DOI, so the
  arXiv ID can be recovered from it and matched against papers already
  stored by `ArxivSource`.
- **OpenAlex abstracts arrive as an inverted index** (`{word: [positions]}`,
  for licensing reasons), not text -- `_reconstruct_abstract()` reassembles
  them, otherwise every OpenAlex-sourced paper would reach the embedder and
  the LLM with no abstract at all.
- **Attribution happens on store, not on discovery.**
  `db.repositories.link_followed_authors()` is called from
  `store_discovered_paper()`, so a followed author's paper is flagged
  whichever query surfaced it -- a topic search finding their paper counts
  the same as the author scan finding it. `add_followed_author()` also runs
  `backfill_author_matches()`, since otherwise following someone would only
  flag papers stored *after* the follow and their existing work in the DB
  would look like it came from nobody.
- **Name matching lives in `discovery/base.py`** (`normalize_author_name`,
  `author_names_match`) purely because both the discovery sources and
  `db/repositories.py` need it and neither may import the other
  (`memory/authors.py` would have been the natural home, but it imports
  repositories, so that direction circles). Matching requires an exact
  surname plus compatible given names, where a single letter counts as an
  initial -- "I. Stoica" matches "Ion Stoica" but "Ioana Stoica" doesn't.
  Comparing initials alone was the first cut and produced exactly that
  false positive.
- **Ranking gained a `+ w_a*A` term**, extending design doc section 14's
  `S(p)`: A is 1 when a followed academic wrote the paper.
  `ranking_weight_followed_author` (default 0.15) is configurable like the
  other weights. It's a flat bonus rather than another LLM-judged
  dimension because authorship is a fact, not a judgement -- and the point
  of following someone is that their work gets a hearing even when the
  abstract doesn't obviously hit a standing topic. `RankedPaper` carries
  `followed_authors: list[str]` so the same lookup drives both the bonus
  and the digest's "📌 You follow ..." line (`slack/views.py`'s new
  `_byline()`, shared by the plain-text and Block Kit renderings).
- **One `/authors` slash command with `add`/`remove`/`list` subcommands**,
  not three separate commands -- each new slash command has to be
  registered by hand in the Slack app config, so subcommands keep that
  setup step to a single addition (README step 4).
- `FollowedAuthor.last_checked_at` bounds each scan (`from_publication_date`
  on OpenAlex; applied client-side for arXiv, whose API has no date filter
  alongside an author query), so a followed author's entire back catalogue
  isn't refetched every pass. A never-scanned author looks back
  `AUTHOR_SCAN_LOOKBACK_DAYS` (default 30).
- Integration tests initially ran against the dev database and collided
  with the user's real data; see the test-isolation entry below for the
  fix.

### Integration tests run against a separate database

Integration tests originally used `DATABASE_URL` directly, i.e. the dev
database, and asserted on query results. That collided with real data in
three escalating ways over a few days: a fixture `Topic` named
"heterogeneous inference" hit a unique violation because the user really
has that topic; `test_followed_author_repositories.py` broke the moment the
user followed the real Ion Stoica in Slack; and both `test_digest_*` tests
started failing once the corpus passed 100 undigested papers, because the
fixture's paper fell outside `undigested_papers(limit=100)`. Symptoms look
like product bugs and get worse as the agent is used, which is the worst
property a test suite can have.

`tests/integration/conftest.py` now:

- derives a `<database>_test` URL from `settings.database_url` and creates
  that database (plus the `vector` extension) on first use;
- **rebinds `db.database.SessionLocal`/`engine`** to it for the test
  session, because some integration tests exercise production code that
  opens its own session via `session_scope()` (`analysis/pipeline.py`,
  `jobs/*`) -- without this they'd write to the dev database while the
  fixture read from the test one;
- isolates each test by **truncating every table before it**, not by
  wrapping it in a transaction that gets rolled back. The transaction
  approach was tried first and broke
  `test_get_or_create_analysis_reuses_persisted_summary`, which
  deliberately commits so a *separate* connection (`session_scope()`) can
  see the row -- an enclosing uncommitted transaction makes that
  impossible.

Verified afterwards that the dev database was untouched (125 papers, 3
topics, 3 followed authors, unchanged).

## Working conventions
- Prefer editing over rewriting; keep diffs minimal.
- No speculative abstractions — build what the current milestone needs.
- Update this file's decisions log as new milestones land, and keep
  `README.md` in sync with actual usage instructions (setup, running,
  testing, deployment).
