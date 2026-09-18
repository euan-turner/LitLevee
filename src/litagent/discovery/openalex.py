"""OpenAlex paper source.

OpenAlex (https://openalex.org) is free, keyless, and -- unlike arXiv --
reports citation counts and per-authorship institution affiliations, which
is what makes it the backbone of both the relevance funnel's "venue/citation"
signals and the one-time landscape discovery workflow (`landscape.py`,
new_design.md section 6).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, time
from typing import Any

import httpx

from litagent.config import settings
from litagent.discovery.base import DiscoveredPaper

logger = logging.getLogger(__name__)

_OPENALEX_API_URL = "https://api.openalex.org"
_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(?P<id>[\w.\-/]+)$", re.IGNORECASE)


def _sanitize_filter_value(query: str) -> str:
    """Strip characters that are syntactically meaningful in an OpenAlex
    `filter=` expression (`,` separates filters, `|` separates an OR-list
    within one) but might appear in a research direction's free text --
    an unescaped comma otherwise gets the whole request rejected with a
    400 ("A filter value contains an unescaped comma")."""
    return query.replace(",", " ").replace("|", " ")


class OpenAlexSource:
    """`PaperSource` implementation backed by the OpenAlex REST API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        # The `mailto` polite-pool parameter is deprecated; an API key gets
        # higher rate limits instead (https://openalex.org/).
        if settings.openalex_api_key:
            params = {**params, "api_key": settings.openalex_api_key}
        try:
            response = await client.get(f"{_OPENALEX_API_URL}{path}", params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        finally:
            if owns_client:
                await client.aclose()

    async def search(
        self, query: str, *, max_results: int = 50, sort_by: str = "relevance"
    ) -> list[DiscoveredPaper]:
        return await self.search_works(query, limit=max_results, sort_by=sort_by)

    async def search_works(
        self, query: str, *, limit: int = 100, sort_by: str = "relevance"
    ) -> list[DiscoveredPaper]:
        """Papers whose title or abstract matches `query`.

        Uses OpenAlex's `title_and_abstract.search` filter rather than its
        general `search` parameter: the latter matches over full text and
        metadata, so a query like "speculative decoding" pulls in anything
        mentioning either word (verified: it returned a 1996
        superscalar-processor paper and a cancer-therapy paper in the top
        results). Downstream relevance filtering still has to narrow this.

        `title_and_abstract.search` itself does a stemmed **AND** match of
        every word in `query` -- not a phrase, not an OR (verified: a
        13-word query built by concatenating several topics returned zero
        results). Callers must pass one coherent phrase/topic at a time,
        not several topics joined together -- see `directions.search_queries`.
        """
        params: dict[str, Any] = {
            "filter": f"title_and_abstract.search:{_sanitize_filter_value(query)}",
            "per-page": min(limit, 200),
        }
        if sort_by == "recency":
            params["sort"] = "publication_date:desc"
        payload = await self._get("/works", params)
        if not payload:
            return []
        papers = [_parse_work(result) for result in payload.get("results", [])]
        return [p for p in papers if p is not None][:limit]

    async def works_published_since(
        self, query: str, *, since: date, limit: int = 200
    ) -> list[DiscoveredPaper]:
        """Recent works matching `query`, for the daily monitoring pass.

        Same single-phrase-at-a-time caveat as `search_works`.
        """
        payload = await self._get(
            "/works",
            {
                "filter": f"title_and_abstract.search:{_sanitize_filter_value(query)},"
                f"from_publication_date:{since.isoformat()}",
                "per-page": min(limit, 200),
                "sort": "publication_date:desc",
            },
        )
        if not payload:
            return []
        papers = [_parse_work(result) for result in payload.get("results", [])]
        return [p for p in papers if p is not None][:limit]


def _parse_work(payload: dict[str, Any]) -> DiscoveredPaper | None:
    title = payload.get("title") or payload.get("display_name")
    if not title:
        return None

    doi = _bare_doi(payload.get("doi"))
    location = payload.get("primary_location") or {}
    authorships = payload.get("authorships", [])

    return DiscoveredPaper(
        title=" ".join(title.split()),
        abstract=_reconstruct_abstract(payload.get("abstract_inverted_index")),
        authors=[
            authorship["author"]["display_name"]
            for authorship in authorships
            if authorship.get("author", {}).get("display_name")
        ],
        institutions=_institutions(authorships),
        # arXiv preprints are indexed with a `10.48550/arXiv.<id>` DOI, so
        # pulling the arXiv ID out of it lets OpenAlex results deduplicate
        # against papers already found via `ArxivSource`.
        arxiv_id=_arxiv_id_from_doi(doi),
        doi=doi,
        openalex_id=_bare_id(payload.get("id", "")) or None,
        published_at=_parse_date(payload.get("publication_date")),
        citation_count=payload.get("cited_by_count"),
        paper_url=location.get("landing_page_url") or payload.get("id"),
        pdf_url=location.get("pdf_url"),
        source="openalex",
    )


def _institutions(authorships: list[dict[str, Any]]) -> list[str]:
    """Distinct institution names across all authors (section 15's per-paper list)."""
    seen: dict[str, None] = {}
    for authorship in authorships:
        for institution in authorship.get("institutions", []):
            name = institution.get("display_name")
            if name:
                seen.setdefault(name, None)
    return list(seen)


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Rebuild an abstract from OpenAlex's inverted index representation.

    OpenAlex stores abstracts as `{word: [positions]}` (for licensing
    reasons) rather than as plain text, so it has to be reassembled.
    """
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = [
        (position, word) for word, occurrences in inverted_index.items() for position in occurrences
    ]
    positions.sort()
    return " ".join(word for _, word in positions) or None


def _bare_id(url: str) -> str:
    return url.rsplit("/", 1)[-1] if url else ""


def _bare_doi(url: str | None) -> str | None:
    if not url:
        return None
    return url.removeprefix("https://doi.org/")


def _arxiv_id_from_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    match = _ARXIV_DOI_RE.search(doi)
    return match.group("id") if match else None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
    except ValueError:
        logger.warning("Could not parse OpenAlex publication date: %r", value)
        return None
