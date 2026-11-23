import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from app.llm.base import LLMProviderError


# We only model the part of the DeepSeek response that we use.
class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message


class _ChatResponse(BaseModel):
    choices: list[_Choice]


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
