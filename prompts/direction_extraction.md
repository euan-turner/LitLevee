# Research Direction Extraction Prompt

A researcher has described a new research direction in their own words.
Turn this into the structured research profile defined below (see
new_design.md section 4).

## Description

{{DESCRIPTION}}

## Task

Produce:

- `id`: a short kebab-case slug derived from the description (e.g.
  "agentic-inference").
- `name`: a short human-readable title.
- `research_question`: one or two sentences framing the open question this
  direction investigates.
- `scope.included`: concrete topics/methods clearly inside this direction.
- `scope.excluded`: neighbouring topics that sound related but should NOT
  be treated as relevant -- be specific about the boundary (e.g. "agent
  planning algorithms without a systems contribution" rather than just
  "agent planning").
- `topics`: a shorter list of the core recurring topics/subtopics used for
  tagging individual papers later.
- `adjacent`: neighbouring research areas worth occasional exposure but not
  core.
- `methods`: specific methods/technologies associated with this direction.
- `priority.core` / `priority.interesting` / `priority.peripheral`: how the
  topics above rank in importance.
- `venues.primary`: the 3-6 venues most associated with this kind of work.

Be specific rather than generic. A vague scope produces a noisy digest.
