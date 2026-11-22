import os
import re
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# 必须在导入 app 之前设置：测试用独立缓存目录，默认走 Mock，不读取任何真实 Key
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ai-study-test-")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = BACKEND_ROOT / "scripts" / "samples"


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_doc(client) -> dict:
    resp = client.post("/api/documents", files={"file": ("normal.pdf", (SAMPLES / "normal.pdf").read_bytes())})
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def evidence():
    return [
        {"doc_id": "testdoc", "page_no": 1, "index": 0, "text": "Chapter 1: Newton's Laws of Motion. Key formula: F = m * a (second law)."},
        {"doc_id": "testdoc", "page_no": 2, "index": 0, "text": "Chapter 2: Conservation of Energy. Total mechanical energy E = K + U is conserved."},
        {"doc_id": "testdoc", "page_no": 3, "index": 0, "text": "Chapter 3: Friction force f = mu * N opposes relative motion."},
    ]
