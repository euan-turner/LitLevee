# Literature Review Agent

## 1. Overview

The Literature Review Agent is a persistent research assistant that continuously discovers academic papers relevant to the user's research interests, analyses them, and delivers concise personalised summaries through a private Slack channel.

The system is designed around three principles:

1. **Continuous discovery** rather than manual literature searches.
2. **Personalised relevance** rather than simple keyword matching.
3. **Persistent research memory** rather than treating every interaction independently.

Slack is the primary user interface. The agent communicates with the user through a private Slack channel that functions similarly to a DM, while PostgreSQL stores the persistent research state.

The initial system should be deliberately simple and deterministic:

```text
discover → deduplicate → retrieve → rank → analyse → notify
```

Agentic behaviour should be introduced later where it provides genuine value, particularly for deeper literature searches, synthesis, research-question tracking, and deciding which research actions to perform.

---

# 2. Goals

## 2.1 Primary goals

The system should:

- continuously discover newly published papers;
- identify papers relevant to the user's research interests;
- avoid repeatedly recommending papers the user has already seen;
- produce concise but technically useful summaries;
- explain **why a paper is relevant to the user**;
- deliver summaries automatically to a private Slack channel;
- learn from explicit user feedback;
- maintain a persistent representation of the user's research interests;
- support interactive literature searches;
- build a graph of related papers and citations;
- periodically synthesise developments across the literature.

## 2.2 Non-goals initially

The first version should not attempt to:

- autonomously read every paper in existence;
- run a large local LLM;
- deploy Kubernetes;
- maintain a complex multi-agent architecture;
- perfectly model the entire academic citation graph;
- replace a reference manager;
- automatically make high-confidence claims about scientific correctness.

The system should first become a **useful paper discovery and summarisation service**.

---

# 3. User experience

The primary interface is a **private Slack channel**.

For example:

```text
#literature-euan
```

The bot posts directly into this channel. The channel should be private and accessible only to the user and the bot, making it functionally similar to a DM while retaining the advantages of a persistent Slack channel.

The bot should not initially spam the user's normal research channels.

## 3.1 Daily digest

A typical message:

```text
📚 Literature Digest
1 September 2026

I found 4 papers worth your attention.

━━━━━━━━━━━━━━━━━━━━━━

🔥 Heterogeneous LLM Serving

Why you might care

This paper directly addresses dynamic placement of
LLM inference across heterogeneous accelerators,
which matches your current interest in heterogeneous
inference systems.

Core idea

...

Main result

...

Limitations

...

[Read Paper] [Deep Dive]
[👍 Relevant] [👎 Not Relevant] [🔖 Save]

━━━━━━━━━━━━━━━━━━━━━━

🧠 Agentic Memory ...

...
```

The important distinction is that the bot should provide both:

**Objective summary**

> What does this paper do?

and:

**Personalised interpretation**

> Why should I care about this paper?

The latter is the primary differentiator from a generic paper-newsletter service.

---

# 4. Slack interface

## 4.1 Slack application

Create a Slack App using Slack Bolt for Python.

Use **Socket Mode** so the application can maintain a WebSocket connection to Slack without requiring a publicly exposed HTTP endpoint.

The basic architecture is:

```text
                    Slack
                      │
                WebSocket
                      │
                      ▼
              ┌───────────────┐
              │ Slack Bolt App│
              └───────────────┘
```

Socket Mode is supported directly by Slack's current Bolt Python tooling.

## 4.2 Slack permissions

Initially request only the permissions required for:

- posting messages;
- receiving relevant events;
- receiving interactive button actions;
- responding to commands.

Avoid giving the bot broad workspace access unnecessarily.

## 4.3 Private channel

Create a private channel:

```text
#literature-euan
```

Invite the bot.

All automated research notifications should initially go here.

This gives a much cleaner UX than posting into a general-purpose research channel.

---

# 5. Slack commands

The initial interface should expose four commands.

## `/papers`

Search the literature.

Example:

```text
/papers speculative decoding
```

Pipeline:

```text
query
  ↓
embedding
  ↓
vector retrieval
  ↓
metadata filtering
  ↓
LLM reranking
  ↓
Slack results
```

---

