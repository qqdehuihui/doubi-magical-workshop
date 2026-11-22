"""文档分块与关键词检索（基于统一 DocumentBlock 结构）。

- 片段携带 doc_id、位置信息（page_no/slide_no 为数值定位，label 为展示定位）与 sequence
- 检索仅用关键词匹配（MVP，无向量库），并限制上下文预算，绝不将整份文档一次性传给模型
- 旧版仅含 pages 的文档由 storage.load_document 自动升级为 blocks
"""

import re

from app.core import config

CHUNK_SIZE = 500
DEFAULT_TOP_K = 4
QA_CHAR_BUDGET = 8000

_ASCII_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _pieces(content: str):
    for start in range(0, len(content), CHUNK_SIZE):
        piece = content[start : start + CHUNK_SIZE].strip()
        if piece:
            yield piece


def build_chunks(doc: dict) -> list[dict]:
    chunks: list[dict] = []
    sections = doc.get("sections") or []

    def _sec_for(value) -> str | None:
        if not isinstance(value, int):
            return None
        for s in sections:
            if (
                isinstance(s.get("start_page"), int)
                and isinstance(s.get("end_page"), int)
                and s["start_page"] <= value <= s["end_page"]
            ):
                return s.get("title")
        return None

    blocks = doc.get("blocks")
    if blocks is None:
        blocks = [
            {
                "content": p["text"],
                "block_type": "text",
                "location_type": "page_number",
                "location_value": p["no"],
                "location_label": f"第{p['no']}页",
                "section_title": None,
                "sequence": i,
            }
            for i, p in enumerate(doc.get("pages", []))
        ]
    for block in sorted(blocks, key=lambda b: b.get("sequence", 0)):
        text = block.get("content") or ""
        if not text:
            continue
        loc_value = block.get("location_value")
        section = block.get("section_title") or _sec_for(loc_value)
        index = 0
        for piece in _pieces(text):
            chunks.append(
                {
                    "doc_id": doc["doc_id"],
                    "page_no": loc_value if isinstance(loc_value, int) else None,
                    "location_type": block.get("location_type"),
                    "location_value": loc_value,
                    "location_label": block.get("location_label") or "",
                    "section": section,
                    "block_type": block.get("block_type", "text"),
                    "sequence": block.get("sequence", 0),
                    "index": index,
                    "text": piece,
                }
            )
            index += 1
    return chunks


def _tokens(text: str) -> set[str]:
    tokens = {t.lower() for t in _ASCII_TOKEN.findall(text)}
    cjk = re.findall(r"[一-鿿]", text)
    tokens.update(a + b for a, b in zip(cjk, cjk[1:]))
    tokens.update(cjk)
    return tokens


def search(doc: dict, query: str, top_k: int = DEFAULT_TOP_K, budget: int = QA_CHAR_BUDGET) -> list[dict]:
    """返回与 query 相关的片段（按原文顺序），无相关证据时返回空列表。"""
    chunks = build_chunks(doc)
    grams = _tokens(query)
    if not grams or not chunks:
        return []
    scored = []
    for chunk in chunks:
        score = sum(chunk["text"].count(g) * len(g) for g in grams)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked: list[dict] = []
    used = 0
    for _, chunk in scored[: max(top_k, 1) * 2]:
        if len(picked) >= top_k or used + len(chunk["text"]) > budget:
            continue
        picked.append(chunk)
        used += len(chunk["text"])
    picked.sort(key=lambda c: (c["sequence"], c["index"]))
    return picked


def sample_chunks(doc: dict, max_chunks: int = 8, budget: int = 12000, sections: list[str] | None = None) -> list[dict]:
    """无查询场景（考点/出题）：均匀抽取覆盖全文的片段，受预算限制；可按章节标题过滤。"""
    chunks = build_chunks(doc)
    if sections:
        wanted = [s.strip() for s in sections if s and s.strip()]
        if wanted and not (len(wanted) == 1 and wanted[0] in ("all", "全部")):
            filtered = [
                c
                for c in chunks
                if any(
                    w.lower() in ((c.get("section") or "") + " " + (c.get("location_label") or "")).lower()
                    for w in wanted
                )
            ]
            chunks = filtered or []
    if not chunks:
        return []
    step = max(1, len(chunks) // max_chunks)
    picked = chunks[::step][:max_chunks]
    trimmed: list[dict] = []
    used = 0
    for chunk in picked:
        if used + len(chunk["text"]) > budget:
            break
        trimmed.append(chunk)
        used += len(chunk["text"])
    return trimmed or picked[:1]


def render(evidence: list[dict]) -> str:
    return "\n\n".join(f"[{c['location_label'] or f'第{c['page_no']}页'}]\n{c['text']}" for c in evidence)


def locations(evidence: list[dict]) -> list[str]:
    """证据片段的去重来源标签（第N页 / 第N张幻灯片 / 章节路径）。"""
    out: list[str] = []
    for c in evidence:
        label = c.get("location_label") or (f"第{c['page_no']}页" if c.get("page_no") else "")
        if label and label not in out:
            out.append(label)
    return out


def valid_pages(doc: dict) -> set[int]:
    return {
        b["location_value"]
        for b in doc.get("blocks", [])
        if isinstance(b.get("location_value"), int)
    } or {p["no"] for p in doc.get("pages", [])}


def guard_size(doc: dict) -> None:
    from app.core.errors import ApiException

    if doc["total_chars"] > config.MAX_GEN_CHARS:
        raise ApiException(
            "DOC_TOO_LONG",
            f"文档共 {doc['total_chars']} 字符，超过单次处理上限 "
            f"{config.MAX_GEN_CHARS}，建议按章节拆分后分别上传",
        )
