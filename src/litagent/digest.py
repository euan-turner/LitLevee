"""Builds the daily Slack digest text (section 23).

Plain `mrkdwn`, not Block Kit -- interactive elements are explicitly V2
(section 24), so there's nothing here but text and a link. Pulls
`Why relevant` / `Core idea` / `Key result` / `Relation to your work`
straight out of the already-persisted `PaperAnalysis`; no LLM call happens
at digest-build time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from litagent.db.models import (
    LandscapeCategory,
    LandscapeEntry,
    Paper,
    PaperDirectionMatch,
    RelevanceCategory,
)

_DIVIDER = "━" * 22

_LANDSCAPE_LABELS = {
    LandscapeCategory.FOUNDATIONS: "FOUNDATIONAL",
    LandscapeCategory.MAJOR_APPROACHES: "MAJOR APPROACH",
    LandscapeCategory.RECENT_WORK: "RECENT WORK",
    LandscapeCategory.ADJACENT: "ADJACENT",
}


def _byline(paper: Paper, institutions: list[str]) -> str:
    parts = []
    if paper.authors:
        parts.append(", ".join(paper.authors[:3]) + (" et al." if len(paper.authors) > 3 else ""))
    if institutions:
        parts.append(institutions[0])
    if paper.venue:
        parts.append(paper.venue)
    elif paper.publication_date:
        parts.append(str(paper.publication_date.date()))
    return " · ".join(parts)


def _paper_block(paper: Paper, match: PaperDirectionMatch, direction_name: str, institutions: list[str]) -> str:
    label = match.relevance_category.value.upper()
    subtopic = f" → {match.subtopics[0]}" if match.subtopics else ""
    lines = [
        f"[{label}] {direction_name}{subtopic}",
        "",
        f"<{paper.url}|{paper.title}>" if paper.url else paper.title,
    ]
    byline = _byline(paper, institutions)
    if byline:
        lines.append(byline)
    lines.append("")

    analysis = match.analysis
    if analysis is not None:
        lines.append(f"Why relevant:\n{analysis.context.why_relevant}")
        if analysis.contributions:
            lines.append(f"\nCore idea:\n{analysis.contributions[0]}")
        if analysis.evaluation.results:
            result = analysis.evaluation.results[0]
            lines.append(f"\nKey result:\n{result.metric}: {result.improvement} ({result.comparison})")
        elif analysis.evaluation.summary:
            lines.append(f"\nKey result:\n{analysis.evaluation.summary}")
    elif match.reason:
        lines.append(f"Why relevant:\n{match.reason}")

    return "\n".join(lines)


def _landscape_block(paper: Paper, entry: LandscapeEntry, direction_name: str, institutions: list[str]) -> str:
    label = _LANDSCAPE_LABELS[entry.category]
    lines = [
        f"[{label}] {direction_name}",
        "",
        f"<{paper.url}|{paper.title}>" if paper.url else paper.title,
    ]
    byline = _byline(paper, institutions)
    if byline:
        lines.append(byline)
    if entry.signal_summary:
        lines.append(f"\nWhy it's here:\n{entry.signal_summary}")
    return "\n".join(lines)


def build_landscape_digest(
    direction_name: str,
    entries: list[tuple[Paper, LandscapeEntry, list[str]]],
) -> str:
    """The one-time literature landscape (section 6), delivered as the first
    part of a direction's first digest -- `entries` is `(paper, landscape
    entry, institutions)`, already in delivery order (see
    `db.repository.undelivered_landscape_entries`)."""
    header = f"Literature Landscape — {direction_name}"
    if not entries:
        return f"{header}\n\nNothing to show yet -- run scripts/run_landscape.py for this direction."

    count = len(entries)
    noun = "paper" if count == 1 else "papers"
    blocks = [f"{header}\n\n{count} {noun} to get you oriented in this field."]
    for paper, entry, institutions in entries:
        blocks.append(_landscape_block(paper, entry, direction_name, institutions))
    return f"\n\n{_DIVIDER}\n\n".join(blocks)


def build_digest(
    direction_name: str,
    entries: list[tuple[Paper, PaperDirectionMatch, list[str]]],
    *,
    as_of: datetime | None = None,
) -> str:
    """`entries` is `(paper, match, institutions)`, already ordered by category/score."""
    as_of = as_of or datetime.now(UTC)
    header = f"Literature Review — {as_of.strftime('%-d %B %Y')}"

    if not entries:
        return f"{header}\n\nNo papers passed the relevance threshold today."

    count = len(entries)
    noun = "paper" if count == 1 else "papers"
    blocks = [f"{header}\n\n{count} {noun} worth reading today."]
    for paper, match, institutions in entries:
        blocks.append(_paper_block(paper, match, direction_name, institutions))
    return f"\n\n{_DIVIDER}\n\n".join(blocks)


def sort_for_digest(
    entries: list[tuple[Paper, PaperDirectionMatch, list[str]]],
) -> list[tuple[Paper, PaperDirectionMatch, list[str]]]:
    """Core before interesting, then by relevance score (section 12: only
    Core and Interesting normally reach the digest -- callers filter that)."""
    order = {RelevanceCategory.CORE: 0, RelevanceCategory.INTERESTING: 1}
    return sorted(
        entries,
        key=lambda e: (order.get(e[1].relevance_category, 2), -(e[1].relevance_score or 0)),
    )