## `/paper`

Analyse a specific paper.

```text
/paper 2405.12345
```

Output:

```text
📄 Paper Title

TL;DR
...

Problem
...

Core idea
...

Method
...

Results
...

Limitations
...

Why you should care
...

Related work
...
```

---

## `/related`

Given a paper, find related work.

```text
/related 2405.12345
```

Use:

- vector similarity;
- papers cited by the target;
- papers citing the target;
- author/topic similarity.

---

## `/research`

Perform a deeper literature investigation.

```text
/research heterogeneous inference for agentic workloads
```

Unlike `/papers`, this should eventually allow the agent to plan multiple retrieval actions:

```text
query
 ↓
search literature
 ↓
inspect promising papers
 ↓
follow citations
 ↓
search related concepts
 ↓
identify disagreements
 ↓
synthesise
```

This is where genuinely agentic behaviour should eventually live.

---

# 6. Architecture

The complete system should look like:

```text
                         ┌─────────────────────┐
                         │        Slack        │
                         │                     │
                         │ #literature-euan    │
                         │ /papers             │
                         │ /paper              │
                         │ /related            │
                         │ /research            │
                         │                     │
                         │ 👍 👎 ⭐ 🔖 📖       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Slack Service    │
                         │                     │
                         │ Bolt / Socket Mode  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │ Research Orchestrator  │
                       └────────────┬───────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
             ▼                      ▼                      ▼
      ┌────────────┐         ┌────────────┐         ┌────────────┐
      │ Discovery  │         │  Ranking   │         │  Analysis  │
      │            │         │            │         │            │
      │ arXiv      │         │ embeddings │         │ extraction │
      │ Semantic   │         │ relevance  │         │ summary    │
      │ Scholar    │         │ novelty    │         │ critique   │
      │ OpenAlex   │         │ feedback   │         │ synthesis  │
      └─────┬──────┘         └─────┬──────┘         └─────┬──────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │     PostgreSQL         │
                       │                        │
                       │ papers                 │
                       │ embeddings             │
                       │ topics                 │
                       │ feedback               │
                       │ summaries              │
                       │ citations              │
                       │ research questions     │
                       │ claims                 │
                       └────────────────────────┘

                                   ▲
                                   │
                           ┌───────┴────────┐
                           │    Scheduler   │
                           │                │
                           │ 6-hour ingest  │
                           │ daily digest   │
                           │ weekly review  │
                           │ maintenance    │
                           └────────────────┘
```

---

# 7. Technology stack

## Application

```text
Python 3.12+
uv
Pydantic
SQLAlchemy
httpx
```

## Slack

```text
slack-bolt
Socket Mode
```

## Database

```text
PostgreSQL
pgvector
```

PostgreSQL should be the source of truth for all persistent research state.

## Scheduling

Initially:

```text
APScheduler
```

There is no need for Celery, Kafka, Airflow, etc. for the first version.

## LLM

Use an external LLM API.

The system should abstract the provider:

```python
class LLMClient(Protocol):
    async def generate(...)
    async def structured(...)
```

This allows the model/provider to be changed without modifying the research pipeline.

## Embeddings

Use an embedding API initially.

Later, a small local embedding model can be deployed on the VM if desired.

## Deployment

```text
Docker
Docker Compose
Linux VPS
```

---

# 8. Repository structure

```text
literature-agent/
│
├── pyproject.toml
├── uv.lock
├── .env
├── .env.example
├── docker-compose.yml
├── README.md
│
├── src/
│   └── litagent/
│       │
│       ├── config.py
│       │
│       ├── slack/
│       │   ├── app.py
│       │   ├── commands.py
│       │   ├── events.py
│       │   └── views.py
│       │
│       ├── discovery/
│       │   ├── base.py
│       │   ├── arxiv.py
│       │   ├── semantic_scholar.py
│       │   └── openalex.py
│       │
│       ├── ranking/
│       │   ├── embeddings.py
│       │   ├── relevance.py
│       │   └── ranker.py
│       │
│       ├── analysis/
│       │   ├── extract.py
│       │   ├── summarise.py
│       │   └── synthesis.py
│       │
│       ├── memory/
│       │   ├── papers.py
│       │   ├── interests.py
│       │   ├── feedback.py
│       │   └── research_questions.py
│       │
│       ├── jobs/
│       │   ├── discovery.py
│       │   ├── digest.py
│       │   └── maintenance.py
│       │
│       └── db/
│           ├── database.py
│           ├── models.py
│           └── repositories.py
│
└── tests/
    ├── unit/
    └── integration/
```

