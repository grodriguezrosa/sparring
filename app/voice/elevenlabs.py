from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from app.voice.base import VoiceConversation, VoiceProviderError


class _SignedUrlResponse(BaseModel):
    signed_url: str = Field(pattern=r"^wss://")


class _ErrorDetail(BaseModel):
    message: str


class _ErrorResponse(BaseModel):
    detail: _ErrorDetail


def _error_message(response: httpx.Response) -> str:
    """ElevenLabs explains errors in detail.message (e.g. a missing key permission)."""
    try:
        return _ErrorResponse.model_validate_json(response.content).detail.message
    except ValidationError:
        return "no details"


class ElevenLabsVoice:
    """ElevenLabs Agents client. Only requests signed URLs for an agent with auth enabled."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        agent_id: str,
        base_url: str,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._agent_id = agent_id
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._transport = transport  # tests only: lets us fake the server without network

    async def create_conversation(self) -> VoiceConversation:
        headers = {"xi-api-key": self._api_key.get_secret_value()}
        # With include_conversation_id the URL carries the conversation id and is single-use.
        # A plain signed URL can open any number of conversations during its 15 minutes.
        params = {"agent_id": self._agent_id, "include_conversation_id": "true"}

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.get(
                    "/v1/convai/conversation/get-signed-url", params=params, headers=headers
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            reason = _error_message(error.response)
            raise VoiceProviderError(
                f"ElevenLabs returned HTTP error {status}: {reason}"
            ) from error
        except httpx.HTTPError as error:
            raise VoiceProviderError(
                f"Could not reach ElevenLabs ({type(error).__name__})"
            ) from error

        try:
            data = _SignedUrlResponse.model_validate_json(response.content)
        except ValidationError as error:
            raise VoiceProviderError(
                "ElevenLabs returned a response with an unexpected format"
            ) from error

        conversation_ids = parse_qs(urlparse(data.signed_url).query).get("conversation_id", [])
        if len(conversation_ids) != 1 or not conversation_ids[0]:
            # Without it the URL would be reusable: refuse rather than hand it out.
            raise VoiceProviderError("ElevenLabs returned a signed URL without a conversation_id")
        return VoiceConversation(signed_url=data.signed_url, conversation_id=conversation_ids[0])
