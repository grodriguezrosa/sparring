import copy
from typing import Any

import pytest

from app.services.interviewer import AGENT_PROMPT_STUB
from scripts.configure_agent import (
    MANAGED_FIELDS,
    PRESERVED_FIELDS,
    check_update,
    desired_values,
    dig,
    nest,
    validate_llm_url,
)

AGENT: dict[str, Any] = {
    "conversation_config": {
        "agent": {
            "first_message": "old greeting",
            "language": "es",
            "prompt": {"prompt": "old prompt", "llm": "deepseek-v41-flash", "built_in_tools": {}},
        },
        "tts": {"voice_id": "voice_1", "model_id": "eleven_v3_conversational"},
        "conversation": {"max_duration_seconds": 2100},
    },
    "platform_settings": {
        "auth": {"enable_auth": False},
        "call_limits": {"agent_concurrency_limit": 1, "daily_limit": 5},
        "overrides": {"conversation_config_override": {"conversation": {"text_only": True}}},
    },
}


def apply(agent: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """What a successful PATCH would leave: the agent with the managed fields replaced."""
    result = copy.deepcopy(agent)
    for path, value in values.items():
        *parents, leaf = path.split(".")
        node = result
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return result


def test_dig_reads_nested_paths_and_returns_none_when_missing() -> None:
    assert dig(AGENT, "conversation_config.tts.voice_id") == "voice_1"
    assert dig(AGENT, "conversation_config.nope.voice_id") is None


def test_nest_builds_the_patch_body() -> None:
    assert nest({"a.b": 1, "a.c": 2, "d": 3}) == {"a": {"b": 1, "c": 2}, "d": 3}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://abc.trycloudflare.com", "https://abc.trycloudflare.com"),
        ("https://abc.trycloudflare.com/", "https://abc.trycloudflare.com"),
    ],
)
def test_accepts_https_base_urls(url: str, expected: str) -> None:
    assert validate_llm_url(url) == expected


@pytest.mark.parametrize(
    "url", ["http://abc.trycloudflare.com", "https://abc.trycloudflare.com/v1", "abc.com"]
)
def test_rejects_other_urls(url: str) -> None:
    with pytest.raises(ValueError, match="https base URL"):
        validate_llm_url(url)


def test_desired_values_only_touch_managed_fields() -> None:
    desired = desired_values("https://abc.trycloudflare.com", "secret_1")

    assert set(desired) == set(MANAGED_FIELDS)
    assert not set(desired) & set(PRESERVED_FIELDS)


def test_desired_values_point_the_agent_at_our_endpoint_securely() -> None:
    desired = desired_values("https://abc.trycloudflare.com", "secret_1")

    assert desired["conversation_config.agent.prompt.prompt"] == AGENT_PROMPT_STUB
    assert desired["conversation_config.agent.prompt.llm"] == "custom-llm"
    assert desired["conversation_config.agent.prompt.custom_llm"] == {
        "url": "https://abc.trycloudflare.com/v1",
        "model_id": "sparring-interviewer",
        "api_key": {"secret_id": "secret_1"},
    }
    assert desired["platform_settings.auth.enable_auth"] is True
    text_only = "platform_settings.overrides.conversation_config_override.conversation.text_only"
    assert desired[text_only] is False


def test_a_clean_update_has_no_problems() -> None:
    desired = desired_values("https://abc.trycloudflare.com", "secret_1")
    after = apply(AGENT, desired)
    # ElevenLabs does not echo the secret reference back in the same shape.
    after["conversation_config"]["agent"]["prompt"]["custom_llm"].pop("api_key")

    assert check_update(AGENT, after, desired) == []


def test_reports_fields_not_applied_and_preserved_fields_that_changed() -> None:
    desired = desired_values("https://abc.trycloudflare.com", "secret_1")
    after = apply(AGENT, desired)
    after["platform_settings"]["auth"]["enable_auth"] = False
    after["platform_settings"]["call_limits"] = {"daily_limit": 100_000}

    assert check_update(AGENT, after, desired) == [
        "not applied: platform_settings.auth.enable_auth",
        "changed: platform_settings.call_limits",
    ]
