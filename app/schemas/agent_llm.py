from typing import Self

from pydantic import BaseModel, model_validator

# A 35-minute interview transcript is far below this; it only stops absurd payloads.
MAX_CONVERSATION_CHARS = 200_000


class IncomingMessage(BaseModel):
    """One message as ElevenLabs sends it (OpenAI Chat Completions format)."""

    role: str  # system, user, assistant, and possibly tool: we keep only what we use
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    """The subset of an OpenAI Chat Completions request that we read. Extra fields
    (model, temperature, max_tokens, stream_options...) are accepted and ignored."""

    messages: list[IncomingMessage]
    model: str = "sparring-interviewer"

    @model_validator(mode="after")
    def conversation_is_not_too_large(self) -> Self:
        total = sum(len(message.content or "") for message in self.messages)
        if total > MAX_CONVERSATION_CHARS:
            raise ValueError(f"conversation is too large (max {MAX_CONVERSATION_CHARS} chars)")
        return self
