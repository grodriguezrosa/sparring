from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED_ENV = {
    "DEEPSEEK_API_KEY": "test-deepseek-key",
    "ELEVENLABS_API_KEY": "test-elevenlabs-key",
    "ELEVENLABS_AGENT_ID": "agent_test",
    "ACCESS_CODES": "first-access-code-0123, second-access-code-4567",
    "AGENT_LLM_SECRET": "agent-llm-secret-0123456789abcdefgh",
}


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Tests run inside an empty temporary folder, so they never read the real .env
    # and do not depend on what is on your machine.
    monkeypatch.chdir(tmp_path)
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)


def set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)


def load_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  (see app/config.py)


def test_reads_configuration_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    settings = load_settings()

    assert settings.deepseek_api_key.get_secret_value() == "test-deepseek-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.elevenlabs_agent_id == "agent_test"
    assert settings.elevenlabs_base_url == "https://api.elevenlabs.io"


def test_keys_are_hidden_when_printing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    settings = load_settings()

    for secret in (
        "test-deepseek-key",
        "test-elevenlabs-key",
        "first-access-code-0123",
        "agent-llm-secret-0123456789abcdefgh",
    ):
        assert secret not in repr(settings)
        assert secret not in str(settings)


@pytest.mark.parametrize("missing", list(REQUIRED_ENV))
def test_fails_when_a_required_variable_is_missing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    set_required_env(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        load_settings()


def test_access_codes_are_read_as_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    codes = [code.get_secret_value() for code in load_settings().access_codes]

    assert codes == ["first-access-code-0123", "second-access-code-4567"]


def test_rejects_short_access_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("ACCESS_CODES", "long-enough-access-code,1234")

    with pytest.raises(ValidationError, match="at least 16 characters"):
        load_settings()


def test_voice_quota_defaults_to_three_per_day(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    assert load_settings().voice_sessions_per_code_per_day == 3


def test_rejects_a_short_agent_llm_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("AGENT_LLM_SECRET", "too-short")

    with pytest.raises(ValidationError, match="at least 32 characters"):
        load_settings()
