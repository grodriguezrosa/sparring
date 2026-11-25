import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_conversation_store, get_voice_provider
from app.main import app
from app.schemas.interview_plan import MAX_PLAN_CHARS
from app.voice.base import VoiceConversation, VoiceProvider, VoiceProviderError
from app.voice.elevenlabs import ElevenLabsVoice
from tests.conftest import TEST_ACCESS_CODE, TEST_VOICE_LIMIT
from tests.plans import make_plan

FAKE_KEY = "fake-elevenlabs-key"
CONVERSATION_ID = "conv_123"
SIGNED_URL = (
    "wss://api.elevenlabs.test/v1/convai/conversation"
    f"?agent_id=agent_x&conversation_id={CONVERSATION_ID}&conversation_signature=abc"
)


def make_voice(transport: httpx.MockTransport) -> ElevenLabsVoice:
    return ElevenLabsVoice(
        api_key=SecretStr(FAKE_KEY),
        agent_id="agent_x",
        base_url="https://api.elevenlabs.test",
        transport=transport,
    )


# --- ElevenLabs adapter, against a fake server -------------------------------------------


@pytest.mark.anyio
async def test_requests_a_single_use_signed_url_for_the_configured_agent() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"signed_url": SIGNED_URL})

    voice = make_voice(httpx.MockTransport(fake_server))

    conversation = await voice.create_conversation()

    assert conversation == VoiceConversation(signed_url=SIGNED_URL, conversation_id=CONVERSATION_ID)
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == "/v1/convai/conversation/get-signed-url"
    assert request.url.params["agent_id"] == "agent_x"
    # A plain signed URL can be reused for 15 minutes; with the conversation id it is single-use.
    assert request.url.params["include_conversation_id"] == "true"
    assert request.headers["xi-api-key"] == FAKE_KEY


@pytest.mark.anyio
async def test_a_signed_url_without_conversation_id_is_rejected() -> None:
    reusable = "wss://api.elevenlabs.test/v1/convai/conversation?agent_id=agent_x&conversation_signature=abc"
    voice = make_voice(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"signed_url": reusable}))
    )

    with pytest.raises(VoiceProviderError, match="conversation_id"):
        await voice.create_conversation()


@pytest.mark.anyio
async def test_http_error_becomes_provider_error_without_leaking_key() -> None:
    voice = make_voice(httpx.MockTransport(lambda _: httpx.Response(403, json={"detail": "no"})))

    with pytest.raises(VoiceProviderError, match="403") as info:
        await voice.create_conversation()

    assert FAKE_KEY not in str(info.value)


@pytest.mark.anyio
async def test_http_error_includes_the_reason_given_by_elevenlabs() -> None:
    body = {"detail": {"message": "The API key is missing the permission convai_write."}}
    voice = make_voice(httpx.MockTransport(lambda _: httpx.Response(401, json=body)))

    with pytest.raises(VoiceProviderError, match=r"401: .*convai_write"):
        await voice.create_conversation()


