"""Unit tests for Semantic Scholar response parsing (no network)."""

from __future__ import annotations

from litagent.discovery.semantic_scholar import _parse_paper

_PAPER = {
    "paperId": "649def34f8be52c8b66281af98ae884c09aef38",
    "title": "Construction of the Literature Graph in Semantic Scholar",
    "abstract": "We describe a deployed scalable system...",
    "venue": "NAACL",
    "year": 2018,
    "publicationDate": "2018-05-01",
    "externalIds": {"DOI": "10.18653/v1/N18-3011", "ArXiv": "1805.02262"},
    "citationCount": 300,
    "authors": [{"authorId": "1", "name": "Waleed Ammar"}, {"authorId": "2", "name": "Dirk Groeneveld"}],
    "openAccessPdf": {"url": "https://arxiv.org/pdf/1805.02262"},
}


def test_parse_paper_extracts_fields() -> None:
    paper = _parse_paper(_PAPER)
    assert paper is not None
    assert paper.title == "Construction of the Literature Graph in Semantic Scholar"
    assert paper.doi == "10.18653/v1/N18-3011"
    assert paper.arxiv_id == "1805.02262"
    assert paper.semantic_scholar_id == "649def34f8be52c8b66281af98ae884c09aef38"
    assert paper.authors == ["Waleed Ammar", "Dirk Groeneveld"]
    assert paper.citation_count == 300
    assert paper.source == "semantic_scholar"
    assert paper.published_at is not None and paper.published_at.year == 2018


def test_parse_paper_falls_back_to_year_only() -> None:
    paper = _parse_paper({**_PAPER, "publicationDate": None})
    assert paper.published_at is not None
    assert paper.published_at.year == 2018


def test_parse_paper_without_title_is_skipped() -> None:
    assert _parse_paper({"paperId": "x"}) is None
