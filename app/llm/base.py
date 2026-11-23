from typing import Protocol


class LLMProviderError(Exception):
    """Failure talking to the provider: network, timeout, invalid key, HTTP error..."""


class LLMClient(Protocol):
    """The minimum we need from any LLM provider (DeepSeek, the fake one...)."""

    async def complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
        """Send a system message and a user message and return the response text.

        With `json_mode=True` the provider is asked to reply with JSON.
        """
        ...
