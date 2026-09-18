"""PDF text extraction for the small set of papers that reach analysis.

Section 36 excludes "automatic PDF downloading for every candidate" and a
full OCR pipeline -- but the analysed set is only ~5-15 papers/day
(section 28), not every candidate, so downloading and extracting text for
*those* is in scope ("available full text where practical", section 14).
Extraction failures fall back to abstract-only analysis rather than
failing the paper (section 29: per-paper failure isolation).
"""

from __future__ import annotations

import io
import logging

import httpx
from pypdf import PdfReader

from litagent.config import settings

logger = logging.getLogger(__name__)


async def fetch_pdf_text(pdf_url: str | None) -> str | None:
    """Download and extract text from `pdf_url`, capped to `max_pdf_text_chars`.

    Returns `None` (never raises) if there's no URL, the download fails, or
    the PDF can't be parsed -- callers fall back to abstract-only text.
    """
    if not pdf_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(pdf_url, follow_redirects=True)
            response.raise_for_status()
        reader = PdfReader(io.BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        text = text.strip()
        if not text:
            return None
        return text[: settings.max_pdf_text_chars]
    except Exception:
        logger.warning("Could not extract PDF text from %s", pdf_url, exc_info=True)
        return None
