"""Qoder CN Cloud Agents 只读接入客户端（第一阶段：连通性检查）.

安全约束：
- PAT 仅从 config（backend/.env）读取，绝不写入日志、异常信息或 HTTP 响应；
- 本模块只发起 GET 只读请求，不创建 Agent/Session，不发送模型推理请求；
- 拒绝重定向（防止 Bearer 头被转发到其他来源），限制响应体大小；
- 上游返回的 detail 先做长度截断与 Token 掩码，再对外暴露。
"""

import logging
import re
import time

import httpx

from app.core import config

logger = logging.getLogger("app.qoder")

MAX_BODY_BYTES = 2 * 1024 * 1024

# 错误分类 → 对外 kind / 中文说明
KIND_NOT_CONFIGURED = "not_configured"
KIND_AUTH_FAILED = "auth_failed"
KIND_PERMISSION_DENIED = "permission_denied"
KIND_INSUFFICIENT_CREDITS = "insufficient_credits"
KIND_RATE_LIMITED = "rate_limited"
KIND_TIMEOUT = "timeout"
KIND_NETWORK = "network_error"
KIND_API_ERROR = "api_error"

_LABELS = {
    KIND_NOT_CONFIGURED: "配置不完整：未设置 QODER_ACCESS_TOKEN",
    KIND_AUTH_FAILED: "认证失败：PAT 无效、过期或未被接受（HTTP 401）",
    KIND_PERMISSION_DENIED: "权限不足：当前账号无权访问该资源（HTTP 403）",
    KIND_INSUFFICIENT_CREDITS: "额度不足：Cloud Agents Credits 不足，请先到 Qoder 控制台确认额度，勿重复重试或自动购买",
    KIND_RATE_LIMITED: "请求过于频繁（HTTP 429）",
    KIND_TIMEOUT: "网络异常：请求超时",
    KIND_NETWORK: "网络异常：无法连接到 Qoder API",
    KIND_API_ERROR: "API 返回错误",
}

_CREDIT_HINT_RE = re.compile(r"insufficient|credit|quota|额度|余额", re.IGNORECASE)


