from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

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
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._timeout_s = timeout_s
        self._transport = transport  # tests only: lets us fake the server without network
        # Shared connection pool (one per app): reusing an open connection saves the TLS
        # handshake on every call. Without it, each call opens and closes its own client.
        self._http_client = http_client

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._http_client is not None:
            yield self._http_client  # not ours to close: the app closes it on shutdown
            return
        async with httpx.AsyncClient(transport=self._transport) as client:
            yield client

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
            async with self._client() as client:
                response = await client.post(
                    self._url, json=body, headers=headers, timeout=self._timeout_s
                )
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

    async def stream(
        self, *, messages: Sequence[ChatMessage], reasoning: bool = False
    ) -> AsyncIterator[str]:
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            # deepseek-flash thinks by default; for live turns that only adds latency.
            "thinking": {"type": "enabled" if reasoning else "disabled"},
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

        try:
            async with (
                self._client() as client,
                client.stream(
                    "POST", self._url, json=body, headers=headers, timeout=self._timeout_s
                ) as response,
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
