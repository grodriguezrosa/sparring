"""POST /v1/chat/completions: the custom LLM endpoint the ElevenLabs agent calls every turn."""

import json
from collections.abc import AsyncIterator, Sequence

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conversation_store, get_llm
from app.config import get_settings
from app.llm.base import ChatMessage, LLMClient, LLMProviderError
from app.llm.fake import FakeLLM
from app.main import app
from app.services.conversations import ConversationStore
from tests.conftest import TEST_AGENT_LLM_SECRET
from tests.plans import make_plan

PATH = "/v1/chat/completions"
CONVERSATION_ID = "conv_abc123"
AUTH = {"Authorization": f"Bearer {TEST_AGENT_LLM_SECRET}"}
REPLY = "Perfecto, empecemos con pytest."


def elevenlabs_body(conversation_id: str = CONVERSATION_ID) -> dict[str, object]:
    """What ElevenLabs sends: its system prompt (with our marker rendered) plus the turns."""
    return {
        "model": "sparring-interviewer",
        "stream": True,
        "temperature": 0.0,
        "max_tokens": 8192,
        "stream_options": {"include_usage": True},
        "messages": [
            {
                "role": "system",
                "content": f"(boilerplate) <conversation_id>{conversation_id}</conversation_id>",
            },
            {"role": "assistant", "content": "Hola, ¿me oyes bien?"},
            {"role": "user", "content": "Sí, estoy listo."},
        ],
    }


def store() -> ConversationStore:
    conversations: ConversationStore = app.dependency_overrides[get_conversation_store]()
    return conversations


def use_llm(llm: LLMClient) -> None:
    app.dependency_overrides[get_llm] = lambda: llm


def start_conversation() -> None:
    store().start(CONVERSATION_ID, plan=make_plan(), access_id="code-a")


def sse_events(text: str) -> list[str]:
    return [line.removeprefix("data: ") for line in text.splitlines() if line.startswith("data: ")]


# --- authentication ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong-secret"}, {"Authorization": TEST_AGENT_LLM_SECRET}],
    ids=["missing", "wrong", "not bearer"],
)
def test_rejects_requests_without_the_agent_secret(
    client: TestClient, headers: dict[str, str]
) -> None:
    llm = FakeLLM([REPLY])
    use_llm(llm)
    start_conversation()

    response = client.post(PATH, json=elevenlabs_body(), headers=headers)

    assert response.status_code == 401
    assert llm.stream_calls == []


def test_access_code_is_not_enough(client: TestClient) -> None:
    use_llm(FakeLLM([REPLY]))
    start_conversation()

    assert client.post(PATH, json=elevenlabs_body()).status_code == 401


# --- conversation lookup -----------------------------------------------------------------


def test_unknown_conversation_returns_404_without_calling_the_llm(client: TestClient) -> None:
    llm = FakeLLM([REPLY])
    use_llm(llm)

    response = client.post(PATH, json=elevenlabs_body("conv_never_started"), headers=AUTH)

    assert response.status_code == 404
    assert llm.stream_calls == []


def test_missing_marker_returns_404(client: TestClient) -> None:
    use_llm(FakeLLM([REPLY]))
    body = elevenlabs_body()
    body["messages"] = [{"role": "user", "content": "Hola"}]

    assert client.post(PATH, json=body, headers=AUTH).status_code == 404


# --- streaming reply ---------------------------------------------------------------------


def test_streams_the_reply_in_openai_chunk_format(client: TestClient) -> None:
    use_llm(FakeLLM([REPLY]))
    start_conversation()

    response = client.post(PATH, json=elevenlabs_body(), headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    assert events[-1] == "[DONE]"
    chunks = [json.loads(event) for event in events[:-1]]
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert text == REPLY
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_the_llm_gets_our_prompt_and_the_spoken_history(client: TestClient) -> None:
    llm = FakeLLM([REPLY])
    use_llm(llm)
    start_conversation()

    client.post(PATH, json=elevenlabs_body(), headers=AUTH)

    (messages,) = llm.stream_calls
    assert "boilerplate" not in messages[0].content
    assert make_plan().topics[0].opening_question in messages[0].content
    assert messages[1:] == [
        ChatMessage(role="assistant", content="Hola, ¿me oyes bien?"),
        ChatMessage(role="user", content="Sí, estoy listo."),
    ]


class DownLLM:
    async def complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
        raise LLMProviderError("down")

    async def stream(self, *, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        raise LLMProviderError("down")
        yield ""  # never reached; makes this an async generator


class BreaksMidReplyLLM(DownLLM):
    async def stream(self, *, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        yield "Perfecto, "
        raise LLMProviderError("connection lost")


def test_provider_down_before_the_reply_returns_503(client: TestClient) -> None:
    use_llm(DownLLM())
    start_conversation()

    response = client.post(PATH, json=elevenlabs_body(), headers=AUTH)

    assert response.status_code == 503


def test_provider_failure_mid_reply_ends_the_stream_cleanly(client: TestClient) -> None:
    use_llm(BreaksMidReplyLLM())
    start_conversation()

    response = client.post(PATH, json=elevenlabs_body(), headers=AUTH)

    events = sse_events(response.text)
    assert response.status_code == 200  # already sent, cannot change now
    assert events[-1] == "[DONE]"
    assert json.loads(events[-2])["choices"][0]["finish_reason"] == "stop"


def test_oversized_conversation_returns_422(client: TestClient) -> None:
    use_llm(FakeLLM([REPLY]))
    start_conversation()
    body = elevenlabs_body()
    body["messages"] = [{"role": "user", "content": "x" * 300_000}]

    assert client.post(PATH, json=body, headers=AUTH).status_code == 422


# --- real DeepSeek. Run with: make test-live ---------------------------------------------


@pytest.mark.live
def test_live_interviewer_opens_with_the_plan_in_spanish(client: TestClient) -> None:
    conversations = ConversationStore()
    app.dependency_overrides[get_conversation_store] = lambda: conversations
    conversations.start(CONVERSATION_ID, plan=make_plan(), access_id="live")
    auth = {"Authorization": f"Bearer {get_settings().agent_llm_secret.get_secret_value()}"}

    response = client.post(PATH, json=elevenlabs_body(), headers=auth)

    assert response.status_code == 200, response.text
    chunks = [json.loads(event) for event in sse_events(response.text)[:-1]]
    text = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert text.strip()
    print(f"\nInterviewer said: {text}")