---

# 9. Research state

The system should maintain explicit research state rather than putting everything into an LLM prompt.

The main entities are:

```text
User
Topic
Paper
PaperEmbedding
PaperSummary
Feedback
ReadingHistory
ResearchQuestion
Claim
Citation
```

---

# 10. Paper database

The canonical paper record should contain:

```text
Paper
-----
id
canonical_id

title
abstract
authors

arxiv_id
doi
semantic_scholar_id
openalex_id

published_at
updated_at

paper_url
pdf_url

source
created_at
```

Multiple external identifiers should map to one canonical paper.

This prevents the same paper from appearing multiple times when discovered through different sources.

---

# 11. Research interests

Topics should be stored explicitly.

Example:

```text
Topic
-----
name:
heterogeneous inference

description:
Systems techniques for executing ML workloads across
heterogeneous accelerators, including scheduling,
disaggregation, runtime adaptation and communication.

weight:
0.9
```

Initial topics can be manually configured.

Later they should be learned from behaviour.

---

# 12. Discovery system

Start with one source:

```text
arXiv
```

Then add:

```text
Semantic Scholar
OpenAlex
```

The discovery interface should be abstract:

```python
class PaperSource(Protocol):

    async def search(
        self,
        query: str,
    ) -> list[Paper]:
        ...
```

Implementations:

```text
ArxivSource
SemanticScholarSource
OpenAlexSource
```

This prevents source-specific logic from contaminating the rest of the application.

---

# 13. Discovery pipeline

Every few hours:

```text
Research topics
      ↓
generate searches
      ↓
query sources
      ↓
normalise metadata
      ↓
deduplicate
      ↓
store new papers
```

The initial system can run every six hours.

There is no need to continuously poll every minute.

---

# 14. Ranking pipeline

The ranking system should have multiple stages.

## Stage 1: cheap filtering

Remove:

- papers already seen;
- duplicates;
- obviously irrelevant categories;
- papers outside the configured publication window.

## Stage 2: embedding retrieval

Represent:

```text
paper = embedding(title + abstract)
```

and:

```text
topic = embedding(topic description)
```

Then calculate semantic similarity.

For multiple topics:

\[
S_{\mathrm{semantic}}(p)
=
\sum_i w_i
\operatorname{cos}(e_p,e_i).
\]

This produces perhaps the top 50 candidates.

## Stage 3: LLM relevance judgement

The LLM evaluates candidates using structured output:

```json
{
  "relevance": 0.91,
  "novelty": 0.72,
  "importance": 0.85,
  "technical_depth": 0.94,
  "topic_matches": [
    "heterogeneous inference",
    "LLM serving"
  ],
  "reason": "..."
}
```

## Stage 4: final ranking

Initially:

\[
S(p)=
w_rR+
w_nN+
w_iI+
w_dD-
w_xX
\]

where:

- \(R\) = relevance;
- \(N\) = novelty;
- \(I\) = importance;
- \(D\) = technical depth;
- \(X\) = redundancy.

The exact weights should be configurable.

---

# 15. Why novelty matters

The objective isn't simply:

> Find the papers most similar to my interests.

That produces an echo chamber.

A better objective is:

> Find papers that are relevant **and add something new to my understanding**.

For example, a paper that is 80% relevant but introduces a completely new approach may be more valuable than a 95%-relevant paper that reproduces a familiar technique.

Therefore the ranking system should explicitly model:

```text
relevance
novelty
importance
technical depth
redundancy
```

---

# 16. Paper analysis

Only the highest-ranked papers should undergo expensive full analysis.

For each selected paper, produce:

```python
class PaperAnalysis(BaseModel):
    problem: str
    core_idea: str
    methodology: str
    main_results: str
    limitations: list[str]
    novelty: str
    related_work: list[str]
    why_relevant: str
```

