"""旧 PDF 解析入口（已并入统一解析层，此处仅为兼容壳，避免重复实现）。"""

from app.core.documents import parse_document
from app.core.documents.parsers import MIN_TEXT_CHARS, sniff_format, validate_upload as _validate


def validate_upload(data: bytes, filename: str = "untitled.pdf") -> None:
    _validate(data, filename)


def parse_pdf(data: bytes, filename: str) -> dict:
    doc = parse_document(data, filename, "pdf-doc", "pdf")
    # 兼容旧版调用方期望的扁平结构
    return {
        "filename": doc["filename"],
        "page_count": doc["unit_count"],
        "total_chars": doc["total_chars"],
        "pages": doc["pages"],
    }
