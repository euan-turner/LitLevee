# Literature Review Agent

## 1. Overview

Build a personal literature-review agent that continuously monitors newly published research relevant to the user's research directions, filters irrelevant papers, produces structured high-level overviews of relevant papers, and delivers a daily digest to Slack.

The system must support two distinct modes:

1. **Research-direction onboarding**

   * Used when starting a new research project.
   * Takes a natural-language description of a research direction.
   * Builds a structured research profile.
   * Discovers foundational and influential literature, including papers substantially older than the monitoring window.
   * Allows the user to refine the resulting scope.

2. **Continuous literature monitoring**

   * Runs daily.
   * Finds newly published papers from arXiv and relevant conference proceedings.
   * Filters candidates against the active research profiles.
   * Performs detailed analysis only on papers that survive relevance filtering.
   * Tags papers by authors, institutions/labs, research direction and subtopic.
   * Posts a concise daily digest to Slack.

The initial implementation should be deliberately simple:

**GitHub Actions + SQLite + Python + Slack Bot + external literature APIs.**

Do not introduce a continuously running backend until interactive Slack functionality is required.

---

# 2. Design principles

### 2.1 Research directions are persistent objects

A research direction is not simply a search query.

It is a structured representation containing:

* research question
* scope
* included topics
* excluded topics
* adjacent topics
* methods/technologies
* target venues
* positive seed papers
* negative seed papers
* relevance criteria
* monitoring configuration
* literature landscape

The representation should evolve as the user provides feedback.

### 2.2 Separate exploration from monitoring

The initial discovery process and daily monitoring are different workloads.

**Exploration:**

> "Teach me this field."

Search broadly and historically to identify:

* foundational papers
* influential systems
* major approaches
* terminology
* research communities
* important institutions/labs
* recent influential work
* adjacent research areas
* potential open problems

**Monitoring:**

> "What has appeared recently that matters to me?"

Search only recent publications and apply much stricter filtering.

### 2.3 Slack is an interface, not the source of truth

Slack should be treated as an output/interface layer.

Persistent state must live in the literature database and research-direction configuration.

### 2.4 Expensive analysis happens after filtering

Do not send every newly discovered paper to an expensive LLM analysis workflow.

Use progressively more expensive retrieval and classification stages.

### 2.5 Relevance is not binary

Papers should have:

* relevance score
* relevance category
* matched research direction
* matched subtopics
* explanation of why they are relevant

The system must preserve peripheral/adjacent papers rather than treating relevance as a simple keyword match.

---

# 3. Functional requirements

## 3.1 Research-direction creation

The system shall allow the user to create a new research direction from a natural-language description.

Example:

> "I'm interested in systems and architecture for efficient inference of agentic AI workloads, particularly state management, scheduling, memory and heterogeneous execution."

The system shall derive a proposed structured profile containing:

* name
* research question
* scope
* included topics
* excluded topics
* adjacent topics
* relevant methods/technologies
* target venues
* relevance criteria

The system shall present this proposal to the user for refinement before activating monitoring.

---

# 4. Research profile schema

Represent each direction approximately as:

```yaml
id: agentic-inference
name: Agentic Inference Systems

research_question: >
  How should ML inference systems adapt to the temporal,
  stateful and heterogeneous computation patterns created
  by autonomous agents?

scope:
  included:
    - inference systems
    - scheduling
    - state management
    - memory management
    - distributed execution
    - computer architecture

  excluded:
    - agent planning algorithms
    - prompting techniques
    - purely algorithmic memory methods

topics:
  - agentic memory
  - computer-use agents
  - multi-agent inference
  - long-running agents
  - tool-use inference

adjacent:
  - LLM serving
  - distributed systems
  - operating systems

methods:
  - GPU scheduling
  - KV cache management
  - heterogeneous execution

priority:
  core: []
  interesting: []
  peripheral: []

venues:
  primary:
    - MLSys
    - ASPLOS
    - ISCA
    - MICRO
    - OSDI

  secondary:
    - ...

seeds:
  positive: []
  negative: []

monitoring:
  enabled: true
  frequency: daily
  publication_window_hours: 48
```

