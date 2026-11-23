import json

import httpx
import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import get_settings
from app.llm.base import LLMClient, LLMProviderError
from app.llm.deepseek import DeepSeekLLM
from app.llm.structured import generate_structured

pytestmark = pytest.mark.anyio

FAKE_KEY = "sk-fake-test-key"


def ok_response(content: str) -> httpx.Response:
    """Mimic a successful DeepSeek response with the given text."""
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def make_llm(transport: httpx.MockTransport) -> DeepSeekLLM:
    return DeepSeekLLM(
        api_key=SecretStr(FAKE_KEY),
        base_url="https://api.deepseek.test",
        model="deepseek-flash",
        transport=transport,
    )


async def test_sends_request_in_deepseek_format() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return ok_response("Hola")

    llm = make_llm(httpx.MockTransport(fake_server))

    text = await llm.complete(system="You are an interviewer.", user="Hola")

    assert text == "Hola"
    request = requests[0]
    assert request.method == "POST"
    assert request.url == "https://api.deepseek.test/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-flash"
    assert body["messages"] == [
        {"role": "system", "content": "You are an interviewer."},
        {"role": "user", "content": "Hola"},
    ]
    assert "response_format" not in body


async def test_enables_response_format_in_json_mode() -> None:
    requests: list[httpx.Request] = []

    def fake_server(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return ok_response("{}")

    llm = make_llm(httpx.MockTransport(fake_server))

    await llm.complete(system="Reply in JSON.", user="...", json_mode=True)

    body = json.loads(requests[0].content)
    assert body["response_format"] == {"type": "json_object"}


async def test_null_content_becomes_empty_string() -> None:
    llm = make_llm(
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        )
    )

    assert await llm.complete(system="...", user="...") == ""


async def test_http_error_becomes_provider_error_without_leaking_key() -> None:
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "bad key"})))

    with pytest.raises(LLMProviderError, match="401") as info:
        await llm.complete(system="...", user="...")

    assert FAKE_KEY not in str(info.value)


async def test_timeout_becomes_provider_error() -> None:
    def slow_server(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    llm = make_llm(httpx.MockTransport(slow_server))

    with pytest.raises(LLMProviderError, match="ReadTimeout"):
        await llm.complete(system="...", user="...")


async def test_unexpected_response_format_gives_clear_error() -> None:
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(200, json={"weird": "thing"})))

    with pytest.raises(LLMProviderError, match="unexpected format"):
        await llm.complete(system="...", user="...")


def test_deepseek_implements_the_interface() -> None:
    llm: LLMClient = make_llm(httpx.MockTransport(lambda _: ok_response("")))
    assert llm is not None


# --- Test against the real API. Run only with: make test-live --------------------------


class Greeting(BaseModel):
    greeting: str
    language: str


@pytest.mark.live
async def test_live_deepseek_returns_valid_json_in_spanish() -> None:
    try:
        settings = get_settings()
    except ValidationError:
        pytest.skip("DEEPSEEK_API_KEY is missing from .env")

    llm = DeepSeekLLM(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )

    result = await generate_structured(
        llm,
        system="Greet a candidate about to do a Python interview. Write the greeting in Spanish.",
        user="Me llamo Guillermo.",
        schema=Greeting,
    )

    assert result.greeting.strip()
    print(f"\nDeepSeek response: {result}")
