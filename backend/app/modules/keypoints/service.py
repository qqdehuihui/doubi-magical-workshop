"""重难点分析（五层结构）。

- 课程核心框架 / 核心知识点 / 重难点解析 / 可能考查内容：基于课件证据由 Provider 生成
- 历年高频考点：只由服务端从考试资料库统计注入，模型不得编造；无资料时返回固定提示
- 四个指标严格区分：课件强调度 emphasis、知识点重要性 importance、
  推测考查价值 priority、历史考试频率 historical_frequency（来自题库统计）
"""

from app.core import retrieval
from app.core.errors import ApiException
from app.core.providers import GenerationRequest, run
from app.modules.examdb import service as examdb

NO_HISTORY_NOTICE = (
    "当前仅基于教师课件分析，尚未导入历年考试资料，无法统计真实考频。"
    "上传往年试卷后可生成历年高频考点分析。"
)

SYSTEM = (
    "你是面向大学生的课程分析专家。只依据给定课件片段分析，不得编造片段之外的内容或来源。"
    "严格区分四类指标：课件强调度（片段中重复/突出程度）、知识点重要性（定义/公式/原理）、"
    "推测考查价值（基于强调度的复习优先级）、历史考试频率（只能来自另行提供的统计数据，"
    "未提供时必须说明无法统计）。严格输出 JSON，不要输出其他文字。"
)

SCHEMA = (
    "输出 JSON，包含四个键（历年高频考点由系统另行注入，你不要输出）："
    '{"course_framework": {"topic": 课程主题, "chapters": [{"title": 章节名, "location": 来源定位, "summary": 一句话摘要}], '
    '"relations": [{"from": 章节A, "to": 章节B, "relation": 逻辑关系}]}, '
    '"core_knowledge": [{"item": 知识点, "kind": "definition|principle|formula|conclusion", "content": 讲解, '
    '"location": 来源定位, "importance": "高|中|低", "emphasis": "高|中|低"}], '
    '"difficult_points": [{"item": 内容, "content": 解析, "why": ["需要重点理解|易混淆概念|复杂推导|常见理解错误"], '
    '"confusion": {"with": 易混对象, "difference": 区别}, "location": 来源定位}], '
    '"exam_predictions": [{"item": 内容, "priority": "高|中|低", "basis": ["依据：重复强调/章节总结/公式案例"], '
    '"location": 来源定位, "emphasis": "高|中|低", "note": 说明此为推测而非历史考频}]}'
    "。location 必须使用片段方括号中的原文定位标签，逐字一致。"
)