The exact representation can evolve, but the above conceptual fields are mandatory.

---

# 5. Seed papers and negative examples

Seed papers are evidence used to understand the user's research direction.

They are not themselves the definition of the direction.

The system shall support:

```text
positive seeds
negative seeds
```

Positive seeds indicate:

> "Papers like this are relevant."

Negative seeds indicate:

> "Papers like this should generally not be surfaced."

Negative examples are particularly important for distinguishing neighbouring research areas.

Example:

> Agent memory algorithms are relevant only when they contain a substantial systems/infrastructure contribution.

The system should be able to incorporate this as a boundary condition in relevance classification.

---

# 6. Initial literature landscape

After a research direction is created, run a one-time **Landscape Discovery** workflow.

It should search beyond the daily monitoring period.

The resulting literature landscape should contain categories such as:

### Foundations

Approximately 5–10 highly influential papers.

### Major approaches

Approximately 5–10 papers representing important approaches/systems.

### Recent influential work

Approximately 5–10 recent papers.

### Adjacent areas

Approximately 5–10 papers that are relevant to understanding neighbouring research.

Do not simply rank by citation count.

Use multiple signals:

* citation count
* citation velocity
* influential citations
* citation/reference relationships
* presence in important recent papers
* semantic relevance
* venue
* author/institution context
* subsequent work building upon the paper

The system should construct a conceptual literature graph where practical.

Example:

```text
Research Direction
        |
        +-- Foundation A
        |      |
        |      +-- Approach A
        |      +-- Approach B
        |
        +-- Foundation B
        |      |
        |      +-- Approach C
        |
        +-- Recent Work
               |
               +-- Paper X
               +-- Paper Y
```

The user must be able to review and correct this landscape.

---

# 7. Continuous monitoring pipeline

The daily workflow shall execute:

```text
1. Discover new papers
2. Normalize metadata
3. Deduplicate
4. Metadata filtering
5. Candidate retrieval
6. Semantic retrieval
7. Relevance classification
8. Full paper analysis
9. Author/institution tagging
10. Research-direction/subtopic classification
11. Update database
12. Generate daily digest
13. Post digest to Slack
```

---

# 8. Paper discovery

Initial external sources:

1. arXiv
2. Semantic Scholar
3. OpenAlex
4. conference proceedings where practical

The implementation should abstract literature providers behind a common interface:

```python
class PaperSource(Protocol):
    def search(self, query: str, start_date: datetime, end_date: datetime) -> list[Paper]:
        ...
```

Each provider should normalize into the common `Paper` schema.

---

# 9. Paper schema

At minimum:

```python
Paper(
    id,
    title,
    abstract,
    authors,
    institutions,
    publication_date,
    venue,
    arxiv_id,
    doi,
    url,
    pdf_url,
    source,
    citation_count,
)
```

Additional fields:

```text
first_seen_at
last_updated_at
content_hash
```

---

# 10. Deduplication

The same paper may appear through multiple providers.

Deduplicate using, in descending preference:

1. DOI
2. arXiv ID
3. normalized title
4. title + author similarity

The database should maintain provider-specific identifiers separately.

---

# 11. Candidate retrieval

The daily pipeline must avoid expensive LLM analysis of the entire candidate set.

Use a funnel.

```text
ALL NEW PAPERS
      |
      v
Metadata filtering
      |
      v
Lexical retrieval
      |
      v
Embedding retrieval
      |
      v
Research-profile ranking
      |
      v
LLM relevance classifier
      |
      +------ reject
      |
      v
Detailed analysis
```

The precise thresholds should be configurable.

---

# 12. Relevance classifier

For every candidate, determine:

```json
{
  "relevant": true,
  "score": 0.87,
  "direction": "agentic-inference",
  "subtopics": [
    "state-management",
    "scheduling"
  ],
  "category": "core",
  "reason": "..."
}
```

The classifier must consider:

* research question
* scope
* included topics
* excluded topics
* adjacent topics
* positive seeds
* negative seeds
* venue
* paper abstract/title
* available full text where practical

