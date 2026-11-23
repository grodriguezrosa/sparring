from typing import Protocol


class VoiceProviderError(Exception):
    """Failure talking to the voice provider: network, timeout, invalid key, HTTP error..."""


class VoiceProvider(Protocol):
    """What we need from the voice provider: a short-lived URL the browser can connect to."""

    async def create_signed_url(self) -> str:
        """Return a signed URL to start one conversation with the interviewer agent."""
        ...
