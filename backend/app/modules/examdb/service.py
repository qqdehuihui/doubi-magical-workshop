"""历年考试资料库：上传登记、统计与高频考点。

- 试卷/题库/提纲复用统一解析层，拆题后连同元数据保存（kind=exam）
- 统计完全来自真实导入资料；无资料时 available=False，供上层展示固定提示
- 年份/题型/分值无法识别时为“未知”，不参与猜测
"""

from __future__ import annotations

import json

from app.core import config, storage
from app.core.documents import parse_document, validate_upload
from app.core.errors import ApiException
from app.modules.examdb.extract import UNKNOWN, _similar, extract_questions

MATERIAL_TYPES = {"试卷": "exam_paper", "题库": "question_bank", "复习提纲": "outline",
                  "exam_paper": "exam_paper", "question_bank": "question_bank", "outline": "outline"}
_TYPE_LABEL = {"exam_paper": "试卷", "question_bank": "题库", "outline": "复习提纲", UNKNOWN: "未知"}
_QTYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断", "fill": "填空",
                "short": "简答", "comprehensive": "综合", "unknown": "未标注"}


def upload_exam(data: bytes, filename: str, course_id: str | None, material_type: str | None,
                year: int | None = None) -> dict:
    detected = validate_upload(data, filename)
    doc_id = storage.new_doc_id()
    parsed = parse_document(data, filename, doc_id, detected)
    doc = {
        **parsed,
        "kind": "exam",
        "course_id": (course_id or "").strip() or "default",
        "material_type": MATERIAL_TYPES.get((material_type or "").strip(), UNKNOWN),
        "year_input": year,
    }
    questions = extract_questions(doc)
    year = year if year is not None else (questions[0]["year"] if questions else None)
    doc["exam_year"] = year if year is not None else UNKNOWN
    doc["exam_questions"] = questions
    storage.save_document(doc)
    return {
        "exam_doc_id": doc_id,
        "filename": filename,
        "file_type": detected,
        "course_id": doc["course_id"],
        "material_type": _TYPE_LABEL[doc["material_type"]],
        "year": doc["exam_year"],
        "extracted_questions": len(questions),
        "note": None if questions else "未能从该资料中拆出题目，请确认为含文字的试卷/题库文本",
    }


