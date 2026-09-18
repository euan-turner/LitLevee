"""arXiv paper source.

Uses the public arXiv API (https://info.arxiv.org/help/api/index.html),
which returns an Atom feed. No API key is required.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from xml.etree import ElementTree

import httpx

from litagent.discovery.base import DiscoveredPaper

logger = logging.getLogger(__name__)

_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_ID_RE = re.compile(r"abs/(?P<id>[\w.\-/]+?)(v\d+)?$")
_ARXIV_URL_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>[\w.\-/]+?)(?:v\d+)?(?:\.pdf)?/?$", re.IGNORECASE
)
_TRAILING_VERSION_RE = re.compile(r"v\d+$")


def normalize_arxiv_id(text: str) -> str:
    """Extract a bare arXiv ID from a URL, or strip a version suffix from a bare ID.

    Accepts `1706.03762`, `1706.03762v5`, `https://arxiv.org/abs/1706.03762`,
    and `https://arxiv.org/pdf/1706.03762v5.pdf` -- users commonly paste any
    of these when asking about a specific paper.
    """
    text = text.strip()
    match = _ARXIV_URL_ID_RE.search(text)
    if match:
        return match.group("id")
    return _TRAILING_VERSION_RE.sub("", text)


class ArxivSource:
    """`PaperSource` implementation backed by the arXiv API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def search(
        self, query: str, *, max_results: int = 50, sort_by: str = "relevance"
    ) -> list[DiscoveredPaper]:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        arxiv_sort = "submittedDate" if sort_by == "recency" else "relevance"
        try:
            response = await client.get(
                _ARXIV_API_URL,
                params={
                    "search_query": f'all:"{query}"',
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": arxiv_sort,
                    "sortOrder": "descending",
                },
            )
            response.raise_for_status()
            return _parse_feed(response.text)
        finally:
            if owns_client:
                await client.aclose()

    async def search_by_author(
        self, author_name: str, *, max_results: int = 25
    ) -> list[DiscoveredPaper]:
        """Most recent papers with `author_name` in the author list.

        arXiv has no author IDs, only name matching, so this is
        deliberately name-based and can pick up namesakes -- the caller
        (`jobs/discovery.py`'s author scan) pairs it with OpenAlex's
        disambiguated author ID, and uses arXiv purely for freshness:
        preprints appear here the day they're submitted, well before
        OpenAlex indexes them.
        """
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        try:
            response = await client.get(
                _ARXIV_API_URL,
                params={
                    "search_query": f'au:"{author_name}"',
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            response.raise_for_status()
            return _parse_feed(response.text)
        finally:
            if owns_client:
                await client.aclose()

    async def get_by_id(self, arxiv_id: str) -> DiscoveredPaper | None:
        """Fetch a single paper by its arXiv ID, e.g. `2405.12345`."""
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        try:
            response = await client.get(_ARXIV_API_URL, params={"id_list": arxiv_id})
            response.raise_for_status()
            papers = _parse_feed(response.text)
            return papers[0] if papers else None
        finally:
            if owns_client:
                await client.aclose()


def _parse_feed(xml_text: str) -> list[DiscoveredPaper]:
    root = ElementTree.fromstring(xml_text)
    papers = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        paper = _parse_entry(entry)
        if paper is not None:
            papers.append(paper)
    return papers


def _parse_entry(entry: ElementTree.Element) -> DiscoveredPaper | None:
    entry_id = _text(entry, "id")
    if not entry_id:
        return None

    match = _ARXIV_ID_RE.search(entry_id)
    arxiv_id = match.group("id") if match else None

    title = _text(entry, "title")
    if not title:
        return None

    authors = [
        name.text.strip()
        for author in entry.findall(f"{_ATOM_NS}author")
        if (name := author.find(f"{_ATOM_NS}name")) is not None and name.text
    ]

    pdf_url = None
    for link in entry.findall(f"{_ATOM_NS}link"):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")

    return DiscoveredPaper(
        title=" ".join(title.split()),
        abstract=_clean(_text(entry, "summary")),
        authors=authors,
        arxiv_id=arxiv_id,
        published_at=_parse_datetime(_text(entry, "published")),
        paper_url=entry_id,
        pdf_url=pdf_url,
        source="arxiv",
    )


def _text(entry: ElementTree.Element, tag: str) -> str | None:
    element = entry.find(f"{_ATOM_NS}{tag}")
    return element.text if element is not None else None


def _clean(text: str | None) -> str | None:
    return " ".join(text.split()) if text else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Could not parse arXiv published date: %r", value)
        return None
