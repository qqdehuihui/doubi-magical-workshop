from app.core import retrieval
from app.core.providers import GenerationRequest, run

NO_EVIDENCE_ANSWER = (
    "证据不足：在课件中未找到与该问题直接相关的内容，无法回答。"
    "请尝试换一种问法，或上传包含相关章节的课件。"
)

SYSTEM = (
    "你是大学生课件问答助手。只依据给定课件片段回答，简洁准确；"
    "片段不足以回答时必须明确说明证据不足，不得编造。"
    "来源定位必须逐字使用片段方括号中的标签，不得自行编号。"
    '严格输出 JSON：{"answer": 回答文本, "pages": [数值页/幻灯片编号], "locations": ["原文定位标签"]}'
)


def answer(doc: dict, question: str, history: list[dict]) -> dict:
    retrieval.guard_size(doc)
    evidence = retrieval.search(doc, question)
    if not evidence:
        return {
            "answer": NO_EVIDENCE_ANSWER,
            "cited_pages": [],
            "locations": [],
            "insufficient_evidence": True,
            "provider": {
                "name": "rule",
                "model": "-",
                "elapsed_ms": 0,
                "mock": False,
                "disclaimer": "检索未发现相关证据，已短路返回，未调用任何模型。",
            },
            "evidence_chunks": 0,
        }

    context = retrieval.render(evidence)[: retrieval.QA_CHAR_BUDGET]
    history_text = "\n".join(
        f"{h['role']}: {str(h['content'])[:500]}"
        for h in history[-4:]
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")
    )
    prompt = (
        f"课件《{doc['filename']}》相关片段如下：\n{context}\n\n"
        + (f"最近对话：\n{history_text}\n\n" if history_text else "")
        + f"问题：{question}"
    )
    result = run(GenerationRequest(task="qa", prompt=prompt, system=SYSTEM, evidence=evidence))
    data = result.data
    allowed = retrieval.valid_pages(doc)
    answer_text = str(data.get("answer") or "").strip()
    if not answer_text:
        from app.core.errors import ApiException

        raise ApiException("LLM_ERROR", "AI 未返回有效回答，请重试", 502)
    locations = [
        str(x)[:40] for x in (data.get("locations") or [])
        if isinstance(x, str) and x
    ] or retrieval.locations(evidence)
    return {
        "answer": answer_text,
        "cited_pages": [p for p in data.get("pages", data.get("cited_pages", [])) if isinstance(p, int) and p in allowed],
        "locations": locations[:8],
        "insufficient_evidence": bool(data.get("insufficient_evidence")),
        "provider": result.info(),
        "evidence_chunks": len(evidence),
    }
