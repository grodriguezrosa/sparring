from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


class LLMProviderError(Exception):
    """Failure talking to the provider: network, timeout, invalid key, HTTP error..."""


@dataclass(frozen=True)
class ChatMessage:
    """One message of a multi-turn conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    """The minimum we need from any LLM provider (DeepSeek, the fake one...)."""

    async def complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
        """Send a system message and a user message and return the response text.

        With `json_mode=True` the provider is asked to reply with JSON.
        """
        ...

    def stream(
        self, *, messages: Sequence[ChatMessage], reasoning: bool = False
    ) -> AsyncIterator[str]:
        """Send a whole conversation and yield the reply text as it is generated.

        Used where latency matters (the voice interviewer speaks while text arrives), so
        the model's step-by-step reasoning is off unless `reasoning=True`.
        Raises LLMProviderError if the provider fails, before or during the stream.
        """
        ...
