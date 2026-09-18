"""Semantic Scholar paper source.

Uses the public Semantic Scholar Graph API
(https://api.semanticscholar.org/graph/v1). Works without a key (shared,
very low rate-limit pool); `settings.semantic_scholar_api_key`, if set, is
sent as `x-api-key`.

**Rate limiting, verified against the live API**: even with a freshly
issued key, back-to-back requests hit `429` immediately, and repeated `429`
responses keep coming for tens of seconds afterwards -- this looks like a
per-process token-bucket that a burst empties quickly and refills slowly,
not a simple "1 request/second" cap. Since `pipeline.discover_for_direction`
queries once per topic (see `directions.search_queries`), a multi-topic
direction fires several S2 requests in a row, so both throttling *and*
retry-with-backoff are needed here rather than in the caller -- the caller
only sees "this provider failed" and moves on (section 29), which would
otherwise silently starve S2 out of every run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

from litagent.config import settings
from litagent.discovery.base import DiscoveredPaper

logger = logging.getLogger(__name__)

_API_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,abstract,authors,venue,year,publicationDate,externalIds,citationCount,openAccessPdf"

# Module-level (not per-`SemanticScholarSource`-instance) because
# `pipeline.discover_for_direction` constructs a fresh source per query --
# the throttle has to be shared across those to mean anything.
_MIN_REQUEST_INTERVAL_SECONDS = 3.0
_MAX_RETRIES = 4
_RETRY_BACKOFF_SECONDS = 5.0

_last_request_at = 0.0
_throttle_lock = asyncio.Lock()


async def _throttle() -> None:
    global _last_request_at
    async with _throttle_lock:
        wait = _last_request_at + _MIN_REQUEST_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


class SemanticScholarSource:
    """`PaperSource` implementation backed by the Semantic Scholar Graph API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        headers = (
            {"x-api-key": settings.semantic_scholar_api_key} if settings.semantic_scholar_api_key else {}
        )
        try:
            for attempt in range(_MAX_RETRIES + 1):
                await _throttle()
                response = await client.get(f"{_API_URL}{path}", params=params, headers=headers)
                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    if attempt == _MAX_RETRIES:
                        logger.warning(
                            "Semantic Scholar rate-limited %s after %d attempts -- giving up for this query",
                            path,
                            attempt + 1,
                        )
                        response.raise_for_status()
                    retry_after = _retry_after_seconds(response) or (
                        _RETRY_BACKOFF_SECONDS * (attempt + 1)
                    )
                    logger.info(
                        "Semantic Scholar rate-limited %s (attempt %d/%d); waiting %.1fs",
                        path,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            return None  # unreachable (loop always returns or raises)
        finally:
            if owns_client:
                await client.aclose()

    async def search(
        self, query: str, *, max_results: int = 50, sort_by: str = "relevance"
    ) -> list[DiscoveredPaper]:
        payload = await self._get(
            "/paper/search",
            {"query": query, "fields": _FIELDS, "limit": min(max_results, 100)},
        )
        if not payload:
            return []
        papers = [_parse_paper(result) for result in payload.get("data", [])]
        papers = [p for p in papers if p is not None]
        if sort_by == "recency":
            papers.sort(key=lambda p: p.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return papers[:max_results]

    async def search_since(
        self, query: str, *, since: date, max_results: int = 100
    ) -> list[DiscoveredPaper]:
        """Recent matches for `query`, for the daily monitoring pass.

        The Graph API's bulk search endpoint supports a `publicationDateOrYear`
        range filter, which is used here instead of client-side filtering so
        the API does the trimming.
        """
        payload = await self._get(
            "/paper/search/bulk",
            {
                "query": query,
                "fields": _FIELDS,
                "publicationDateOrYear": f"{since.isoformat()}:",
                "sort": "publicationDate:desc",
            },
        )
        if not payload:
            return []
        papers = [_parse_paper(result) for result in payload.get("data", [])]
        return [p for p in papers if p is not None][:max_results]


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_paper(payload: dict[str, Any]) -> DiscoveredPaper | None:
    title = payload.get("title")
    if not title:
        return None
    external_ids = payload.get("externalIds") or {}
    open_access = payload.get("openAccessPdf") or {}
    return DiscoveredPaper(
        title=" ".join(title.split()),
        abstract=payload.get("abstract"),
        authors=[a["name"] for a in payload.get("authors") or [] if a.get("name")],
        arxiv_id=external_ids.get("ArXiv"),
        doi=external_ids.get("DOI"),
        semantic_scholar_id=payload.get("paperId"),
        published_at=_parse_date(payload.get("publicationDate"), payload.get("year")),
        paper_url=f"https://www.semanticscholar.org/paper/{payload['paperId']}"
        if payload.get("paperId")
        else None,
        pdf_url=open_access.get("url"),
        citation_count=payload.get("citationCount"),
        source="semantic_scholar",
    )


def _parse_date(publication_date: str | None, year: int | None) -> datetime | None:
    if publication_date:
        try:
            return datetime.fromisoformat(publication_date).replace(tzinfo=UTC)
        except ValueError:
            logger.warning("Could not parse Semantic Scholar publicationDate: %r", publication_date)
    if year:
        return datetime(year, 1, 1, tzinfo=UTC)
    return None
