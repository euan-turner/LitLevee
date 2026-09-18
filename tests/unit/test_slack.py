"""Unit tests for Slack posting (mocked client, section 31)."""

from __future__ import annotations

import pytest
from slack_sdk.errors import SlackApiError

from litagent.slack import post_digest


class _FakeSlackClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def chat_postMessage(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise SlackApiError("boom", response={"error": "boom"})


@pytest.mark.asyncio
async def test_post_digest_sends_expected_payload() -> None:
    client = _FakeSlackClient()
    ok = await post_digest("hello", client=client)
    assert ok is True
    assert client.calls[0]["text"] == "hello"
    assert client.calls[0]["unfurl_links"] is False
    assert client.calls[0]["unfurl_media"] is False


@pytest.mark.asyncio
async def test_post_digest_returns_false_on_failure() -> None:
    client = _FakeSlackClient(fail=True)
    ok = await post_digest("hello", client=client)
    assert ok is False
