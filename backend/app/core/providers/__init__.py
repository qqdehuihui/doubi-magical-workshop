"""Provider 工厂与统一调用入口。

业务模块只允许通过 providers.run() 调用模型，禁止直连任何 SDK。
"""

import logging

from app.core import config
from app.core.errors import ApiException
from app.core.providers.base import BaseProvider, GenerationRequest, GenerationResult
from app.core.providers.mock import MockProvider
from app.core.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger("ai_study.provider")

__all__ = [
    "BaseProvider",
    "GenerationRequest",
    "GenerationResult",
    "get_provider",
    "run",
]


def get_provider() -> BaseProvider:
    name = config.LLM_PROVIDER
    if name == "mock":
        return MockProvider()
    if name in ("openai", "openai_compatible"):
        return OpenAICompatibleProvider()
    raise ApiException(
        "LLM_PROVIDER_UNSUPPORTED",
        f"未知的 LLM_PROVIDER：{name}（支持 mock / openai）",
    )


def run(req: GenerationRequest, json_mode: bool = True) -> GenerationResult:
    provider = get_provider()
    try:
        result = provider.generate_json(req) if json_mode else provider.generate_text(req)
    except ApiException as exc:
        logger.warning(
            "provider=%s model=%s task=%s status=error code=%s",
            provider.name, provider.model_name, req.task, exc.code,
        )
        raise
    logger.info(
        "provider=%s model=%s task=%s status=ok elapsed_ms=%s prompt_tokens=%s completion_tokens=%s",
        result.provider, result.model, req.task, result.elapsed_ms,
        result.prompt_tokens, result.completion_tokens,
    )
    return result