It should explicitly distinguish:

### Core

Directly addresses the research direction.

### Interesting

Not central, but potentially useful.

### Peripheral

Adjacent research that may be worth occasional exposure.

### Irrelevant

Does not belong in the daily digest.

The daily digest should normally include only **Core** and **Interesting** papers.

---

# 13. "Why this matters to me"

Every surfaced paper must have a short research-context explanation.

Example:

> This paper studies persistent state management for long-running agents. It is relevant to the state-management component of your agentic-inference direction because it treats inactive agent state as a resource that can be managed independently of active computation.

This explanation must be generated relative to the research profile, rather than being a generic paper summary.

---

# 14. Detailed paper analysis

Only relevant papers proceed to detailed analysis.

The analysis workflow itself should be defined separately from the retrieval system so that the user can change the desired paper-overview format without modifying discovery infrastructure.

Each analysis should include at minimum:

```text
Title
Authors
Institution/lab
Venue/date
Research direction
Subtopic

Problem
Core idea
System/design
Evaluation
Key results
Relation to existing work
Why relevant to user's research
Potential limitations
Potential research opportunities
```

The exact workflow/schema should be configurable.

---

# 15. Author and institution tagging

For each analysed paper:

* normalize author names
* extract author affiliations
* normalize institutions
* identify labs/groups where possible
* store institution metadata separately

Example:

```text
Authors:
  Alice Smith
  Bob Jones

Institutions:
  Imperial College London
  University of Cambridge

Labs:
  Example Systems Lab
```

Institution/lab extraction should not prevent a paper from being surfaced if metadata is incomplete.

---

# 16. Literature database

Use SQLite for the initial implementation.

Suggested schema:

```text
research_directions
-------------------
id
name
config
created_at
updated_at
active


papers
------
id
title
abstract
publication_date
venue
doi
arxiv_id
url
pdf_url
source
citation_count
first_seen_at
last_updated_at


authors
-------
id
name
normalized_name


institutions
------------
id
name
normalized_name


paper_authors
-------------
paper_id
author_id
author_order


paper_institutions
------------------
paper_id
institution_id


paper_directions
----------------
paper_id
direction_id
relevance_score
relevance_category
reason
subtopics
analysed
analysis


feedback
--------
id
paper_id
direction_id
feedback_type
feedback_text
created_at


runs
----
id
started_at
completed_at
status
papers_discovered
papers_analysed
error
```

SQLite is sufficient for a single user and daily execution.

---

# 17. State management

The database is the canonical state.

The Git repository contains:

* code
* prompts
* research-direction definitions
* configuration
* schemas

The database contains:

* discovered papers
* analysis results
* feedback
* citation metadata
* execution state

Do not use Slack history as the persistent database.

---

# 18. Repository structure

Recommended structure:

```text
literature-agent/
│
├── agent/
│   ├── discovery/
│   ├── retrieval/
│   ├── relevance/
│   ├── analysis/
│   ├── ranking/
│   └── digest/
│
├── integrations/
│   ├── slack.py
│   ├── arxiv.py
│   ├── semantic_scholar.py
│   └── openalex.py
│
├── db/
│   ├── schema.sql
│   ├── models.py
│   └── repository.py
│
├── directions/
│   ├── agentic-inference.yaml
│   └── ...
│
├── prompts/
│   ├── direction_extraction.md
│   ├── relevance.md
│   ├── landscape.md
│   ├── analysis.md
│   └── digest.md
│
├── tests/
│
├── scripts/
│   ├── run_daily.py
│   └── run_landscape.py
│
├── pyproject.toml
│
└── .github/
    └── workflows/
        └── daily-literature.yml
```

Use Python.

Prefer typed models and explicit interfaces between pipeline stages.

---

# 19. GitHub Actions deployment

The initial deployment shall use GitHub Actions.

The daily workflow should:

```text
checkout repository
      |
restore database/state
      |
run daily pipeline
      |
post Slack digest
      |
persist updated database/state
```

Use a scheduled workflow plus manual dispatch.