The resulting analysis should be persisted.

This means the system does not need to repeatedly analyse the same paper.

---

# 17. Personalised summaries

Every paper should produce two levels of understanding.

### Objective

```text
What does the paper claim?
```

### Personalised

```text
Why does this matter to this user?
```

The personalised explanation should use:

- current research topics;
- previously read papers;
- saved papers;
- research questions;
- known preferences;
- previous feedback.

This is one of the most important features of the system.

---

# 18. Slack feedback

Each automated summary should include interactive actions:

```text
👍 Relevant
👎 Not relevant
⭐ Important
🔖 Save
📖 Read
```

The interaction should produce a persistent record:

```text
UserFeedback
------------
user_id
paper_id
feedback_type
timestamp
```

Do not rely on the LLM to infer whether the user liked a paper.

Explicit UI actions are much cleaner labels.

---

# 19. Personalisation

Over time, the system should move from:

```text
manually defined interests
```

towards:

```text
explicit interests
+
positive examples
+
negative examples
+
reading history
+
saved papers
+
feedback
```

The user's interest representation becomes:

```text
InterestProfile
├── topics
├── topic weights
├── positive papers
├── negative papers
├── recent interests
├── embeddings
└── research questions
```

This can eventually support a learned ranking model.

---

# 20. Literature graph

Papers should not be treated as independent documents.

Store relationships:

```text
Paper A
  │
  ├── cites → Paper B
  ├── extends → Paper C
  ├── contradicts → Paper D
  ├── benchmarks → Paper E
  └── related → Paper F
```

Citation relationships can be obtained from bibliographic APIs.

Higher-level semantic relationships can eventually be extracted using an LLM.

A graph database is not required initially.

PostgreSQL tables are sufficient.

---

# 21. Research questions

Add persistent research questions:

```text
ResearchQuestion
----------------
id
question
description
status
created_at
updated_at
```

Example:

```text
How should inference workloads be scheduled across
heterogeneous accelerators when workload characteristics
are uncertain?
```

Every important paper can then be evaluated against active questions:

```text
Does this paper:

- provide evidence?
- challenge an assumption?
- introduce a competing approach?
- identify a limitation?
- suggest a new research direction?
```

This allows the system to evolve from paper recommendation into actual literature review.

---

# 22. Interactive research

Eventually `/research` should operate as a planning agent.

For example:

```text
/research heterogeneous inference for agentic workloads
```

The planner might decide:

```text
1. Search "heterogeneous LLM inference"
2. Search "agentic inference systems"
3. Find highly cited papers
4. Follow citation chains
5. Search papers related to promising results
6. Identify common approaches
7. Identify disagreements
8. Identify open problems
9. Produce synthesis
```

The agent should have a limited tool set:

```text
search_papers
get_paper
get_related_papers
get_citations
get_citing_papers
get_user_interests
get_research_questions
save_research_note
```

Do not initially give the agent unrestricted access to arbitrary tools.

---

# 23. Scheduled jobs

The system should have four main jobs.

## Discovery

Frequency:

```text
Every 6 hours
```

Actions:

```text
query sources
→ deduplicate
→ store papers
→ generate embeddings
```

## Daily digest

Frequency:

```text
Once per day
```

Actions:

```text
rank unseen papers
→ analyse top candidates
→ send Slack digest
```

## Weekly synthesis

Frequency:

```text
Once per week
```

Actions:

```text
papers from last week
→ identify themes
→ identify important developments
→ identify contradictions
→ map to research questions
→ send synthesis
```

## Maintenance

Frequency:

```text
Daily
```

Actions:

```text
update citation information
merge duplicates
update embeddings
update topic associations
update user-interest weights
clean stale jobs
```

---

# 24. Deployment

## Recommended option: Hetzner

For this workload, a small Hetzner Cloud VM is probably the best price/performance option.

The current CAX11 is:

```text
2 vCPU
4 GB RAM
40 GB storage
ARM64
```

and current pricing is around €6/month before VAT depending on location/pricing configuration. Hetzner's current published pricing shows CAX11 at €5.99/month in its June 2026 price-adjustment table, while its current product pages show low-cost CAX11/CX23 configurations around this range.

