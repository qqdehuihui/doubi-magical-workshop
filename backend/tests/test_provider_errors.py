import pytest

from app.core import config
from app.core.errors import ApiException
from app.core.providers.openai_compatible import classify_exception


class FakeAuthenticationError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeAPITimeoutError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


@pytest.mark.parametrize(
    "exc,expected_code",
    [
        (FakeAuthenticationError("bad key"), "LLM_AUTH"),
        (FakeRateLimitError("429 too many requests"), "LLM_RATE_LIMIT"),
        (FakeAPITimeoutError("timed out"), "LLM_TIMEOUT"),
        (FakeAPIConnectionError("connection refused"), "LLM_NETWORK"),
        (TimeoutError("socket timeout"), "LLM_TIMEOUT"),
        (ValueError("unexpected"), "LLM_ERROR"),
    ],
)
def test_exception_classification(exc, expected_code):
    code, message, status = classify_exception(exc)
    assert code == expected_code
    assert message and status >= 400


def test_real_provider_without_key_returns_503(client, sample_doc, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    resp = client.post(f"/api/documents/{sample_doc['doc_id']}/key-points")
    assert resp.status_code == 503
    assert resp.json()["code"] == "LLM_NOT_CONFIGURED"


def test_unknown_provider_rejected_via_api(client, sample_doc, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    resp = client.post(f"/api/documents/{sample_doc['doc_id']}/key-points")
    assert resp.status_code == 400
    assert resp.json()["code"] == "LLM_PROVIDER_UNSUPPORTED"


def test_doc_too_long_guard(client, sample_doc, monkeypatch):
    monkeypatch.setattr(config, "MAX_GEN_CHARS", 10)
    resp = client.post(f"/api/documents/{sample_doc['doc_id']}/key-points")
    assert resp.status_code == 400
    assert resp.json()["code"] == "DOC_TOO_LONG"


def test_healthz_exposes_provider_info(client):
    body = client.get("/api/healthz").json()
    assert body["provider"]["provider"] == "mock"
    assert body["provider"]["mock"] is True
    assert body["llm_configured"] is True


def test_provider_logs_include_model_and_status(client, sample_doc, caplog):
    with caplog.at_level("INFO", logger="ai_study.provider"):
        client.post(f"/api/documents/{sample_doc['doc_id']}/key-points")
    record = next(r.getMessage() for r in caplog.records if "task=keypoints_v2" in r.getMessage())
    assert "provider=mock" in record
    assert "model=mock-v2" in record
    assert "status=ok" in record
    assert "prompt_tokens=" in record
