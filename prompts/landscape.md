# Landscape Categorization Prompt

You are helping a researcher understand the literature landscape around
their research direction, for a one-time "teach me this field" discovery
pass (as opposed to daily monitoring of new work).

Research direction: {{DIRECTION_NAME}}
Research question: {{RESEARCH_QUESTION}}
Category being populated: {{CATEGORY}}

Candidate paper:
Title: {{TITLE}}
Year: {{YEAR}}
Citation count: {{CITATION_COUNT}}
Abstract: {{ABSTRACT}}

Mark the paper off-topic if it only matches by coincidence of wording
rather than genuinely belonging in this category for this research
direction. Otherwise, write one concise sentence (at most 30 words)
summarising what this paper contributes and why it belongs in this
category -- name the specific approach/system/finding, don't restate the
title.
