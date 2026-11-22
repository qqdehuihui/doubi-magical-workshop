"""统一文档解析入口：按扩展名+内容魔数分派 PDF / PPTX / DOCX 解析器。

- 输出统一 DocumentBlock 结构（见 blocks.summarize_doc）
- .ppt/.doc 明确拒绝并提示另存为新格式
- 解析不到任何文字 → EMPTY_DOCUMENT（图片型内容需 OCR，当前未支持，不谎报成功）
"""

from __future__ import annotations

import io
import re
import zipfile

from app.core import config
from app.core.documents.blocks import (
    LOC_HEADING,
    LOC_PAGE,
    LOC_SLIDE,
    LOC_TABLE,
    make_block,
    summarize_doc,
)
from app.core.errors import ApiException

MIN_TEXT_CHARS = 30

SUPPORTED_EXTS = {".pdf": "pdf", ".pptx": "pptx", ".docx": "docx"}
LEGACY_EXTS = {".ppt": "PowerPoint 97-2003 (.ppt)", ".doc": "Word 97-2003 (.doc)"}


def sniff_format(data: bytes, filename: str) -> str:
    ext = ""
    lower = (filename or "").lower()
    for known in list(SUPPORTED_EXTS) + list(LEGACY_EXTS):
        if lower.endswith(known):
            ext = known
            break
    if data[:5].startswith(b"%PDF"):
        return "pdf"
    if data[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except Exception as exc:
            raise ApiException("INVALID_FILE", "文件已损坏或不是有效的 Office 文档", 415) from exc
        if any(n.startswith("ppt/") for n in names):
            return "pptx"
        if any(n.startswith("word/") for n in names) or any(
            n == "word/document.xml" for n in names
        ):
            return "docx"
        raise ApiException("UNSUPPORTED_FORMAT", "压缩包内未找到 PowerPoint/Word 文档结构，请确认文件为 .pptx 或 .docx")
    if ext in LEGACY_EXTS:
        raise ApiException(
            "UNSUPPORTED_FORMAT",
            f"暂不支持旧版 Office 格式（{LEGACY_EXTS[ext]}）。请在 Office/WPS 中「另存为」.pptx 或 .docx 后上传",
            415,
        )
    if ext in SUPPORTED_EXTS:
        raise ApiException("INVALID_FILE", f"文件扩展名为 {ext}，但内容不是有效的该格式文件（可能已损坏）", 415)
    raise ApiException(
        "UNSUPPORTED_FORMAT",
        "目前仅支持 PDF（.pdf）、PowerPoint（.pptx）、Word（.docx）三种格式",
        415,
    )


def validate_upload(data: bytes, filename: str) -> str:
    if not data:
        raise ApiException("EMPTY_FILE", "文件为空，请检查后重新上传")
    if len(data) > config.MAX_FILE_BYTES:
        raise ApiException("FILE_TOO_LARGE", f"文件超过 {config.MAX_FILE_MB:g}MB 限制", 413)
    return sniff_format(data, filename)


class PdfParser:
    @staticmethod
    def parse(data: bytes, doc_id: str, filename: str) -> dict:
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
        except ApiException:
            raise
        except Exception as exc:
            raise ApiException("INVALID_PDF", "PDF 文件已损坏或格式不正确，无法解析") from exc
        if not pages:
            raise ApiException("EMPTY_PDF", "PDF 中没有任何页面")
        total = sum(len(t) for _, t in pages)
        if total < MIN_TEXT_CHARS:
            raise ApiException(
                "SCANNED_PDF",
                "几乎未提取到文字，可能是扫描版/图片型 PDF，当前版本暂不支持 OCR 识别",
                415,
            )
        blocks = []
        seq = 0
        for no, text in pages:
            if not text:
                continue
            blocks.append(make_block(doc_id, text, "text", LOC_PAGE, no, seq))
            seq += 1
        return summarize_doc(doc_id, filename, "pdf", blocks)


class PptxParser:
    @staticmethod
    def parse(data: bytes, doc_id: str, filename: str) -> dict:
        from pptx import Presentation

        try:
            prs = Presentation(io.BytesIO(data))
        except Exception as exc:
            raise ApiException("INVALID_FILE", "PPTX 文件已损坏或格式不正确，无法解析", 415) from exc
        blocks: list[dict] = []
        seq = 0
        for slide_no, slide in enumerate(prs.slides, start=1):
            for shape in slide.shapes:
                if shape.has_table:
                    rows = [
                        " | ".join((cell.text or "").strip() for cell in row.cells)
                        for row in shape.table.rows
                    ]
                    rows = [r for r in rows if r.strip(" |")]
                    if rows:
                        blocks.append(
                            make_block(doc_id, "\n".join(rows), "table", LOC_SLIDE, slide_no, seq)
                        )
                        seq += 1
                    continue
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip() or (para.text or "").strip()
                    if not text:
                        continue
                    is_title_shape = False
                    try:
                        title_shape = slide.shapes.title
                        is_title_shape = title_shape is not None and shape._element is title_shape._element
                    except Exception:
                        is_title_shape = False
                    btype = "title" if is_title_shape and len(text) <= 60 else "text"
                    blocks.append(make_block(doc_id, text, btype, LOC_SLIDE, slide_no, seq, section_title=_slide_title(slide)))
                    seq += 1
        if not blocks:
            raise ApiException(
                "EMPTY_DOCUMENT",
                "PPTX 中未提取到文字内容（可能是纯图片幻灯片），图片 OCR 暂未支持",
                415,
            )
        return summarize_doc(doc_id, filename, "pptx", blocks)


def _slide_title(slide) -> str | None:
    try:
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            t = slide.shapes.title.text.strip()
            return t[:60] or None
    except Exception:
        return None
    return None


_HEADING_RE = re.compile(r"^(?:heading|标题)\s*(\d+)", re.IGNORECASE)


class DocxParser:
    @staticmethod
    def parse(data: bytes, doc_id: str, filename: str) -> dict:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph as DocxParagraph

        try:
            document = Document(io.BytesIO(data))
        except Exception as exc:
            raise ApiException("INVALID_FILE", "DOCX 文件已损坏或格式不正确，无法解析", 415) from exc

        blocks: list[dict] = []
        seq = 0
        heading_stack: list[tuple[int, str]] = []  # (level, title)
        para_index = 0
        table_index = 0

        def heading_path() -> str:
            parts = [t for _, t in heading_stack]
            return "/".join([filename] + parts) if parts else filename

        for child in document.element.body.iterchildren():
            if child.tag == qn("w:p"):
                para = DocxParagraph(child, document)
                text = (para.text or "").strip()
                style_name = ""
                try:
                    style_name = (para.style.name or "") if para.style is not None else ""
                except Exception:
                    style_name = ""
                m = _HEADING_RE.match(style_name) or _HEADING_RE.match(text[:10] if text else "")
                if m and text:
                    level = int(m.group(1))
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text[:80]))
                    blocks.append(
                        make_block(doc_id, text, "heading", LOC_HEADING, heading_path(), seq, section_title=text[:80])
                    )
                    seq += 1
                elif text:
                    blocks.append(
                        make_block(
                            doc_id,
                            text,
                            "text",
                            LOC_HEADING,
                            f"{heading_path()}/第{para_index + 1}段",
                            seq,
                            section_title=heading_stack[-1][1] if heading_stack else None,
                        )
                    )
                    seq += 1
                    para_index += 1
            elif child.tag == qn("w:tbl"):
                table = DocxTable(child, document)
                rows = []
                for row in table.rows:
                    cells = [(c.text or "").strip() for c in row.cells]
                    if any(cells):
                        rows.append(" | ".join(cells))
                table_index += 1
                if rows:
                    blocks.append(
                        make_block(
                            doc_id,
                            "\n".join(rows),
                            "table",
                            LOC_TABLE,
                            table_index,
                            seq,
                            section_title=heading_stack[-1][1] if heading_stack else None,
                        )
                    )
                    seq += 1

        if not blocks:
            raise ApiException(
                "EMPTY_DOCUMENT",
                "DOCX 中未提取到文字内容（可能是纯图片或空文档），图片 OCR 暂未支持",
                415,
            )
        total = sum(len(b["content"]) for b in blocks)
        if total < MIN_TEXT_CHARS:
            raise ApiException(
                "EMPTY_DOCUMENT",
                "DOCX 几乎未提取到文字，可能为图片型内容，图片 OCR 暂未支持",
                415,
            )
        return summarize_doc(doc_id, filename, "docx", blocks)


_PARSERS = {"pdf": PdfParser, "pptx": PptxParser, "docx": DocxParser}


def parse_document(data: bytes, filename: str, doc_id: str, file_type: str | None = None) -> dict:
    """统一解析入口：识别格式 → 分派解析器 → 统一 DocumentBlock 结构。"""
    fmt = file_type or sniff_format(data, filename)
    parser = _PARSERS.get(fmt)
    if parser is None:
        raise ApiException("UNSUPPORTED_FORMAT", f"暂不支持的文件格式：{fmt}")
    return parser.parse(data, doc_id, filename)
