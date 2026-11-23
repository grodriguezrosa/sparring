from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.api.deps import get_conversation_store, get_voice_quota
from app.config import Settings, get_settings
from app.main import app
from app.services.conversations import ConversationStore
from app.services.quota import DailyQuota

TEST_ACCESS_CODE = "test-access-code-0123456789"
TEST_VOICE_LIMIT = 3
TEST_AGENT_LLM_SECRET = "test-agent-llm-secret-0123456789abcdef"  # noqa: S105  (fake, tests only)


def make_test_settings() -> Settings:
    return Settings(
        deepseek_api_key=SecretStr("test-deepseek-key"),
        elevenlabs_api_key=SecretStr("test-elevenlabs-key"),
        elevenlabs_agent_id="agent_test",
        agent_llm_secret=SecretStr(TEST_AGENT_LLM_SECRET),
        access_codes=[SecretStr(TEST_ACCESS_CODE)],
    )


@pytest.fixture
def client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    """A test client that already sends a valid access code.

    Normal tests get fake settings, a fresh voice quota and a fresh conversation store.
    Tests marked `live` use the real .env (and its first access code), and are skipped
    if it is incomplete.
    """
    if request.node.get_closest_marker("live"):
        try:
            settings = get_settings()
        except ValidationError:
            pytest.skip("Required variables are missing from .env")
    else:
        settings = make_test_settings()
        quota = DailyQuota(limit_per_day=TEST_VOICE_LIMIT)
        app.dependency_overrides[get_settings] = lambda: settings
        conversations = ConversationStore()
        app.dependency_overrides[get_voice_quota] = lambda: quota
        app.dependency_overrides[get_conversation_store] = lambda: conversations

    access_code = settings.access_codes[0].get_secret_value()
    yield TestClient(app, headers={"X-Access-Code": access_code})
    app.dependency_overrides.clear()  # so one test does not leak into the next
