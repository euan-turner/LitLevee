"""Slack posting -- `chat:write` only (section 22).

No Socket Mode, no slash commands, no interactive actions: this codebase's
Slack footprint is a single `chat.postMessage` call per run. Interactive
functionality is explicitly V2 (section 24), gated on a manual evaluation
period (section 37 milestone 8) that hasn't happened yet.
"""

from __future__ import annotations

import logging

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from litagent.config import settings

logger = logging.getLogger(__name__)


async def post_digest(text: str, *, client: AsyncWebClient | None = None) -> bool:
    """Post `text` to the configured digest channel. Returns whether it succeeded.

    Never raises (section 29: "Slack posting failure should be recorded and
    retried" -- the caller records the outcome on the `runs` row rather than
    the whole pipeline failing).
    """
    client = client or AsyncWebClient(token=settings.slack_bot_token)
    try:
        await client.chat_postMessage(
            channel=settings.slack_channel_id,
            text=text,
            unfurl_links=False,
            unfurl_media=False,
        )
        return True
    except SlackApiError:
        logger.exception("Failed to post digest to Slack")
        return False
