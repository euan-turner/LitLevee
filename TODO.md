# TODO

Tracking against `new_design.md` section 37's V1 milestones. The redesign
(see `CLAUDE.md`) implemented milestones 1-7 directly; what's left:

- [ ] Milestone 8 — Evaluation: run the system for several days against
      real directions and inspect false positives/negatives, analysis
      quality, duplicate handling, digest usefulness, API/LLM costs (section
      37). Only after this should interactive Slack functionality (V2,
      section 24) be built.
- [ ] One-time `state` branch bootstrap on GitHub (see README.md) and the
      GitHub Actions secrets configured on the real repo.
- [ ] Tune funnel thresholds (`.env`'s `LEXICAL_CANDIDATE_LIMIT` /
      `EMBEDDING_CANDIDATE_LIMIT` / `LLM_CLASSIFY_LIMIT`) against the
      section-28 target flow once real discovery volume is known.
- [ ] Author affiliations: verify OpenAlex's per-authorship institution
      data is populated/accurate enough in practice for the digest byline.
- [ ] Add more research directions beyond the seeded `mlsys-llm-serving`
      example (e.g. heterogeneous inference, agentic scheduling) via
      `scripts/create_direction.py`.