Example:

```yaml
on:
  schedule:
    - cron: "17 7 * * *"
      timezone: "Europe/London"

  workflow_dispatch:
```

Schedule at a non-round minute to reduce the chance of GitHub Actions scheduling congestion.

The exact execution time is not critical.

---

# 20. Database persistence in GitHub Actions

For V1, SQLite can be persisted as a repository artifact or committed state.

Preferred initial implementation:

* workflow checks out repository
* retrieves current database
* executes pipeline
* uploads the resulting database as an artifact or commits it to a dedicated state branch/file

Avoid committing generated state to the main source branch if doing so creates noisy history.

A dedicated state branch is preferable if repository-backed persistence is selected.

If this becomes awkward, migrate the database to hosted PostgreSQL without changing the application-level repository interface.

---

# 21. Secrets

Initial GitHub Actions secrets:

```text
SLACK_BOT_TOKEN
SLACK_CHANNEL_ID
OPENAI_API_KEY
```

Add provider API keys only when required:

```text
SEMANTIC_SCHOLAR_API_KEY
OPENALEX_API_KEY
...
```

Never put secrets in:

* research-direction YAML
* source code
* prompts
* Git history
* Slack messages

Research directions are not secrets and should remain version-controlled.

---

# 22. Slack application

Create a Slack application installed into the target workspace.

Initial required capability:

```text
chat:write
```

The bot only needs permission to post the daily digest initially.

Store:

```text
SLACK_BOT_TOKEN
SLACK_CHANNEL_ID
```

as GitHub Actions secrets/configuration.

Do not initially request broad message-reading permissions.

---

# 23. Initial Slack output

The daily digest should be concise.

Example:

```text
Literature Review — 17 September 2026

3 papers worth reading today.

━━━━━━━━━━━━━━━━━━━━━━

[CORE] Agentic Inference → State Management

Paper Title
Authors · Institution · ASPLOS 2027

Why relevant:
...

Core idea:
...

Key result:
...

Relation to your work:
...

━━━━━━━━━━━━━━━━━━━━━━

[INTERESTING] ...

━━━━━━━━━━━━━━━━━━━━━━

No other papers passed the relevance threshold.
```

The Slack message should link to the paper.

Do not dump full paper analyses into the daily digest.

The database should contain the complete analysis.

---

# 24. Interactive Slack functionality — V2

The first implementation does not require a continuously running service.

When interactive functionality is added, support:

```text
@literature-agent
/literature
```

and interactive buttons/actions.

Potential interactions:

```text
Why did you include this?
Mark as relevant
Mark as irrelevant
More like this
Exclude this type
Add to research direction
```

Feedback must update the database.

---

# 25. Slack interaction architecture

For V2, introduce a small always-on service.

Preferred architecture:

```text
Slack
  |
  | Socket Mode / Events API
  v
Small Python Slack service
  |
  v
Literature database
  |
  v
Research agent
```

Socket Mode is appropriate for a personal deployment because it avoids exposing a public HTTP endpoint.

The Slack app will require an app-level token with:

```text
connections:write
```

and an `xapp-...` token.

The interactive service should remain lightweight. Expensive literature processing should be delegated to background jobs rather than performed synchronously in Slack event handlers.

---

# 26. V2 infrastructure

The always-on Slack component can run on:

* small VPS
* Cloud Run
* Fly.io
* Railway
* Render
* equivalent small container host

Do not deploy Kubernetes or other heavyweight infrastructure.

The daily literature computation can remain in GitHub Actions.

---

# 27. Hybrid final architecture

The intended mature architecture is:

```text
                         GitHub Repository
                    ┌────────────────────────┐
                    │ Agent code              │
                    │ Research profiles       │
                    │ Prompts                  │
                    │ Configuration            │
                    └───────────┬────────────┘
                                │
                       GitHub Actions
                                │
                         DAILY BATCH JOB
                                │
                                ▼
                       Literature Database
                                ▲
                                │
                ┌───────────────┴──────────────┐
                │                              │
        Literature APIs                  Slack service
                │                              │
      ┌─────────┼─────────┐             interactive
      │         │         │              queries/
     arXiv   OpenAlex  S2                 feedback
                │                              │
                └──────────────┬───────────────┘
                               │
                               ▼
                              Slack
```

