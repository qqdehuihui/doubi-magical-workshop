"""统一文档数据结构 Document / DocumentBlock。

- 所有格式解析结果都转成 blocks，业务层（考点/出题/问答/题库）只依赖统一结构
- 定位规则：PDF=page_number，PPTX=slide_number，DOCX=heading_path/paragraph_index/table_index
- 不同格式的来源编号绝不混用；location_label 供提示词与前端展示
"""

from __future__ import annotations

import re

LOC_PAGE = "page_number"
LOC_SLIDE = "slide_number"
LOC_HEADING = "heading_path"
LOC_TABLE = "table_index"

_UNIT_LABEL = {"pdf": "页", "pptx": "幻灯片", "docx": "文档块"}


def make_block(
    document_id: str,
    content: str,
    block_type: str,
    location_type: str,
    location_value,
    sequence: int,
    section_title: str | None = None,
) -> dict:
    return {
        "block_id": f"{document_id}-b{sequence}",
        "document_id": document_id,
        "content": content,
        "block_type": block_type,
        "section_title": section_title,
        "location_type": location_type,
        "location_value": location_value,
        "location_label": location_label(location_type, location_value, section_title),
        "sequence": sequence,
    }


def location_label(location_type: str, location_value, section_title: str | None = None) -> str:
    if location_type == LOC_PAGE:
        return f"第{location_value}页"
    if location_type == LOC_SLIDE:
        return f"第{location_value}张幻灯片"
    if location_type == LOC_TABLE:
        base = section_title or "文档"
        return f"{base} / 表格{location_value}"
    if location_type == LOC_HEADING:
        path = str(location_value)
        if "/" in path:
            path = path.split("/", 1)[1]
        return f"章节 {path}"
    return str(location_value)


_CJK_NUM = "零一二三四五六七八九十百千两"
_CHAPTER_RE_PDF = re.compile(
    rf"^\s*((?:第[{_CJK_NUM}\d]+(?:章|节|部分))[\s.、:：]*(?:\S{{1,30}})?|Chapter\s+\d+[^\n]{{0,30}})"
)


def detect_pdf_sections(pages: list[dict]) -> list[dict]:
    """从 PDF 页文本中识别章/节标题，返回 [{title, start_page, end_page}]（尽力而为，识别不到则为空）。"""
    found: list[tuple[str, int]] = []
    for page in pages:
        for line in page["text"].splitlines()[:6]:
            m = _CHAPTER_RE_PDF.match(line.strip())
            if m and m.group(1).strip():
                title = re.sub(r"\s+", " ", m.group(1).strip())
                if not found or found[-1][1] != page["no"]:
                    found.append((title, page["no"]))
                break
    sections = []
    for i, (title, start) in enumerate(found):
        end = found[i + 1][1] - 1 if i + 1 < len(found) else pages[-1]["no"] if pages else start
        sections.append({"title": title, "start_page": start, "end_page": max(start, end)})
    return sections


def summarize_doc(doc_id: str, filename: str, file_type: str, blocks: list[dict]) -> dict:
    """由 blocks 组装统一文档对象。"""
    total_chars = sum(len(b["content"]) for b in blocks)
    unit_values = []
    for b in blocks:
        v = (b["location_type"], b["location_value"])
        if v not in unit_values:
            unit_values.append(v)
    unit_count = len(unit_values)
    sections: list[dict] = []
    if file_type == "docx":
        seen_titles: list[str] = []
        for b in blocks:
            t = b.get("section_title")
            if b["block_type"] == "heading" and t and t not in seen_titles:
                seen_titles.append(t)
        sections = [{"title": t, "path": t} for t in seen_titles]
    elif file_type == "pptx":
        titles: dict[int, str] = {}
        for b in blocks:
            if b["block_type"] == "title" and isinstance(b["location_value"], int):
                titles.setdefault(b["location_value"], b["content"][:60])
        sections = [
            {"title": titles[n] if n in titles else f"第{n}张幻灯片", "slide": n}
            for n in sorted({b["location_value"] for b in blocks if isinstance(b["location_value"], int)})
        ]
    pages = []
    if file_type == "pdf":
        by_page: dict[int, list[str]] = {}
        for b in blocks:
            if isinstance(b["location_value"], int):
                by_page.setdefault(b["location_value"], []).append(b["content"])
        pages = [{"no": n, "text": "\n".join(t)} for n, t in sorted(by_page.items())]
        sections = detect_pdf_sections(pages)

    return {
        "doc_id": doc_id,
        "document_id": doc_id,
        "filename": filename,
        "file_type": file_type,
        "schema_version": 2,
        "unit_count": unit_count,
        "unit_label": _UNIT_LABEL.get(file_type, "块"),
        "page_count": unit_count if file_type == "pdf" else len([v for v in unit_values if v[0] == LOC_SLIDE]),
        "total_chars": total_chars,
        "sections": sections,
        "pages": pages,
        "blocks": blocks,
    }