@pytest.mark.anyio
async def test_timeout_becomes_provider_error() -> None:
    def slow_server(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    voice = make_voice(httpx.MockTransport(slow_server))

    with pytest.raises(VoiceProviderError, match="ConnectTimeout"):
        await voice.create_conversation()


@pytest.mark.anyio
@pytest.mark.parametrize("body", [{"weird": "thing"}, {"signed_url": "https://not-a-websocket"}])
async def test_unexpected_response_gives_clear_error(body: dict[str, str]) -> None:
    voice = make_voice(httpx.MockTransport(lambda _: httpx.Response(200, json=body)))

    with pytest.raises(VoiceProviderError, match="unexpected format"):
        await voice.create_conversation()


def test_elevenlabs_implements_the_interface() -> None:
    voice: VoiceProvider = make_voice(httpx.MockTransport(lambda _: httpx.Response(200)))
    assert voice is not None


# --- POST /voice-session -----------------------------------------------------------------


class FakeVoice:
    async def create_conversation(self) -> VoiceConversation:
        return VoiceConversation(signed_url=SIGNED_URL, conversation_id=CONVERSATION_ID)


class DownVoice:
    async def create_conversation(self) -> VoiceConversation:
        raise VoiceProviderError("ElevenLabs is not answering")


def use_voice(voice: VoiceProvider) -> None:
    app.dependency_overrides[get_voice_provider] = lambda: voice


class CountingVoice(FakeVoice):
    def __init__(self) -> None:
        self.calls = 0

    async def create_conversation(self) -> VoiceConversation:
        self.calls += 1
        return await super().create_conversation()


PLAN_BODY = {"plan": make_plan().model_dump()}


def start(client: TestClient) -> int:
    return client.post("/voice-session", json=PLAN_BODY).status_code


def test_returns_signed_url_and_its_lifetime(client: TestClient) -> None:
    use_voice(FakeVoice())

    response = client.post("/voice-session", json=PLAN_BODY)

    assert response.status_code == 200
    assert response.json() == {
        "signed_url": SIGNED_URL,
        "conversation_id": CONVERSATION_ID,
        "expires_in_seconds": 900,
    }


def test_signed_url_response_is_never_cached(client: TestClient) -> None:
    use_voice(FakeVoice())

    response = client.post("/voice-session", json=PLAN_BODY)

    assert response.headers["Cache-Control"] == "no-store"


def test_daily_limit_per_access_code_returns_429_with_retry_after(client: TestClient) -> None:
    use_voice(FakeVoice())
    for _ in range(TEST_VOICE_LIMIT):
        assert client.post("/voice-session", json=PLAN_BODY).status_code == 200

    response = client.post("/voice-session", json=PLAN_BODY)

    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 86_400


def test_a_provider_failure_does_not_use_up_the_quota(client: TestClient) -> None:
    use_voice(DownVoice())
    for _ in range(TEST_VOICE_LIMIT + 2):
        assert client.post("/voice-session", json=PLAN_BODY).status_code == 503

    use_voice(FakeVoice())

    assert client.post("/voice-session", json=PLAN_BODY).status_code == 200


def test_stores_the_plan_under_the_conversation_id(client: TestClient) -> None:
    use_voice(FakeVoice())

    response = client.post("/voice-session", json=PLAN_BODY)

    session = app.dependency_overrides[get_conversation_store]().get(CONVERSATION_ID)
    assert response.status_code == 200
    assert session is not None
    assert session.plan == make_plan()
    assert session.access_id != TEST_ACCESS_CODE  # a hash, never the code itself


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"plan": {"intro": "Hola", "duration_minutes": 30, "topics": []}},
        {"plan": make_plan().model_dump() | {"intro": "x" * MAX_PLAN_CHARS}},
    ],
    ids=["missing plan", "no topics", "too large"],
)
def test_invalid_plan_returns_422_without_using_quota_or_provider(
    client: TestClient, body: dict[str, object]
) -> None:
    voice = CountingVoice()
    use_voice(voice)

    assert client.post("/voice-session", json=body).status_code == 422

    assert voice.calls == 0
    for _ in range(TEST_VOICE_LIMIT):
        assert start(client) == 200


def test_a_provider_failure_stores_nothing(client: TestClient) -> None:
    use_voice(DownVoice())

    client.post("/voice-session", json=PLAN_BODY)

    assert len(app.dependency_overrides[get_conversation_store]()) == 0


def test_voice_provider_down_returns_503(client: TestClient) -> None:
    use_voice(DownVoice())

    response = client.post("/voice-session", json=PLAN_BODY)

    assert response.status_code == 503
    assert "voice service" in response.json()["detail"]


# --- real ElevenLabs. Run with: make test-live -------------------------------------------


@pytest.mark.live
def test_live_elevenlabs_returns_a_signed_url(client: TestClient) -> None:
    response = client.post("/voice-session", json=PLAN_BODY)

    assert response.status_code == 200, response.text
    signed_url = response.json()["signed_url"]
    assert signed_url.startswith("wss://")
    assert response.json()["conversation_id"].startswith("conv_")
    # Never print the full URL: it is a credential for the next 15 minutes.
    print(f"\nSigned URL received: {signed_url.split('?')[0]}?<redacted>")
