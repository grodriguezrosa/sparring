import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm
from app.config import Settings, get_settings
from app.llm.fake import FakeLLM
from app.main import app
from tests.conftest import TEST_ACCESS_CODE, make_test_settings

PAID_ENDPOINTS = ["/profile", "/interview-plan", "/voice-session"]


@pytest.mark.parametrize("path", PAID_ENDPOINTS)
def test_paid_endpoints_reject_requests_without_access_code(client: TestClient, path: str) -> None:
    llm = FakeLLM([])
    app.dependency_overrides[get_llm] = lambda: llm

    response = client.post(path, json={}, headers={"X-Access-Code": ""})

    assert response.status_code == 401
    assert llm.calls == []  # rejected before any paid call


@pytest.mark.parametrize("path", PAID_ENDPOINTS)
def test_paid_endpoints_reject_a_wrong_access_code(client: TestClient, path: str) -> None:
    response = client.post(path, json={}, headers={"X-Access-Code": "wrong-code-0123456789"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid access code."


def test_a_missing_header_is_rejected_too(client: TestClient) -> None:
    without_header = TestClient(app)

    response = without_header.post("/voice-session")

    assert response.status_code == 401


def test_any_configured_access_code_is_accepted(client: TestClient) -> None:
    settings = make_test_settings()
    second_code = "second-tester-code-0123456789"
    settings_with_two_codes = Settings.model_validate(
        {**settings.model_dump(), "access_codes": [TEST_ACCESS_CODE, second_code]}
    )
    app.dependency_overrides[get_settings] = lambda: settings_with_two_codes

    response = client.post("/voice-session", headers={"X-Access-Code": second_code})

    assert response.status_code != 401


def test_health_does_not_need_an_access_code() -> None:
    assert TestClient(app).get("/health").status_code == 200
