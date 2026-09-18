# Paper Analysis Prompt

You are analysing a research paper for a technical ML systems / computer
architecture researcher.

The reader is expected to read the original paper if the overview makes it
interesting. Your job is therefore to provide a concise, technically precise
overview that helps them decide whether to read it and quickly understand its
research logic.

Do NOT simply paraphrase the abstract.

## Research direction

The following research profile describes the user's current interests:

{{RESEARCH_PROFILE}}

## Paper

Title:
{{TITLE}}

Authors:
{{AUTHORS}}

Metadata:
{{METADATA}}

Paper text:
{{PAPER_TEXT}}

## Required output

Return valid JSON matching the supplied `paper_analysis` schema.

### 1. Objectives

List each genuinely distinct research objective.

An objective describes what the authors are trying to achieve, not a generic
activity such as "evaluate the system" or "build a prototype".

### 2. Challenges

List the concrete technical challenges that make the objectives difficult.

Explain why existing approaches are insufficient where the paper establishes
this.

### 3. Contributions

List the actual technical contributions of the paper.

Distinguish conceptual/system contributions from implementation details. Do not
turn every engineering detail into a separate contribution.

### 4. Evaluation

Identify:

- the principal baselines;
- hardware and software environment;
- models and workloads;
- important evaluation metrics;
- quantitative improvements over the relevant baselines.

Use concrete numbers wherever the paper provides them.

The `results` list should contain the most informative quantitative comparisons,
not every result in the paper.

If the paper does not specify a requested detail in the available text, say
"Not specified in the available paper text." Do not invent information.

## Context

`why_relevant` must explain why this paper matters specifically to the
research direction above, rather than giving a generic summary.

Assign one or more concrete subtopics from the research profile where possible.

## Style constraints

- Be concise.
- Prefer technically dense sentences.
- Avoid generic introductory prose.
- Do not repeat the title or abstract unnecessarily.
- Preserve important systems terminology.
- Do not overstate claims.
- Attribute claims to the paper.
- Do not infer experimental results that are not reported.
- The complete rendered analysis should be approximately two conventional
  paragraphs of information, although it is divided into the four required
  sections.