---

# 28. Performance/cost requirements

The system should be designed around a funnel rather than processing every paper with an expensive model.

Target approximate daily flow:

```text
100–1000+ discovered papers
        ↓
metadata/lexical filtering
        ↓
tens–hundreds of candidates
        ↓
embedding/profile ranking
        ↓
10–30 LLM-classified papers
        ↓
5–15 detailed analyses
        ↓
3–10 Slack recommendations
```

These are targets rather than hard limits.

All thresholds must be configurable.

The implementation must record per-run:

* papers discovered
* papers deduplicated
* candidates after each filter
* LLM calls
* papers analysed
* execution time
* failures

This allows later optimisation of the pipeline.

---

# 29. Error handling

A failed paper must not fail the entire daily run.

Use per-paper failure isolation:

```text
Paper A → success
Paper B → analysis failure
Paper C → success
```

Paper B should be recorded as failed and retried on a later run.

Similarly, failure of one literature provider should not prevent processing results from other providers where possible.

Slack posting failure should be recorded and retried.

The workflow should have a final failure status if the digest could not be delivered.

---

# 30. Observability

Every run should record:

```text
run ID
start/end time
providers queried
papers discovered
papers deduplicated
papers rejected
papers analysed
papers surfaced
LLM usage
errors
Slack status
```

Initially this can simply be stored in SQLite and emitted in GitHub Actions logs.

---

# 31. Testing requirements

Unit tests are required for:

### Deduplication

* DOI matches
* arXiv ID matches
* title normalization
* title similarity

### Relevance

Use a small fixture set containing:

* clearly relevant papers
* clearly irrelevant papers
* adjacent papers
* misleading keyword matches

### Research profiles

Test parsing/validation of YAML.

### Slack

Mock Slack API calls.

### Pipeline

Provide a deterministic fixture mode where external APIs and LLM calls are replaced by test data.

The daily workflow must not be the only way to test the system.

---

# 32. Development modes

Provide:

```bash
python -m scripts.run_daily --dry-run
```

which:

* performs discovery
* performs filtering
* performs analysis
* does not post to Slack
* does not mutate production state

Also:

```bash
python -m scripts.run_daily --direction agentic-inference
```

and:

```bash
python -m scripts.run_landscape --direction agentic-inference
```

The exact CLI implementation is flexible, but equivalent functionality is required.

---

# 33. Manual review/debugging

The system should make it easy to inspect:

```text
Why was paper X rejected?
Why was paper X included?
Which research direction matched?
Which subtopic matched?
Which seed papers influenced the decision?
```

This information should be persisted rather than only appearing in temporary logs.

---

# 34. Future research-direction feedback loop

Over time, user feedback should modify the research profile.

For example:

```text
Paper X → "irrelevant"
```

can be used as a negative example.

```text
Paper Y → "more like this"
```

can be used as a positive example.

The system should not automatically rewrite the research profile after a single piece of feedback.

Instead, accumulate evidence and periodically propose:

> "I have noticed that you consistently reject papers in category X. Would you like to exclude this category from the research direction?"

The user must approve structural changes to the profile.

---

# 35. Landscape maintenance

The initial landscape is not static.

As new papers appear, the agent should be able to identify:

* emerging subtopics
* rapidly growing research areas
* new institutions/labs
* new recurring authors
* new approaches
* changes in terminology

This should initially be informational rather than automatically modifying the research profile.

Example future notification:

> "Your agentic-inference literature has increasingly split into two distinct areas: persistent agent state management and cross-agent scheduling. 11 of the last 40 relevant papers fall into the former."

---

# 36. Explicit non-requirements for V1

Do **not** initially implement:

* web UI
* multi-user support
* PostgreSQL
* Kubernetes
* continuously running agent
* automatic research-profile mutation
* sophisticated citation graph visualisation
* full-paper OCR pipeline
* automatic PDF downloading for every candidate
* broad Slack message-reading permissions
* autonomous literature-review writing