def generate(doc: dict) -> dict:
    retrieval.guard_size(doc)
    evidence = retrieval.sample_chunks(doc, max_chunks=10, budget=16000)
    if not evidence:
        raise ApiException("NO_EVIDENCE", "文档中没有可分析的文字内容", 422)

    headings = [
        b["content"][:60]
        for b in doc.get("blocks", [])
        if b.get("block_type") in ("heading", "title")
    ][:5]
    prompt = (
        f"课件《{doc['filename']}》（{doc.get('file_type', 'pdf')}，共 {doc.get('unit_count')} 个{doc.get('unit_label')}），"
        f"以下为带来源定位标签的课件片段：\n\n{retrieval.render(evidence)}\n\n"
        f"章节标题线索：{headings or doc.get('sections') or '（未在文中识别到显式标题，请依据片段归纳）'}\n\n"
        + SCHEMA
    )
    result = run(
        GenerationRequest(
            task="keypoints_v2",
            prompt=prompt,
            system=SYSTEM,
            evidence=evidence,
            params={"headings": headings, "sections": doc.get("sections") or []},
        )
    )
    data = result.data
    if data.get("insufficient_evidence"):
        raise ApiException("LLM_ERROR", "AI 未能基于证据完成分析，请重试", 502)

    allowed_labels = {c.get("location_label") for c in evidence if c.get("location_label")}
    allowed_pages = retrieval.valid_pages(doc)

    def _loc(item: dict) -> str:
        loc = str(item.get("location") or "")
        return loc if loc in allowed_labels or not allowed_labels else (loc or "（来源未标注）")

    def _pages(item: dict) -> list[int]:
        return [p for p in (item.get("pages") or []) if isinstance(p, int) and p in allowed_pages]

    framework = data.get("course_framework") or {}
    chapters = [
        {"title": str(c.get("title") or ""), "location": str(c.get("location") or ""), "summary": str(c.get("summary") or "")}
        for c in (framework.get("chapters") or [])
        if isinstance(c, dict) and c.get("title")
    ]
    core = []
    for c in data.get("core_knowledge") or []:
        if not isinstance(c, dict) or not c.get("item"):
            continue
        core.append({
            "item": str(c["item"])[:80], "kind": str(c.get("kind") or "key_fact"),
            "content": str(c.get("content") or ""), "location": _loc(c),
            "importance": c.get("importance") if c.get("importance") in ("高", "中", "低") else "中",
            "emphasis": c.get("emphasis") if c.get("emphasis") in ("高", "中", "低") else "中",
            "pages": _pages(c),
        })
    difficult = []
    for c in data.get("difficult_points") or []:
        if not isinstance(c, dict) or not c.get("item"):
            continue
        entry = {
            "item": str(c["item"])[:80], "content": str(c.get("content") or ""),
            "why": [str(w) for w in (c.get("why") or [])][:6], "location": _loc(c), "pages": _pages(c),
        }
        if isinstance(c.get("confusion"), dict):
            entry["confusion"] = {"with": str(c["confusion"].get("with") or ""), "difference": str(c["confusion"].get("difference") or "")}
        if isinstance(c.get("confusion"), list):
            entry["confusion"] = None
        difficult.append(entry)
    predictions = []
    for c in data.get("exam_predictions") or []:
        if not isinstance(c, dict) or not c.get("item"):
            continue
        predictions.append({
            "item": str(c["item"])[:80],
            "priority": c.get("priority") if c.get("priority") in ("高", "中", "低") else "中",
            "basis": [str(b) for b in (c.get("basis") or [])][:6],
            "location": _loc(c), "pages": _pages(c),
            "emphasis": c.get("emphasis") if c.get("emphasis") in ("高", "中", "低") else "中",
            "note": str(c.get("note") or "仅基于课件强调程度的推测，不代表历年真实考频"),
        })

    history = examdb.frequent_points(doc.get("course_id") or "default", doc_id=doc["doc_id"])
    historical_frequent = {
        "available": bool(history["available"]),
        "notice": history["notice"] or NO_HISTORY_NOTICE if not history["available"] else None,
        "items": history["points"] if history["available"] else [],
        "paper_count": history["paper_count"],
        "question_total": history["question_total"],
        "by_year": history["by_year"],
        "by_type": history["by_type"],
        "section_coverage": history["section_coverage"],
        "source": "examdb_statistics" if history["available"] else None,
    }

    return {
        "schema": "keypoints_v2",
        "course_framework": {
            "topic": str(framework.get("topic") or doc["filename"]),
            "chapters": chapters,
            "relations": [
                {"from": str(r.get("from") or ""), "to": str(r.get("to") or ""), "relation": str(r.get("relation") or "")}
                for r in (framework.get("relations") or []) if isinstance(r, dict)
            ],
        },
        "core_knowledge": core,
        "difficult_points": difficult,
        "exam_predictions": predictions,
        "historical_frequent": historical_frequent,
        "metrics_legend": {
            "emphasis": "课件强调度：内容在课件中的重复/突出程度",
            "importance": "知识点重要性：定义、原理、公式等知识属性",
            "priority": "推测考查价值：基于强调度的复习优先级（非统计结论）",
            "historical_frequency": "历史考试频率：仅来自已导入历年试卷/题库的真实统计，未导入则无法得出",
            "warning": "四个指标含义不同，不可混同使用",
        },
        "provider": result.info(),
        "evidence_chunks": len(evidence),
    }