def list_exams(course_id: str | None = None) -> dict:
    items = []
    for path in sorted(config.DATA_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if doc.get("kind") != "exam":
            continue
        if course_id and doc.get("course_id") != course_id:
            continue
        items.append(
            {
                "exam_doc_id": doc["doc_id"],
                "filename": doc["filename"],
                "file_type": doc.get("file_type"),
                "course_id": doc.get("course_id"),
                "material_type": _TYPE_LABEL.get(doc.get("material_type", UNKNOWN), UNKNOWN),
                "year": doc.get("exam_year", UNKNOWN),
                "question_count": len(doc.get("exam_questions", [])),
            }
        )
    return {"exams": items, "exam_count": len(items)}


def delete_exam(exam_doc_id: str) -> dict:
    doc = storage.load_document(exam_doc_id)
    if doc.get("kind") != "exam":
        raise ApiException("EXAM_NOT_FOUND", "该文档不是历年考试资料", 404)
    path = config.DATA_DIR / f"{exam_doc_id}.json"
    path.unlink(missing_ok=True)
    return {"deleted": exam_doc_id}


def frequent_points(course_id: str, doc_id: str | None = None) -> dict:
    """考点统计：总次数、年份分布、题型分布、分值、来源；可关联课件章节覆盖。"""
    points: dict[str, dict] = {}
    by_year: dict[str, int] = {}
    by_type: dict[str, int] = {}
    papers: list[dict] = []
    total_questions = 0
    for path in sorted(config.DATA_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if doc.get("kind") != "exam" or doc.get("course_id") != course_id:
            continue
        qs = doc.get("exam_questions", [])
        total_questions += len(qs)
        papers.append(
            {
                "exam_doc_id": doc["doc_id"],
                "filename": doc["filename"],
                "year": doc.get("exam_year", UNKNOWN),
                "material_type": _TYPE_LABEL.get(doc.get("material_type", UNKNOWN), UNKNOWN),
                "question_count": len(qs),
            }
        )
        for q in qs:
            name = q.get("point") or "综合考点"
            key = name  # 按规范名聚合，避免同一展示名因 key 不同拆成多行
            p = points.setdefault(
                key,
                {"point": name, "count": 0, "years": [], "types": {}, "scores": [], "sources": [], "question_samples": []},
            )
            p["count"] += 1
            year = q.get("year")
            ykey = str(year) if year else UNKNOWN
            by_year[ykey] = by_year.get(ykey, 0) + 1
            if ykey not in p["years"]:
                p["years"].append(ykey)
            tkey = q.get("qtype") or "unknown"
            p["types"][tkey] = p["types"].get(tkey, 0) + 1
            by_type[tkey] = by_type.get(tkey, 0) + 1
            if q.get("score") is not None:
                p["scores"].append(q["score"])
            if q.get("filename") and q["filename"] not in p["sources"]:
                p["sources"].append(q["filename"])
            if len(p["question_samples"]) < 2:
                p["question_samples"].append(q["stem"][:120])
    items = sorted(points.values(), key=lambda x: x["count"], reverse=True)
    # 跨试卷再合并一次：包含关系（取更长名）或高度相似的规范名视为同一考点
    merged: list[dict] = []
    for it in items:
        target = None
        for m in merged:
            a, b = m["point"], it["point"]
            if a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)) or _similar(a, b) >= 0.75:
                target = m
                break
        if target is None:
            merged.append(it)
        else:
            if len(it["point"]) > len(target["point"]):
                target["point"] = it["point"]
            target["count"] += it["count"]
            target["years"] += [y for y in it["years"] if y not in target["years"]]
            for k, v in it["types"].items():
                target["types"][k] = target["types"].get(k, 0) + v
            target["scores"] += it["scores"]
            target["sources"] += [s for s in it["sources"] if s not in target["sources"]]
            target["question_samples"] = (target["question_samples"] + it["question_samples"])[:2]
    items = merged
    for it in items:
        it["score_total"] = sum(it["scores"]) if it["scores"] else UNKNOWN
        known_years = [y for y in it["years"] if y != UNKNOWN]
        it["span"] = f"{min(known_years)}-{max(known_years)}" if known_years else UNKNOWN
        del it["scores"]
    section_cover = None
    if doc_id and items:
        try:
            course_doc = storage.load_document(doc_id)
        except ApiException:
            course_doc = None
        if course_doc:
            section_cover = _section_coverage(course_doc, items)
    return {
        "available": bool(papers and total_questions),
        "course_id": course_id,
        "papers": papers,
        "paper_count": len(papers),
        "question_total": total_questions,
        "by_year": by_year,
        "by_type": {"types": by_type, "labels": {k: _QTYPE_LABEL.get(k, k) for k in by_type}},
        "points": items,
        "section_coverage": section_cover,
        "notice": None
        if papers
        else "当前仅基于教师课件分析，尚未导入历年考试资料，无法统计真实考频。上传往年试卷后可生成历年高频考点分析。",
    }


_GENERIC_BIGRAMS = {"定律", "公式", "原理", "概念", "方法", "关系", "变化", "内容", "考点", "题"}


def _bigrams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _section_coverage(course_doc: dict, point_items: list[dict]) -> list[dict]:
    """考点与课件章节的对齐情况：二字词组交集（剔除“定律/公式”等泛化词）尽力匹配。"""
    sections = course_doc.get("sections") or []
    out = []
    for s in sections:
        title = s.get("title") or ""
        tb = _bigrams(title) - _GENERIC_BIGRAMS
        hit_points = []
        for p in point_items:
            pb = _bigrams(p.get("point") or "") - _GENERIC_BIGRAMS
            if len(tb & pb) >= 1:
                hit_points.append(p["point"])
        out.append({"section": title, "matched_points": hit_points, "matched_count": len(hit_points)})
    return out
