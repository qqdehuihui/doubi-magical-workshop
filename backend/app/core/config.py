import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


MAX_FILE_MB = _num("MAX_FILE_MB", 50)
MAX_FILE_BYTES = int(MAX_FILE_MB * 1024 * 1024)
MAX_GEN_CHARS = int(_num("MAX_GEN_CHARS", 60000))

DATA_DIR = Path(os.getenv("DATA_DIR") or (REPO_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "mock").strip().lower()
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
LLM_TIMEOUT = _num("LLM_TIMEOUT", 90)

# Qoder CN Cloud Agents（Agent/Session/Event API，与 OpenAI 接口互不相干）
QODER_ACCESS_TOKEN = os.getenv("QODER_ACCESS_TOKEN", "").strip()
QODER_API_BASE_URL = (os.getenv("QODER_API_BASE_URL") or "https://api.qoder.com.cn").strip().rstrip("/")
QODER_OPENAPI_BASE_URL = (os.getenv("QODER_OPENAPI_BASE_URL") or "https://openapi.qoder.com.cn").strip().rstrip("/")
QODER_MODEL = (os.getenv("QODER_MODEL") or "ultimate").strip() or "ultimate"
QODER_TIMEOUT = _num("QODER_TIMEOUT", 20)
