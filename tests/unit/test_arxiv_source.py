"""Unit tests for arXiv Atom feed parsing (no network access)."""

from __future__ import annotations

from litagent.discovery.arxiv import _parse_feed, normalize_arxiv_id

_SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>  We propose the Transformer, a novel architecture ...  \n</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <link href="http://arxiv.org/abs/1706.03762v5" rel="alternate"/>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v5" rel="related"/>
  </entry>
</feed>
"""


def test_parse_feed_extracts_fields() -> None:
    papers = _parse_feed(_SAMPLE_FEED)
    assert len(papers) == 1

    paper = papers[0]
    assert paper.title == "Attention Is All You Need"
    assert paper.arxiv_id == "1706.03762"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper.pdf_url == "http://arxiv.org/pdf/1706.03762v5"
    assert paper.source == "arxiv"
    assert paper.published_at is not None
    assert paper.abstract == "We propose the Transformer, a novel architecture ..."


def test_parse_feed_empty() -> None:
    empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    assert _parse_feed(empty_feed) == []


def test_normalize_arxiv_id_bare() -> None:
    assert normalize_arxiv_id("1706.03762") == "1706.03762"


def test_normalize_arxiv_id_bare_with_version() -> None:
    assert normalize_arxiv_id("1706.03762v5") == "1706.03762"


def test_normalize_arxiv_id_abs_url() -> None:
    assert normalize_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"


def test_normalize_arxiv_id_abs_url_with_version() -> None:
    assert normalize_arxiv_id("https://arxiv.org/abs/1706.03762v5") == "1706.03762"


def test_normalize_arxiv_id_pdf_url() -> None:
    assert normalize_arxiv_id("https://arxiv.org/pdf/1706.03762v5.pdf") == "1706.03762"


def test_normalize_arxiv_id_strips_whitespace() -> None:
    assert normalize_arxiv_id("  1706.03762  ") == "1706.03762"
