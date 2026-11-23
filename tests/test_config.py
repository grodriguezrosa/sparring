from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Tests run inside an empty temporary folder, so they never read the real .env
    # and do not depend on what is on your machine.
    monkeypatch.chdir(tmp_path)


def load_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  (see app/config.py)


def test_reads_configuration_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    settings = load_settings()

    assert settings.deepseek_api_key.get_secret_value() == "test-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"


def test_key_is_hidden_when_printing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    settings = load_settings()

    assert "test-key" not in repr(settings)
    assert "test-key" not in str(settings)


def test_fails_when_deepseek_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        load_settings()
