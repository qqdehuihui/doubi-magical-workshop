"""OpenAI 兼容 Provider：统一处理超时、限流、鉴权与网络异常。

任何地方都不得记录 API Key。
"""

import json
import re
import time

from app.core import config
from app.core.errors import ApiException
from app.core.providers.base import BaseProvider, GenerationRequest, GenerationResult


def classify_exception(exc: Exception) -> tuple[str, str, int]:
    name = type(exc).__name__
    text = str(exc).lower()
    if "authentication" in name.lower() or "permission" in name.lower() or "api key" in text:
        return "LLM_AUTH", "AI 服务鉴权失败：请检查 OPENAI_API_KEY 是否正确", 401
    if "ratelimit" in name.lower() or "rate limit" in text or "429" in text:
        return "LLM_RATE_LIMIT", "AI 服务限流：请求过于频繁或额度不足，请稍后重试", 429
    if "timeout" in name.lower() or isinstance(exc, TimeoutError) or "timed out" in text:
        return "LLM_TIMEOUT", f"AI 服务响应超时（>{config.LLM_TIMEOUT:g}s），请稍后重试", 504
    if "connection" in name.lower() or isinstance(exc, OSError):
        return "LLM_NETWORK", "无法连接 AI 服务：请检查网络或 OPENAI_BASE_URL 配置", 502
    return "LLM_ERROR", f"AI 服务调用失败：{exc}", 502


def parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    fence = re.search(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ApiException("LLM_ERROR", "AI 未返回可解析的结果，请重试", 502)
    try:
        data = json.loads(cleaned[min(starts):])
    except json.JSONDecodeError:
        raise ApiException("LLM_ERROR", "AI 返回结果格式错误，请重试", 502)
    return data if isinstance(data, dict) else {"items": data}


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"

    @property
    def model_name(self) -> str:
        return config.LLM_MODEL

    def health_check(self) -> dict:
        configured = bool(config.LLM_API_KEY)
        return {
            "provider": self.name,
            "model": self.model_name,
            "configured": configured,
            "mock": False,
            "detail": "已配置 API Key" if configured else "缺少 OPENAI_API_KEY，无法调用真实模型",
        }

    def _require_key(self) -> None:
        if not config.LLM_API_KEY:
            raise ApiException(
                "LLM_NOT_CONFIGURED",
                "AI 服务未配置：请在 backend/.env 中设置 OPENAI_API_KEY（或切换 LLM_PROVIDER=mock）",
                503,
            )

    def _complete(self, messages: list[dict], temperature: float) -> tuple[str, dict]:
        self._require_key()
        from openai import OpenAI

        client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )
        start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            code, message, status = classify_exception(exc)
            raise ApiException(code, message, status)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        if not content:
            raise ApiException("LLM_ERROR", "AI 服务返回了空内容，请重试", 502)
        usage = getattr(resp, "usage", None)
        tokens = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "elapsed_ms": elapsed_ms,
        }
        return content, tokens

    def _messages(self, req: GenerationRequest) -> list[dict]:
        msgs = [{"role": "system", "content": req.system or "你是一个严谨的课件分析助手。"}]
        msgs.append({"role": "user", "content": req.prompt})
        return msgs

    def generate_text(self, req: GenerationRequest) -> GenerationResult:
        content, tokens = self._complete(self._messages(req), temperature=0.3)
        return self._make(
            text=content,
            prompt_tokens=tokens["prompt_tokens"],
            completion_tokens=tokens["completion_tokens"],
            elapsed_ms=tokens["elapsed_ms"],
        )

    def generate_json(self, req: GenerationRequest) -> GenerationResult:
        content, tokens = self._complete(self._messages(req), temperature=0.2)
        data = parse_json_response(content)
        return self._make(
            data=data,
            text=content,
            prompt_tokens=tokens["prompt_tokens"],
            completion_tokens=tokens["completion_tokens"],
            elapsed_ms=tokens["elapsed_ms"],
        )