class QoderApiError(Exception):
    def __init__(self, kind: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.http_status = http_status

    def info(self) -> dict:
        return {"kind": self.kind, "message": self.message, "http_status": self.http_status}


def _mask_token(text: str) -> str:
    token = config.QODER_ACCESS_TOKEN
    if token and token in text:
        return text.replace(token, "***")
    return text


def _request(path: str) -> dict:
    """对 Cloud Agents API 发起带 PAT 的只读 GET，返回解析后的 JSON。"""
    if not config.QODER_ACCESS_TOKEN:
        raise QoderApiError(KIND_NOT_CONFIGURED, _LABELS[KIND_NOT_CONFIGURED])
    base = config.QODER_API_BASE_URL
    if not base.startswith("https://"):
        raise QoderApiError(KIND_API_ERROR, f"QODER_API_BASE_URL 必须使用 https:// 起始，当前为 {base[:40]}")
    url = f"{base}{path}"
    headers = {"Authorization": f"Bearer {config.QODER_ACCESS_TOKEN}", "Accept": "application/json"}
    try:
        resp = httpx.get(
            url,
            headers=headers,
            timeout=config.QODER_TIMEOUT,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise QoderApiError(KIND_TIMEOUT, _LABELS[KIND_TIMEOUT]) from exc
    except (httpx.HTTPError, OSError) as exc:
        raise QoderApiError(KIND_NETWORK, _LABELS[KIND_NETWORK]) from exc

    if resp.status_code in (301, 302, 303, 307, 308):
        raise QoderApiError(KIND_API_ERROR, "API 返回重定向，出于 Token 安全已拒绝跟随", resp.status_code)

    status = resp.status_code
    body_bytes = getattr(resp, "content", b"") or b""
    if len(body_bytes) > MAX_BODY_BYTES:
        raise QoderApiError(KIND_API_ERROR, "API 响应体超过 2MB 安全上限，已丢弃", status)
    raw_text = body_bytes.decode("utf-8", errors="replace")
    detail = _mask_token(raw_text[:200])

    if status == 401:
        raise QoderApiError(KIND_AUTH_FAILED, _LABELS[KIND_AUTH_FAILED], status)
    if status == 403:
        raise QoderApiError(KIND_PERMISSION_DENIED, _LABELS[KIND_PERMISSION_DENIED], status)
    if status == 402 or (status >= 400 and _CREDIT_HINT_RE.search(detail)):
        raise QoderApiError(KIND_INSUFFICIENT_CREDITS, _LABELS[KIND_INSUFFICIENT_CREDITS], status)
    if status == 429:
        raise QoderApiError(KIND_RATE_LIMITED, _LABELS[KIND_RATE_LIMITED], status)
    if status >= 400:
        raise QoderApiError(KIND_API_ERROR, f"API 返回 HTTP {status}：{detail}", status)

    try:
        return resp.json()
    except ValueError as exc:
        raise QoderApiError(KIND_API_ERROR, f"API 返回非 JSON 响应：{detail}", status) from exc


def check_config() -> dict:
    """本地配置完整性检查，不发起任何网络请求，也不外露 Token 内容。"""
    missing = []
    if not config.QODER_ACCESS_TOKEN:
        missing.append("QODER_ACCESS_TOKEN")
    if not config.QODER_API_BASE_URL.startswith("https://"):
        missing.append("QODER_API_BASE_URL(需 https://)")
    if not config.QODER_MODEL:
        missing.append("QODER_MODEL")
    return {
        "configured": not missing,
        "missing": missing,
        "api_base_url": config.QODER_API_BASE_URL,
        "openapi_base_url": config.QODER_OPENAPI_BASE_URL,
        "model": config.QODER_MODEL,
        "timeout_seconds": config.QODER_TIMEOUT,
        "token_present": bool(config.QODER_ACCESS_TOKEN),
    }


def list_environments() -> dict:
    data = _request("/api/v1/cloud/environments")
    items = data.get("data") or []
    return {
        "environments": [
            {"id": e.get("id"), "name": e.get("name"), "status": e.get("status")}
            for e in items
            if isinstance(e, dict)
        ],
        "has_more": bool(data.get("has_more")),
    }


def list_models() -> dict:
    data = _request("/api/v1/cloud/models")
    items = data.get("data") or []
    models = []
    for m in items:
        if isinstance(m, dict):
            models.append({"id": m.get("id"), "enabled": m.get("enabled", True)})
    wanted = config.QODER_MODEL
    available = any(m["id"] == wanted and m["enabled"] for m in models)
    return {"models": models, "requested_model": wanted, "requested_model_available": available}


def _check(fn) -> dict:
    try:
        out = fn()
        out["ok"] = True
        return out
    except QoderApiError as exc:
        return {"ok": False, **exc.info()}


def connectivity_report() -> dict:
    """第一阶段只读体检：配置完整性 + PAT 认证 + 环境列表 + 模型可用性。"""
    started = time.perf_counter()
    cfg = check_config()
    report: dict = {
        "provider": "qoder_cloud_agents",
        "api_style": "Agent/Session/Event（非 OpenAI Chat Completions）",
        "readonly": True,
        "config": cfg,
        "configured": cfg["configured"],
        "auth_verified": None,
        "checks": {},
        "error": None,
    }
    if not cfg["configured"]:
        report["auth_verified"] = False
        report["error"] = {"kind": KIND_NOT_CONFIGURED, "message": _LABELS[KIND_NOT_CONFIGURED]}
        report["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return report

    env_check = _check(list_environments)
    report["checks"]["environments"] = env_check
    if env_check["ok"]:
        report["auth_verified"] = True
    else:
        report["auth_verified"] = False
        report["error"] = {
            "kind": env_check["kind"],
            "message": env_check["message"],
            "http_status": env_check.get("http_status"),
        }

    # 模型列表同为只读请求；仅在认证已通过或失败原因非网络类时补充信息
    model_check = _check(list_models)
    report["checks"]["models"] = model_check

    report["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    logger.info(
        "qoder health check provider=qoder_cloud_agents auth_verified=%s error_kind=%s elapsed_ms=%s",
        report["auth_verified"],
        (report.get("error") or {}).get("kind", "-"),
        report["elapsed_ms"],
    )
    return report