The x86 CX23 is preferable if you want to avoid ARM compatibility issues.

Recommended deployment:

```text
Hetzner CX23/CAX11
        │
        └── Ubuntu 24.04
                │
                └── Docker Compose
                        │
              ┌─────────┼──────────┐
              │         │          │
          slack-bot   worker    scheduler
              │         │          │
              └─────────┼──────────┘
                        │
                    PostgreSQL
```

For this application, **4 GB RAM is sufficient** because the LLM and embedding workloads are external API calls rather than local inference.

---

# 25. Free option: Oracle Cloud

If zero hosting cost is important, Oracle Cloud's Always Free tier is worth trying.

Oracle currently provides:

```text
Ampere A1
2 OCPUs
12 GB RAM
```

within its Always Free allocation, as well as storage and networking resources.

This is actually more capable than the cheap paid VM described above.

The downsides are:

- ARM64;
- occasional lack of available Always Free capacity;
- more fiddly account/cloud setup;
- Oracle's free-instance eligibility has operational restrictions;
- you need to be careful about accidentally provisioning paid resources.

Oracle explicitly notes that Always Free instances can encounter "out of host capacity" errors, and idle instances can be reclaimed under its stated idle criteria.

For a hobby/research project:

**Oracle Always Free = cheapest.**

**Hetzner = least hassle.**

---

# 26. Google Cloud alternative

Google Cloud also provides an Always Free Compute Engine allowance of:

```text
1 × e2-micro
30 GB standard persistent disk
1 GB outbound traffic/month
```

for eligible users.

However, the e2-micro has only 1 GB RAM.

I would **not** choose it for the complete application.

It is fine for:

```text
Slack bot
+
tiny worker
```

but PostgreSQL + indexing + background jobs will make 1 GB unpleasant.

---

# 27. AWS alternative

AWS Lightsail is another simple option.

Its cheapest Linux plans currently start around $5/month for a small IPv4 instance, although AWS's pricing pages have different pricing depending on IP configuration and plan.

It is therefore viable, but I would choose Hetzner instead for this particular application.

---

# 28. Hosting recommendation

| Provider | Approx. cost | Useful RAM | Recommendation |
|---|---:|---:|---|
| Oracle Always Free | £0 | 12 GB | Best free option |
| Hetzner CAX11 | ~£5–6/mo | 4 GB | **Best overall** |
| Hetzner CX23 | ~£4–6/mo | 4 GB | **Best x86 option** |
| Google e2-micro | £0 | 1 GB | Too constrained |
| AWS Lightsail | ~£4–5/mo | 0.5–1 GB at cheapest tier | Fine, but not first choice |

Prices can change, and VAT/network/IP costs need to be considered when comparing providers.

---

# 29. Docker Compose

The initial deployment should be:

```yaml
services:

  bot:
    build: .
    command: python -m litagent.slack.app

  worker:
    build: .
    command: python -m litagent.jobs.worker

  scheduler:
    build: .
    command: python -m litagent.jobs.scheduler

  postgres:
    image: pgvector/pgvector:pg17
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Redis should only be introduced if the job system eventually needs it.

---

# 30. Security

Secrets should live in environment variables:

```text
SLACK_BOT_TOKEN
SLACK_APP_TOKEN

DATABASE_URL

LLM_API_KEY

SEMANTIC_SCHOLAR_API_KEY
```

Do not commit `.env`.

The server should:

- disable password SSH;
- use SSH keys;
- enable UFW;
- expose only required ports;
- keep PostgreSQL private;
- automatically apply security updates;
- periodically back up PostgreSQL.

Because the Slack bot uses Socket Mode, you don't initially need to expose an application HTTP port to the public internet.

---

# 31. Development milestones

The implementation should proceed in the following order.

## Milestone 1 — Slack skeleton

Build:

```text
Slack app
+
Socket Mode
+
Bolt
+
private channel
+
/papers
```

The command can initially return:

```text
Paper search isn't implemented yet.
```

The purpose is simply to establish the interface.

---

## Milestone 2 — Database

Implement:

```text
PostgreSQL
SQLAlchemy
Alembic
Paper model
Topic model
Feedback model
```

Get persistence working.

---

## Milestone 3 — arXiv ingestion

Implement:

```text
arXiv API
 ↓
