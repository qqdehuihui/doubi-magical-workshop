"""历年考试资料：从试卷/题库/提纲文本中提取题目并归一化考点。

原则：年份、题型、分值无法可靠识别时标记为“未知”，绝不猜测编造。
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

UNKNOWN = "未知"

_SECTION_TYPES = [
    (re.compile(r"多?项选择|多选题|选择题"), {"single", "multi"}),
    (re.compile(r"单项选择|单选题"), {"single"}),
    (re.compile(r"判断"), {"judge"}),
    (re.compile(r"填空"), {"fill"}),
    (re.compile(r"简答|问答"), {"short"}),
    (re.compile(r"论述|案例分析|综合应用|计算|证明"), {"comprehensive"}),
]

_QNUM_RE = re.compile(r"^\s*(\d{1,2})\s*[.、．]\s*(.*)$")
_SECTION_HEAD_RE = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、.．]\s*(.+)")
_OPTION_RE = re.compile(r"^\s*([A-HＡ-Ｈ])\s*[.、．:：]\s*(.+)$")
_SCORE_RE = re.compile(r"[（(]?\s*(\d{1,3})\s*分[)）]?")
_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})\s*年?")

_STOP_SUBSTR = [
    "下列", "关于", "正确", "错误", "的是", "下列哪", "根据", "请", "简述", "试述", "计算",
    "求", "已知", "以下", "哪些", "哪个", "选项", "判断", "填空", "选择", "问答", "题",
    "每小题", "共", "卷", "考试", "试卷", "大学", "学期", "课程", "姓名", "学号",
    "得分", "评卷人", "闭卷", "开卷", "注意事项", "答案",
    "表达", "描述", "指出", "关系", "内容", "公式", "适用", "条件", "填入", "填空",
    "每项", "每空", "如下", "哪些项", "说法", "表述", "下列各项", "完成", "表达式",
]
_CONNECTOR_SPLIT = re.compile(
    r"(?:\s|的|了|与|和|及|为|是|而|即|则|就|把|被|使|其|已|更|之|于|或|在|并且|或者|以及|已经|通过)"
)
_EDGE_STRIP = "的了与和及为是而即则就把使其已更之于或在，。；：、（）()____ "
_SCORE_MARK_RE = re.compile(r"[（(]\s*\d+\s*(?:分|pts|points?|marks?)\s*[）)]?")
_EN_STOP = {
    "the", "and", "for", "its", "are", "was", "were", "when", "that", "this", "which",
    "what", "how", "why", "is", "as", "of", "to", "in", "on", "by", "with", "not", "can",
    "will", "has", "have", "from", "pts", "point", "points", "marks", "following", "below",
    "about", "best", "most", "likely", "each", "all", "true", "false", "written", "stated",
    "described", "correct", "incorrect", "regarding", "choose", "select", "explain",
}


def detect_year(filename: str, text: str) -> int | None:
    """仅从文件名/卷头可靠提取年份；提取不到返回 None（未知）。"""
    for source in (filename or "", (text or "")[:600]):
        m = _YEAR_RE.search(source)
        if m:
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return y
    return None


def _section_type_guess(header: str | None) -> str:
    if not header:
        return "unknown"
    for rx, kinds in _SECTION_TYPES:
        if rx.search(header):
            if kinds == {"single", "multi"}:
                return "single_or_multi"
            return next(iter(kinds))
    return "unknown"


def _normalize_qtype(section_guess: str, options: list[dict], stem: str) -> str:
    has_options = len(options) >= 2
    if has_options:
        if section_guess == "single_or_multi":
            return "single"  # 无法确证多选时保守取单选语义，多选需题库自身标注
        if section_guess in ("single", "multi"):
            return section_guess
        return "single"
    if section_guess in ("judge", "fill", "short", "comprehensive"):
        return section_guess
    if re.search(r"^\s*判断|是否", stem) and not has_options:
        return "judge"
    if "____" in stem or re.search(r"[（(]\s*[)）]\s*$", stem):
        return "fill"
    return "unknown"


def _score_of(block_text: str) -> int | None:
    m = _SCORE_RE.search(block_text)
    return int(m.group(1)) if m else None


def point_candidates(stem: str) -> list[str]:
    """从题干提取考点候选词：先剔除分值标记与功能词，再按连接词切分为术语片段。"""
    text = _SCORE_MARK_RE.sub(" ", stem or "")
    words: list[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text):
        lw = w.lower()
        if len(lw) >= 3 and lw not in _EN_STOP:
            words.append(lw)
    for seg in re.split(r"[^一-鿿]+", text):
        buf = seg
        for sw in _STOP_SUBSTR:
            buf = buf.replace(sw, " ")
        for part in _CONNECTOR_SPLIT.split(buf):
            part = part.strip(_EDGE_STRIP)
            if 2 <= len(part) <= 8:
                words.append(part)
    seen: list[str] = []
    for w in words:
        if w not in seen:
            seen.append(w)
    return seen


def point_key(stem: str) -> str:
    cands = point_candidates(stem)
    key_terms = sorted(cands[:4])
    return "|".join(key_terms) if key_terms else "misc"


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class PointNormalizer:
    """考点归一化：同一知识点因表达不同被分开统计时合并。

    合并条件：key 相同 / key 相似度≥0.75 / 规范名与别名相似 / 共享一个≥3字的术语片段。
    规范名取组内出现频次最高的候选词（同频取更长者），不做任何“高频”推断。
    """

    def __init__(self):
        self.canonical: list[dict] = []  # {name, key, aliases:set, counts:Counter}

    def normalize(self, stem: str) -> tuple[str, str]:
        cands = point_candidates(stem)
        if not cands:
            return "综合考点", "misc"
        key = "|".join(sorted(cands[:4]))
        cjk = [c for c in cands if re.search(r"[一-鿿]", c)]
        label = max(cjk or cands, key=lambda x: (len(x) <= 8, len(x)))
        for item in self.canonical:
            if (
                item["key"] == key
                or _similar(item["key"], key) >= 0.75
                or any(_similar(alias, label) >= 0.75 for alias in item["aliases"])
                or any(len(c) >= 3 and c in item["counts"] for c in cands)
            ):
                item["counts"].update(cands)
                item["aliases"] |= set(cands)
                item["name"] = max(item["counts"], key=lambda n: (item["counts"][n], len(n)))
                return item["name"], item["key"]
        self.canonical.append({"name": label, "key": key, "aliases": {label}, "counts": Counter(cands)})
        return label, key


def extract_questions(doc: dict) -> list[dict]:
    """把考试资料文档拆成题目记录列表。"""
    normalizer = PointNormalizer()
    questions: list[dict] = []
    lines: list[tuple[str, str]] = []  # (line, location_label)
    if doc.get("blocks"):
        for b in doc["blocks"]:
            for line in (b["content"] or "").splitlines():
                lines.append((line.strip(), b["location_label"]))
    else:
        for p in doc.get("pages", []):
            for line in p["text"].splitlines():
                lines.append((line.strip(), f"第{p['no']}页"))

    header_guess: str | None = None
    pending: dict | None = None
    year = detect_year(doc.get("filename", ""), "\n".join(l for l, _ in lines[:40]))

    def flush(q: dict | None):
        if not q:
            return
        stem = re.sub(r"\s+", " ", q["stem"]).strip()
        if len(stem) < 6:
            return
        score = _score_of(stem + " " + (q.get("tail") or ""))
        qtype = _normalize_qtype(q.get("section", "unknown"), q["options"], stem)
        name, key = normalizer.normalize(stem)
        questions.append(
            {
                "qnum": len(questions) + 1,
                "stem": stem[:1500],
                "options": q["options"],
                "qtype": qtype,
                "score": score,
                "year": year,
                "point": name,
                "point_key": key,
                "location": q["location"],
                "exam_doc_id": doc["doc_id"],
                "filename": doc.get("filename"),
                "course_id": doc.get("course_id"),
            }
        )

    for line, loc in lines:
        m_head = _SECTION_HEAD_RE.match(line)
        if m_head and len(line) <= 40:
            flush(pending)
            pending = None
            header_guess = _section_type_guess(m_head.group(1))
            continue
        m_q = _QNUM_RE.match(line)
        m_o = _OPTION_RE.match(line)
        if m_q and not m_o:
            flush(pending)
            pending = {
                "stem": m_q.group(2),
                "options": [],
                "section": header_guess,
                "location": loc,
                "tail": "",
            }
            continue
        if pending is not None:
            if m_o and len(m_o.group(2)) < 300:
                pending["options"].append({"label": m_o.group(1).upper(), "text": m_o.group(2)[:300]})
            else:
                pending["stem"] += " " + line
                pending["tail"] = (pending["tail"] + " " + line)[-60:]
            pending["stem"] = pending["stem"][:1500]
    flush(pending)
    # 归一化组名会随后续题目合并而变化，统一回写最终规范名，避免同一组留下新旧名
    final_names = {item["key"]: item["name"] for item in normalizer.canonical}
    for q in questions:
        q["point"] = final_names.get(q["point_key"], q["point"])
    return questions
