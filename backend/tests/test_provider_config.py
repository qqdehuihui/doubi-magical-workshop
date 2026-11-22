from app.core import config
from app.core.errors import ApiException
from app.core.providers import get_provider
from app.core.providers.mock import MockProvider
from app.core.providers.openai_compatible import OpenAICompatibleProvider


def test_default_provider_is_mock(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "mock")
    assert isinstance(get_provider(), MockProvider)


def test_switch_to_openai_compatible(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    assert isinstance(get_provider(), OpenAICompatibleProvider)


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "claude")
    try:
        get_provider()
        assert False, "应抛出 LLM_PROVIDER_UNSUPPORTED"
    except ApiException as exc:
        assert exc.code == "LLM_PROVIDER_UNSUPPORTED"


def test_mock_health_check():
    info = MockProvider().health_check()
    assert info["provider"] == "mock"
    assert info["configured"] is True
    assert info["mock"] is True


def test_openai_health_check_requires_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    info = OpenAICompatibleProvider().health_check()
    assert info["configured"] is False
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-test")
    assert OpenAICompatibleProvider().health_check()["configured"] is True
