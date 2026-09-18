"""Abstract discovery interface.

Every paper source (arXiv, Semantic Scholar, OpenAlex, ...) implements
`PaperSource` and returns normalised `DiscoveredPaper` records. This keeps
source-specific parsing/quirks out of the rest of the application -- the
discovery pipeline and the database only ever deal with `DiscoveredPaper`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class DiscoveredPaper(BaseModel):
    title: str
    abstract: str | None = None
    authors: list[str] = []
    # Populated only by sources that report affiliations (OpenAlex); arXiv
    # and Semantic Scholar leave this empty (section 15: incomplete
    # institution metadata should never block a paper from being surfaced).
    institutions: list[str] = []

    arxiv_id: str | None = None
    doi: str | None = None
    semantic_scholar_id: str | None = None
    openalex_id: str | None = None

    published_at: datetime | None = None
    paper_url: str | None = None
    pdf_url: str | None = None

    # Populated by sources that report citation counts (OpenAlex, Semantic
    # Scholar); `None` means "this source doesn't know", which is not the
    # same as zero.
    citation_count: int | None = None

    source: str


class PaperSource(Protocol):
    async def search(
        self, query: str, *, max_results: int = 50, sort_by: str = "relevance"
    ) -> list[DiscoveredPaper]:
        """Search this source for papers matching `query`.

        `sort_by` is one of "relevance" or "recency". The daily monitoring
        pass (new_design.md section 7) wants "recency"; landscape discovery
        (section 6) wants "relevance".
        """
        ...
