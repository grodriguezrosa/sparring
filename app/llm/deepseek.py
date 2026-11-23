from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from app.llm.base import ChatMessage, LLMProviderError

SSE_DATA = "data:"
SSE_DONE = "[DONE]"


# We only model the part of the DeepSeek response that we use.
class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message


class _ChatResponse(BaseModel):
    choices: list[_Choice]


# Streaming chunks: same idea, but each one carries a `delta` (a piece of the reply).
# Fields we do not model, such as `reasoning_content` or `usage`, are ignored.
class _Delta(BaseModel):
    content: str | None = None


class _StreamChoice(BaseModel):
    delta: _Delta


class _ChatChunk(BaseModel):
    choices: list[_StreamChoice] = []


class DeepSeekLLM:
    """DeepSeek client (OpenAI-compatible API: POST /chat/completions)."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport  # tests only: lets us fake the server without network

    async def complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post("/chat/completions", json=body, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise LLMProviderError(
                f"DeepSeek returned HTTP error {error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise LLMProviderError(f"Could not reach DeepSeek ({type(error).__name__})") from error

        try:
            data = _ChatResponse.model_validate_json(response.content)
        except ValidationError as error:
            raise LLMProviderError(
                "DeepSeek returned a response with an unexpected format"
            ) from error

        if not data.choices:
            raise LLMProviderError("DeepSeek returned a response without choices")
        return data.choices[0].message.content or ""

    async def stream(self, *, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

        try:
            async with (
                httpx.AsyncClient(
                    base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
                ) as client,
                client.stream("POST", "/chat/completions", json=body, headers=headers) as response,
            ):
                if response.is_error:
                    raise LLMProviderError(f"DeepSeek returned HTTP error {response.status_code}")
                async for line in response.aiter_lines():
                    # SSE: `data: {json}` lines; blank lines and `: keep-alive` comments are noise.
                    if not line.startswith(SSE_DATA):
                        continue
                    payload = line.removeprefix(SSE_DATA).strip()
                    if payload == SSE_DONE:
                        return
                    text = _chunk_text(payload)
                    if text:
                        yield text
        except httpx.HTTPError as error:
            raise LLMProviderError(f"Could not reach DeepSeek ({type(error).__name__})") from error


def _chunk_text(payload: str) -> str:
    """The reply text carried by one streaming chunk ("" for role-only or usage chunks)."""
    try:
        chunk = _ChatChunk.model_validate_json(payload)
    except ValidationError as error:
        raise LLMProviderError("DeepSeek sent a stream chunk with an unexpected format") from error
    if not chunk.choices:
        return ""
    return chunk.choices[0].delta.content or ""
