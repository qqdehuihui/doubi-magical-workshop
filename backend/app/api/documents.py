from fastapi import APIRouter, Form, UploadFile, File

from app.core import storage
from app.core.documents import parse_document, validate_upload

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _meta(doc: dict, excerpt_len: int = 0) -> dict:
    meta = {
        "doc_id": doc["doc_id"],
        "filename": doc["filename"],
        "file_type": doc.get("file_type", "pdf"),
        "page_count": doc.get("unit_count", doc.get("page_count", 0)),
        "unit_count": doc.get("unit_count", 0),
        "unit_label": doc.get("unit_label", "页"),
        "total_chars": doc["total_chars"],
        "course_id": doc.get("course_id"),
        "sections": (doc.get("sections") or [])[:40],
        "created_at": doc.get("created_at"),
    }
    if excerpt_len and doc.get("pages"):
        meta["pages"] = [
            {"no": p["no"], "text": p["text"][:excerpt_len]} for p in doc["pages"]
        ]
    return meta


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    course_id: str | None = Form(default=None, max_length=100),
):
    data = await file.read()
    filename = file.filename or "untitled"
    file_type = validate_upload(data, filename)
    doc_id = storage.new_doc_id()
    doc = {"course_id": (course_id or "").strip() or None, **parse_document(data, filename, doc_id, file_type)}
    storage.save_document(doc)
    return _meta(doc, excerpt_len=120)


@router.get("/{doc_id}")
def get_document(doc_id: str):
    doc = storage.load_document(doc_id)
    return _meta(doc, excerpt_len=300)
