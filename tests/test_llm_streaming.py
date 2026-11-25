"""Streaming chat (used by the voice agent's custom LLM endpoint): DeepSeek adapter and FakeLLM."""

import json
import time

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import get_settings
from app.llm.base import ChatMessage, LLMProviderError
from app.llm.deepseek import DeepSeekLLM
from app.llm.fake import FakeLLM

pytestmark = pytest.mark.anyio

FAKE_KEY = "fake-deepseek-key"
CONVERSATION = [
    ChatMessage(role="system", content="You are an interviewer."),
    ChatMessage(role="assistant", content="Hola, ¿empezamos?"),
    ChatMessage(role="user", content="Sí, cuando quieras."),
]


def sse(*events: object) -> bytes:
    """Build an SSE body like DeepSeek's: dicts become `data: {json}`, strings go raw."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}" if isinstance(event, dict) else str(event))
        lines.append("")
    return "\n".join(lines).encode()


def delta(**fields: str) -> dict[str, object]:
    return {"choices": [{"index": 0, "delta": fields}]}


def make_llm(transport: httpx.MockTransport) -> DeepSeekLLM:
    return DeepSeekLLM(
        api_key=SecretStr(FAKE_KEY),
        base_url="https://api.deepseek.test",
        model="deepseek-flash",
        transport=transport,
    )


async def collect(llm: DeepSeekLLM | FakeLLM) -> list[str]:
    return [chunk async for chunk in llm.stream(messages=CONVERSATION)]


# --- DeepSeek adapter, against a fake server -------------------------------------------


async def test_streams_the_whole_conversation_and_yields_text_chunks() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = sse(
            delta(role="assistant"), delta(content="Perfecto, "), delta(content="empecemos.")
        )
        return httpx.Response(200, content=body + sse("data: [DONE]"))

    chunks = await collect(make_llm(httpx.MockTransport(fake_server)))

    assert chunks == ["Perfecto, ", "empecemos."]
    body = json.loads(requests[0].content)
    assert body["stream"] is True
    assert body["messages"] == [
        {"role": "system", "content": "You are an interviewer."},
        {"role": "assistant", "content": "Hola, ¿empezamos?"},
        {"role": "user", "content": "Sí, cuando quieras."},
    ]
    assert requests[0].headers["Authorization"] == f"Bearer {FAKE_KEY}"


async def test_skips_keep_alives_reasoning_and_usage_chunks() -> None:
    body = sse(
        ": keep-alive",
        delta(reasoning_content="The user is ready, so..."),
        delta(content="Vale."),
        {"choices": [], "usage": {"total_tokens": 42}},
        "data: [DONE]",
    )
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    assert await collect(llm) == ["Vale."]


async def test_stops_at_done_even_if_more_data_follows() -> None:
    body = sse(delta(content="Uno."), "data: [DONE]", delta(content="Nunca."))
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    assert await collect(llm) == ["Uno."]


async def test_http_error_becomes_provider_error_without_leaking_key() -> None:
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(429, json={"error": "busy"})))

    with pytest.raises(LLMProviderError, match="429") as info:
        await collect(llm)

    assert FAKE_KEY not in str(info.value)


async def test_timeout_becomes_provider_error() -> None:
    def slow_server(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMProviderError, match="ReadTimeout"):
        await collect(make_llm(httpx.MockTransport(slow_server)))


@pytest.mark.parametrize("bad_line", ["data: {not json", 'data: {"choices": "weird"}'])
async def test_malformed_chunk_gives_clear_error(bad_line: str) -> None:
    body = sse(delta(content="Hola"), bad_line)
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(200, content=body)))

    with pytest.raises(LLMProviderError, match="unexpected format"):
        await collect(llm)


async def test_thinking_is_off_by_default_to_cut_latency() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=sse(delta(content="Vale."), "data: [DONE]"))

    llm = make_llm(httpx.MockTransport(fake_server))
    await collect(llm)
    [_ async for _ in llm.stream(messages=CONVERSATION, reasoning=True)]

    assert json.loads(requests[0].content)["thinking"] == {"type": "disabled"}
    assert json.loads(requests[1].content)["thinking"] == {"type": "enabled"}


async def test_reuses_a_shared_http_client_without_closing_it() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=sse(delta(content="Vale."), "data: [DONE]"))

    shared = httpx.AsyncClient(transport=httpx.MockTransport(fake_server))
    llm = DeepSeekLLM(
        api_key=SecretStr(FAKE_KEY),
        base_url="https://api.deepseek.test",
        model="deepseek-flash",
        http_client=shared,
    )

    assert await collect(llm) == ["Vale."]
    assert await collect(llm) == ["Vale."]

    assert len(requests) == 2
    assert str(requests[0].url) == "https://api.deepseek.test/chat/completions"
    assert not shared.is_closed  # the pool belongs to the app, not to one call
    await shared.aclose()


# --- FakeLLM --------------------------------------------------------------------------


async def test_fake_llm_streams_its_canned_response_and_records_the_call() -> None:
    llm = FakeLLM(["Perfecto, empecemos con pytest."])

    chunks = await collect(llm)

    assert "".join(chunks) == "Perfecto, empecemos con pytest."
    assert len(chunks) > 1  # really streamed, not one block
    assert llm.stream_calls == [CONVERSATION]


# --- real DeepSeek. Run with: make test-live -------------------------------------------


@pytest.mark.live
async def test_live_deepseek_streams_spanish_text() -> None:
    try:
        settings = get_settings()
    except ValidationError:
        pytest.skip("DEEPSEEK_API_KEY is missing from .env")
    llm = DeepSeekLLM(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    messages = [
        ChatMessage(
            role="system",
            content="You are a technical interviewer. Reply in Spanish, in one short sentence.",
        ),
        ChatMessage(role="user", content="Hola, estoy listo para la entrevista de Python."),
    ]

    start = time.perf_counter()
    first_chunk_at: float | None = None
    chunks: list[str] = []
    async for chunk in llm.stream(messages=messages):
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter() - start
        chunks.append(chunk)
    total = time.perf_counter() - start

    assert "".join(chunks).strip()
    print(f"\nFirst text chunk after {first_chunk_at:.2f} s, total {total:.2f} s")
    print(f"DeepSeek said: {''.join(chunks)}")
