import pytest
from pydantic import BaseModel

from app.llm.base import LLMClient
from app.llm.fake import FakeLLM
from app.llm.structured import LLMOutputError, generate_structured

pytestmark = pytest.mark.anyio  # every test in this file is async


class Candidate(BaseModel):
    role: str
    years_of_experience: int


VALID_CANDIDATE = '{"role": "Backend Python", "years_of_experience": 3}'


async def test_returns_validated_model_on_first_try() -> None:
    llm = FakeLLM([VALID_CANDIDATE])

    candidate = await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    assert candidate == Candidate(role="Backend Python", years_of_experience=3)
    assert len(llm.calls) == 1


async def test_retries_once_when_response_is_invalid() -> None:
    llm = FakeLLM(["this is not JSON", VALID_CANDIDATE])

    candidate = await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    assert candidate.role == "Backend Python"
    assert len(llm.calls) == 2


async def test_fails_with_clear_error_when_retry_also_fails() -> None:
    llm = FakeLLM(["not JSON", '{"role": "Backend"}'])  # the second one misses a field

    with pytest.raises(LLMOutputError, match="Candidate"):
        await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    assert len(llm.calls) == 2  # never retries more than once


async def test_system_prompt_includes_json_schema() -> None:
    llm = FakeLLM([VALID_CANDIDATE])

    await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    call = llm.calls[0]
    assert call.system.startswith("Extract.")
    assert "JSON" in call.system
    assert "years_of_experience" in call.system


async def test_enables_provider_json_mode() -> None:
    llm = FakeLLM([VALID_CANDIDATE])

    await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    assert llm.calls[0].json_mode is True


async def test_retries_when_provider_returns_blank_content() -> None:
    # DeepSeek in JSON mode may return only spaces if the model did not produce valid JSON.
    llm = FakeLLM(["   ", VALID_CANDIDATE])

    candidate = await generate_structured(llm, system="Extract.", user="...", schema=Candidate)

    assert candidate.years_of_experience == 3
    assert len(llm.calls) == 2


def test_fake_llm_implements_the_interface() -> None:
    # If FakeLLM did not match the LLMClient Protocol, mypy would fail on this line.
    llm: LLMClient = FakeLLM([])
    assert llm is not None