normalisation
 ↓
deduplication
 ↓
PostgreSQL
```

At this point you have a paper database.

---

## Milestone 4 — embeddings

Implement:

```text
paper
 ↓
embedding
 ↓
pgvector
```

and:

```text
/papers query
 ↓
embedding
 ↓
nearest papers
```

At this point `/papers` is useful without any LLM.

---

## Milestone 5 — LLM ranking

Add:

```text
top 50 papers
 ↓
LLM relevance judge
 ↓
top 10
```

Use structured output.

---

## Milestone 6 — paper analysis

Implement:

```text
problem
core idea
method
results
limitations
why relevant
```

Persist the analysis.

---

## Milestone 7 — automated digest

Add:

```text
scheduler
 ↓
ranking
 ↓
analysis
 ↓
private Slack channel
```

The agent is now continuously useful.

---

## Milestone 8 — feedback

Add:

```text
👍
👎
⭐
🔖
📖
```

and persist the events.

---

## Milestone 9 — personalisation

Use feedback to modify:

```text
topic weights
paper similarity
positive examples
negative examples
novelty
redundancy
```

---

## Milestone 10 — Semantic Scholar + OpenAlex

Add additional discovery mechanisms.

Use them primarily for:

```text
citation graph
related papers
author discovery
paper recommendations
```

rather than simply duplicating arXiv search.

---

## Milestone 11 — literature graph

Add:

```text
cites
extends
contradicts
related-to
benchmarks
```

relationships.

---

## Milestone 12 — weekly synthesis

Produce:

```text
papers discovered
papers worth reading
emerging themes
important results
contradictions
research gaps
research-question updates
```

---

## Milestone 13 — research agent

Finally implement `/research` as a planning agent capable of:

```text
plan search
→ execute searches
→ inspect papers
→ follow citations
→ compare approaches
→ synthesise findings
```

---

# 32. Final architecture

The final system should have four conceptual layers.

```text
┌─────────────────────────────────────────────┐
│                 INTERFACE                   │
│                                             │
│             Private Slack channel          │
│             /papers /paper /research       │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                 AGENTS                      │
│                                             │
│ Discovery   Ranking   Analysis   Synthesis │
│                         │                   │
│                    Research Planner         │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                 MEMORY                      │
│                                             │
│ Papers       Interests       Feedback       │
│ Embeddings   Citations       Questions      │
│ Summaries    Claims          Reading state  │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                 SOURCES                     │
│                                             │
│ arXiv       Semantic Scholar       OpenAlex│
└─────────────────────────────────────────────┘
```

The important architectural boundary is:

```text
Slack ≠ memory
LLM ≠ database
Agent ≠ scheduler
Discovery ≠ ranking
Ranking ≠ analysis
```

Slack is the **interface**.

PostgreSQL is the **persistent research memory**.

The discovery/ranking/analysis components are **workers**.

The scheduler determines **when work happens**.

The LLM provides **reasoning and synthesis**, rather than being the entire system.

---

# 33. Recommended first implementation

The minimum useful system is surprisingly small:

```text
                     ┌──────────────┐
                     │     Slack    │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │  Bolt bot    │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │ PostgreSQL   │
                     └──────┬───────┘
                            │
                 ┌──────────▼──────────┐
                 │       Worker        │
                 │                     │
                 │ arXiv               │
                 │ embeddings          │
                 │ LLM ranking         │
                 │ LLM summarisation   │
                 └─────────────────────┘
```

Run this on a **Hetzner 2-vCPU/4-GB VM**.

Then add functionality incrementally.

The first real target should therefore be:

```text
Day 1:

Slack App
    ↓
private #literature-euan
    ↓
/papers

Day 2:

PostgreSQL
    ↓
arXiv ingestion

Day 3:

embeddings
    ↓
relevance ranking

Day 4:

LLM summaries
    ↓
automatic Slack messages

Day 5:

👍 👎 ⭐ 🔖
    ↓
persistent feedback
```

At the end of that first week you should already have a **continuously running personal literature feed**, rather than spending weeks building an elaborate agent framework before you have anything useful.