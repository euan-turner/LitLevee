"""Unit tests for Semantic Scholar's retry-on-429 handling (no network:
httpx.MockTransport stands in for the API; asyncio.sleep is patched out so
the test doesn't actually wait through the backoff)."""

from __future__ import annotations

import httpx
import pytest

import litagent.discovery.semantic_scholar as s2_module
from litagent.discovery.semantic_scholar import SemanticScholarSource


@pytest.fixture(autouse=True)
def _reset_throttle_state(monkeypatch):
    # The throttle is module-level (shared across instances by design --
    # see the module docstring), so tests must reset it or bleed into
    # each other, and must not actually sleep through real backoff delays.
    monkeypatch.setattr(s2_module, "_last_request_at", 0.0)

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(s2_module.asyncio, "sleep", fake_sleep)
    yield sleeps


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_get_retries_after_429_then_succeeds(_reset_throttle_state) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"message": "Too Many Requests"})
        return httpx.Response(200, json={"data": []})

    source = SemanticScholarSource(client=_client(handler))
    payload = await source._get("/paper/search", {"query": "x"})

    assert payload == {"data": []}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_get_gives_up_after_max_retries(_reset_throttle_state) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too Many Requests"})

    source = SemanticScholarSource(client=_client(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await source._get("/paper/search", {"query": "x"})


@pytest.mark.asyncio
async def test_get_honors_retry_after_header(_reset_throttle_state) -> None:
    sleeps = _reset_throttle_state
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json={"data": []})

    source = SemanticScholarSource(client=_client(handler))
    await source._get("/paper/search", {"query": "x"})

    assert 7.0 in sleeps


@pytest.mark.asyncio
async def test_search_since_returns_empty_on_404(_reset_throttle_state) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    source = SemanticScholarSource(client=_client(handler))
    from datetime import date

    papers = await source.search_since("x", since=date(2026, 1, 1))
    assert papers == []
