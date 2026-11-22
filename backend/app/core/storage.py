import json
import re
import uuid
from datetime import datetime, timezone

from app.core import config
from app.core.errors import ApiException

_DOC_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_doc_id() -> str:
    return uuid.uuid4().hex


def _doc_path(doc_id: str):
    if not _DOC_ID_RE.match(doc_id):
        raise ApiException("DOC_NOT_FOUND", "文档不存在或已过期，请重新上传", 404)
    return config.DATA_DIR / f"{doc_id}.json"


def save_document(doc: dict) -> None:
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    _doc_path(doc["doc_id"]).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )


def load_document(doc_id: str) -> dict:
    path = _doc_path(doc_id)
    if not path.exists():
        raise ApiException("DOC_NOT_FOUND", "文档不存在或已过期，请重新上传", 404)
    return json.loads(path.read_text(encoding="utf-8"))
