"""qoder_client 只读连通性检查测试：全部使用假响应，不发起真实网络请求。"""

import json

import httpx
import pytest

from app.core import config, qoder_client
from app.core.qoder_client import (
    KIND_API_ERROR,
    KIND_AUTH_FAILED,
    KIND_INSUFFICIENT_CREDITS,
    KIND_NETWORK,
    KIND_NOT_CONFIGURED,
    KIND_PERMISSION_DENIED,
    KIND_RATE_LIMITED,
    KIND_TIMEOUT,
    QoderApiError,
    check_config,
    connectivity_report,
    list_environments,
)

FAKE_TOKEN = "pt-fake-token-for-tests-1234567890"


class FakeResp:
    def __init__(self, status_code=200, payload=None, content=None):
        self.status_code = status_code
        if content is None:
            content = json.dumps(payload if payload is not None else {}).encode("utf-8")
        self.content = content

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return json.loads(self.content.decode("utf-8"))


def _fake_get_factory(result=None, exc=None):
    calls = []

    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kw):
        calls.append({"url": url, "headers": headers, "follow_redirects": follow_redirects})
        if exc is not None:
            raise exc
        return result

    fake_get.calls = calls
    return fake_get


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    monkeypatch.setattr(config, "QODER_ACCESS_TOKEN", FAKE_TOKEN)
    monkeypatch.setattr(config, "QODER_API_BASE_URL", "https://api.qoder.com.cn")
    monkeypatch.setattr(config, "QODER_MODEL", "ultimate")


def _patch_get(monkeypatch, result=None, exc=None):
    fake = _fake_get_factory(result, exc)
    monkeypatch.setattr(qoder_client.httpx, "get", fake)
    return fake


def test_check_config_complete():
    cfg = check_config()
    assert cfg["configured"] is True
    assert cfg["token_present"] is True
    assert FAKE_TOKEN not in json.dumps(cfg, ensure_ascii=False)


def test_missing_token_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "QODER_ACCESS_TOKEN", "")
    fake = _patch_get(monkeypatch, FakeResp())
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_NOT_CONFIGURED
    assert fake.calls == []  # 未配置时不发任何请求


def test_http_401_auth_failed(monkeypatch):
    _patch_get(monkeypatch, FakeResp(401, {"message": "invalid token"}))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_AUTH_FAILED


def test_http_403_permission_denied(monkeypatch):
    _patch_get(monkeypatch, FakeResp(403, {"message": "forbidden"}))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_PERMISSION_DENIED


def test_http_402_insufficient_credits(monkeypatch):
    _patch_get(monkeypatch, FakeResp(402, {"message": "payment required"}))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_INSUFFICIENT_CREDITS


def test_body_credit_hint_maps_to_insufficient(monkeypatch):
    _patch_get(monkeypatch, FakeResp(400, {"message": "insufficient credits, please top up"}))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_INSUFFICIENT_CREDITS


def test_http_429_rate_limited(monkeypatch):
    _patch_get(monkeypatch, FakeResp(429, {"message": "too many requests"}))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_RATE_LIMITED


def test_network_error_classification(monkeypatch):
    _patch_get(monkeypatch, exc=httpx.ConnectError("dns fail"))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_NETWORK


def test_timeout_classification(monkeypatch):
    _patch_get(monkeypatch, exc=httpx.ReadTimeout("slow"))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_TIMEOUT


def test_redirect_is_refused(monkeypatch):
    _patch_get(monkeypatch, FakeResp(302, content=b"moved"))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_API_ERROR
    assert "重定向" in ei.value.message


def test_http_must_be_https(monkeypatch):
    monkeypatch.setattr(config, "QODER_API_BASE_URL", "http://api.qoder.com.cn")
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert ei.value.kind == KIND_API_ERROR


def test_environments_success_summary_and_bearer_header(monkeypatch):
    fake = _patch_get(
        monkeypatch,
        FakeResp(200, {"data": [{"id": "env_a", "name": "default"}, {"id": "env_b", "name": "cls"}], "has_more": False}),
    )
    out = list_environments()
    assert [e["id"] for e in out["environments"]] == ["env_a", "env_b"]
    assert out["has_more"] is False
    hdr = fake.calls[0]["headers"]["Authorization"]
    assert hdr == f"Bearer {FAKE_TOKEN}"
    assert fake.calls[0]["url"] == "https://api.qoder.com.cn/api/v1/cloud/environments"
    assert fake.calls[0]["follow_redirects"] is False


def test_error_detail_never_leaks_token(monkeypatch):
    _patch_get(monkeypatch, FakeResp(500, content=f'{{"message": "upstream saw {FAKE_TOKEN}"}}'.encode()))
    with pytest.raises(QoderApiError) as ei:
        list_environments()
    assert FAKE_TOKEN not in ei.value.message
    assert "***" in ei.value.message


def test_report_not_configured_shape(monkeypatch):
    monkeypatch.setattr(config, "QODER_ACCESS_TOKEN", "")
    rep = connectivity_report()
    assert rep["configured"] is False
    assert rep["auth_verified"] is False
    assert rep["error"]["kind"] == KIND_NOT_CONFIGURED
    assert rep["readonly"] is True
    assert FAKE_TOKEN not in json.dumps(rep, ensure_ascii=False)


def test_report_success_verified(monkeypatch):
    def fake_get(url, headers=None, timeout=None, follow_redirects=None, **kw):
        if url.endswith("/environments"):
            return FakeResp(200, {"data": [{"id": "env_a", "name": "default"}], "has_more": False})
        return FakeResp(200, {"data": [{"id": "ultimate", "enabled": True}], "has_more": False})

    monkeypatch.setattr(qoder_client.httpx, "get", fake_get)
    rep = connectivity_report()
    assert rep["configured"] is True
    assert rep["auth_verified"] is True
    assert rep["error"] is None
    assert rep["checks"]["environments"]["environments"][0]["id"] == "env_a"
    assert rep["checks"]["models"]["requested_model_available"] is True


def test_report_auth_failure_carried(monkeypatch):
    monkeypatch.setattr(qoder_client.httpx, "get", lambda *a, **k: FakeResp(401, {"message": "bad"}))
    rep = connectivity_report()
    assert rep["auth_verified"] is False
    assert rep["error"]["kind"] == KIND_AUTH_FAILED


def test_health_endpoint(client, monkeypatch):
    monkeypatch.setattr(qoder_client.httpx, "get", lambda *a, **k: FakeResp(401, {"message": "bad"}))
    resp = client.get("/api/llm/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "qoder_cloud_agents"
    assert body["error"]["kind"] == KIND_AUTH_FAILED
    assert FAKE_TOKEN not in resp.text
