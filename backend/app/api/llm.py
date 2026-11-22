"""GET /api/llm/health — Qoder CN Cloud Agents 第一阶段只读连通性检查。

只发起 GET 请求（environments/models），不创建资源、不触发模型推理、不消耗 Credits（失败的调用也不计费）。
响应中只包含配置完整性、认证结果、环境/模型摘要与错误分类，绝不包含 Token。
"""

from fastapi import APIRouter

from app.core import config
from app.core.qoder_client import connectivity_report

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/health")
def llm_health():
    report = connectivity_report()
    report["local_llm_provider"] = config.LLM_PROVIDER
    return report