These can be added after the basic system proves useful.

---

# 37. V1 implementation milestones

## Milestone 1 — Infrastructure

Implement:

* Python project
* SQLite schema
* GitHub Actions workflow
* configuration
* secrets
* logging

## Milestone 2 — Discovery

Implement:

* arXiv provider
* Semantic Scholar provider
* OpenAlex provider
* common Paper model
* deduplication

## Milestone 3 — Research profiles

Implement:

* YAML profile
* profile validation
* profile loading
* positive/negative seeds
* subtopic definitions

## Milestone 4 — Relevance pipeline

Implement:

* lexical retrieval
* embedding retrieval
* relevance classification
* rejection logging
* relevance explanation

## Milestone 5 — Analysis

Implement configurable structured paper analysis.

## Milestone 6 — Slack

Implement:

* Slack app
* `chat:write`
* digest generation
* daily posting

## Milestone 7 — Landscape discovery

Implement the initial research-direction onboarding/landscape workflow.

## Milestone 8 — Evaluation

Run the system manually for several days and inspect:

* false positives
* false negatives
* analysis quality
* duplicate handling
* Slack digest usefulness
* API/LLM costs

Only after this evaluation should interactive Slack functionality be implemented.

---

# 38. Acceptance criteria

V1 is complete when:

1. A research direction can be represented in configuration.
2. The system can discover new papers daily.
3. Duplicate papers from multiple providers are merged.
4. New papers are filtered against a research profile.
5. Clearly irrelevant papers do not receive expensive full analysis.
6. Relevant papers receive the configured structured analysis.
7. Papers are tagged with research direction and subtopic.
8. Authors and institutions are extracted.
9. The system stores persistent state across daily runs.
10. A daily Slack digest is automatically delivered.
11. The workflow can be manually triggered.
12. Dry-run mode exists.
13. Individual paper failures do not terminate the whole run.
14. The initial landscape workflow can identify foundational literature outside the recent-publication window.
15. User feedback can eventually be represented as positive/negative evidence.
16. No always-on server is required for V1.

---

# 39. Recommended initial technology choices

| Component      | V1                                  |
| -------------- | ----------------------------------- |
| Language       | Python                              |
| Scheduling     | GitHub Actions                      |
| Database       | SQLite                              |
| Source control | GitHub                              |
| Literature     | arXiv + Semantic Scholar + OpenAlex |
| LLM            | OpenAI API                          |
| Embeddings     | OpenAI embeddings or equivalent     |
| Slack          | Slack Web API                       |
| Slack auth     | Bot token                           |
| Configuration  | YAML                                |
| Models         | Pydantic/dataclasses                |
| Testing        | pytest                              |
| Linting        | ruff                                |
| Type checking  | pyright                             |

Keep provider implementations behind interfaces so these choices can be replaced independently.

---

# 40. Long-term architecture

The intended evolution is:

```text
             ┌─────────────────────────┐
             │ Research Direction      │
             │                         │
             │ question                │
             │ scope                   │
             │ concepts                │
             │ seeds                   │
             │ feedback                │
             └────────────┬────────────┘
                          │
              ┌───────────▼───────────┐
              │ Literature Landscape  │
              │                       │
              │ foundations           │
              │ approaches            │
              │ communities           │
              │ terminology           │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │ Continuous Discovery  │
              │                       │
              │ retrieval             │
              │ filtering             │
              │ ranking               │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │ Paper Analysis        │
              │                       │
              │ structured overview   │
              │ context               │
              │ authors/labs          │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │ Research Knowledge    │
              │ Base                  │
              │                       │
              │ papers                │
              │ relationships         │
              │ feedback              │
              │ landscape             │
              └───────────┬───────────┘
                          │
                     ┌────▼────┐
                     │  Slack  │
                     └─────────┘
```

The important architectural property is that **the persistent object is the research direction and its evolving literature landscape, not the daily digest**.

The daily digest is simply one projection of that knowledge base.

