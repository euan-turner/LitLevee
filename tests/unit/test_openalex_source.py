"""Unit tests for OpenAlex parsing (no network)."""

from __future__ import annotations

from litagent.discovery.openalex import _parse_work, _reconstruct_abstract

_WORK = {
    "id": "https://openalex.org/W7162338371",
    "doi": "https://doi.org/10.48550/arxiv.2605.23109",
    "title": "Inductive Deductive Synthesis",
    "publication_date": "2026-05-22",
    "abstract_inverted_index": {"We": [0], "verify": [2], "formally": [1]},
    "cited_by_count": 12,
    "authorships": [
        {
            "author": {"display_name": "Shubham Agarwal"},
            "institutions": [{"display_name": "UC Berkeley"}],
        },
        {"author": {}, "institutions": []},
    ],
    "primary_location": {"landing_page_url": "https://doi.org/10.48550/arxiv.2605.23109"},
}


def test_parse_work_extracts_fields() -> None:
    paper = _parse_work(_WORK)
    assert paper is not None
    assert paper.title == "Inductive Deductive Synthesis"
    assert paper.doi == "10.48550/arxiv.2605.23109"
    assert paper.openalex_id == "W7162338371"
    assert paper.authors == ["Shubham Agarwal"]
    assert paper.institutions == ["UC Berkeley"]
    assert paper.citation_count == 12
    assert paper.source == "openalex"
    assert paper.published_at is not None and paper.published_at.year == 2026


def test_parse_work_derives_arxiv_id_from_doi() -> None:
    # This is what lets an OpenAlex result dedup against the same paper
    # already stored from arXiv.
    assert _parse_work(_WORK).arxiv_id == "2605.23109"


def test_parse_work_without_arxiv_doi_has_no_arxiv_id() -> None:
    paper = _parse_work({**_WORK, "doi": "https://doi.org/10.1145/3786335.3813221"})
    assert paper.arxiv_id is None
    assert paper.doi == "10.1145/3786335.3813221"


def test_parse_work_without_title_is_skipped() -> None:
    assert _parse_work({"id": "https://openalex.org/W1"}) is None


def test_parse_work_without_institutions_is_empty() -> None:
    paper = _parse_work({**_WORK, "authorships": [{"author": {"display_name": "Solo Author"}}]})
    assert paper.institutions == []


def test_reconstruct_abstract_orders_words_by_position() -> None:
    assert _reconstruct_abstract({"We": [0], "verify": [2], "formally": [1]}) == "We formally verify"
    assert _reconstruct_abstract({"a": [0, 2], "b": [1]}) == "a b a"
    assert _reconstruct_abstract(None) is None
