"""题目质量审核编排：确定性规则 + Provider 语义审查，两者结果合并。

Mock 模式下 Provider 审查即规则审查（如实标注，不冒充真实模型语义审查）；
真实模式下额外获得模型对多答案/歧义/超纲等语义问题的判断。
"""

from __future__ import annotations

import json

from app.core.providers import GenerationRequest, run
from app.modules.review import rules as R


def audit(questions: list[dict], evidence: list[dict]) -> dict:
    """返回 {"issues": [每题问题列表], "provider": info}"""
    evidence_texts = [c["text"] for c in evidence]
    evidence_labels = {c.get("location_label") for c in evidence if c.get("location_label")}
    rule_issues = [R.check_question(q, evidence_texts, evidence_labels) for q in questions]
    for i, j in R.find_duplicates(questions):
        rule_issues[j].append(f"与第{i + 1}题高度重复")

    compact = [
        {"index": k, "stem": q.get("stem"), "type": q.get("type"),
         "options": q.get("options"), "answer": q.get("answer") or q.get("answers"),
         "location": q.get("location")}
        for k, q in enumerate(questions)
    ]
    prompt = (
        "请审核以下题目：1) 是否确实可能来源于所给课件证据；2) 是否存在多个正确答案或无正确答案；"
        "3) 干扰项是否合理（无『以上都是』类填充）；4) 是否存在歧义；5) 是否与原文矛盾；"
        "6) 是否与其他题目高度重复；7) 难度与认知层次是否合理。\n"
        f"题目：{json.dumps(compact, ensure_ascii=False)[:12000]}\n"
        '输出 JSON：{"reviews": [{"index": 题号, "issues": ["问题描述", ...]}]}，无问题的题 issues 为空数组。'
    )
    try:
        result = run(GenerationRequest(
            task="exam_review", prompt=prompt, evidence=evidence, params={"questions": questions},
        ))
    except Exception:
        result = None

    merged = [list(x) for x in rule_issues]
    provider_info = None
    if result is not None:
        provider_info = result.info()
        for rev in result.data.get("reviews") or []:
            if not isinstance(rev, dict):
                continue
            idx = rev.get("index")
            if isinstance(idx, int) and 0 <= idx < len(merged):
                for issue in rev.get("issues") or []:
                    text = str(issue)[:200]
                    if text and text not in merged[idx]:
                        merged[idx].append(text)
    return {"issues": merged, "provider": provider_info, "rule_only": result is None}
