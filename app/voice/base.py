from dataclasses import dataclass
from typing import Protocol


class VoiceProviderError(Exception):
    """Failure talking to the voice provider: network, timeout, invalid key, HTTP error..."""


@dataclass(frozen=True)
class VoiceConversation:
    """A conversation the browser can join exactly once."""

    signed_url: str  # credential for the browser; never log it
    conversation_id: str  # known before the conversation starts, so the backend can bind data to it


class VoiceProvider(Protocol):
    """What we need from the voice provider: a short-lived, single-use URL for the browser."""

    async def create_conversation(self) -> VoiceConversation:
        """Return a single-use signed URL for one conversation with the interviewer agent."""
        ...
