"""模拟考试生成（六题型 × 难度 × 认知层次 × 章节范围）+ 生成后质量审核。

- 题型：single/multi/judge/fill/short/comprehensive
- 难度：basic/medium/hard/challenge；认知层次（Bloom）：remember..create，二者相互独立
- 干扰项要求来自易混概念/条件颠倒等，禁止“以上都是”类填充（规则审核强制检查）
- 审核不合格的题目重生成一次，仍不合格则标记并排除，不出现在正式卷面
"""

from __future__ import annotations

import json

from app.core import retrieval
from app.core.errors import ApiException
from app.core.providers import GenerationRequest, run
from app.modules.review import rules as R
from app.modules.review.service import audit

VALID_TYPES = R.TYPES
DIFFICULTIES = R.DIFFICULTIES
COGNITIVE_LEVELS = R.COGNITIVE_LEVELS

SYSTEM = (
    "你是大学命题老师。只依据给定课件片段命题，覆盖重点且不超纲；"
    "干扰项必须来自易混淆概念、相近定义、适用条件错误、因果颠倒、数值混淆或常见理解偏差，"
    "禁止使用「以上都是」「以上均不对」等无信息量填充，禁止把「正确答案」「干扰项」写进题干或选项。"
    "每道题给出：正确答案解析、每个错误选项为何错误、对应知识点、原文来源定位（逐字使用片段标签）、"
    "难度与认知层次（两者独立判断）。严格输出 JSON，不要输出其他文字。"
)


def _schema(types: list[str]) -> str:
    common = '"type": "single|multi|judge|fill|short|comprehensive", "stem": 题干, "knowledge_point": 知识点, "location": 原文定位标签, "difficulty": "basic|medium|hard|challenge", "cognitive": "remember|understand|apply|analyze|evaluate|create"'
    return (
        '输出 JSON：{"questions": [{ ' + common + ' , '
        '"options": [{"label":"A","text":"选项内容"}], "answer": ["A"], '
        '"explanation": 正确答案解析, "wrong_option_notes": [{"label":"B","why_wrong": 为何错误}], '
        '"answers": ["填空可接受答案"], "reference_answer": 参考答案, "scoring_points": ["评分要点"]}'
        ']}\n规则：'
        "选择题 answer 的 label 必须来自 options；单选恰好 1 项，多选至少 2 项；"
        "判断题 options 固定为 正确/错误；填空题 stem 含 ____ 且给 answers；"
        "简答题/综合应用题给 reference_answer 与 scoring_points（至少 2 条），options 留空数组；"
        "location 必须逐字使用片段方括号中的标签；认知层次按题目真实要求判断，不等于难度。"
    )


def _normalize(raw: dict, allowed_labels: set[str], allowed_pages: set[int]) -> dict | None:
    if not isinstance(raw, dict) or not raw.get("stem"):
        return None
    qtype = raw.get("type") if raw.get("type") in VALID_TYPES else "single"
    options = [
        {"label": str(o.get("label", "")).upper(), "text": str(o.get("text", "")).strip()}
        for o in (raw.get("options") or []) if isinstance(o, dict)
    ]
    options = [o for o in options if o["label"]]
    labels = {o["label"] for o in options}
    answer = [str(a).upper() for a in (raw.get("answer") or []) if str(a).upper() in labels]
    loc = str(raw.get("location") or "")
    if allowed_labels and loc and loc not in allowed_labels:
        loc = loc  # 保留原值，由审核规则标记“编造来源”
    q: dict = {
        "type": qtype,
        "stem": str(raw["stem"])[:1500],
        "options": options,
        "answer": answer,
        "explanation": str(raw.get("explanation") or ""),
        "wrong_option_notes": [
            {"label": str(n.get("label", "")).upper(), "why_wrong": str(n.get("why_wrong") or "")}
            for n in (raw.get("wrong_option_notes") or []) if isinstance(n, dict)
        ],
        "knowledge_point": str(raw.get("knowledge_point") or "")[:80],
        "location": loc,
        "pages": [p for p in (raw.get("pages") or []) if isinstance(p, int) and p in allowed_pages],
        "difficulty": raw.get("difficulty") if raw.get("difficulty") in DIFFICULTIES else "medium",
        "cognitive": raw.get("cognitive") if raw.get("cognitive") in COGNITIVE_LEVELS else "understand",
    }
    if qtype == "fill":
        q["answers"] = [str(a) for a in (raw.get("answers") or answer) if str(a)]
    if qtype in ("short", "comprehensive"):
        q["reference_answer"] = str(raw.get("reference_answer") or "")
        q["scoring_points"] = [str(s) for s in (raw.get("scoring_points") or [])][:8]
    return q


def generate(doc: dict, params: dict) -> dict:
    retrieval.guard_size(doc)
    count = int(params.get("count", 5))
    if not 1 <= count <= 20:
        raise ApiException("INVALID_COUNT", "题目数量需在 1-20 之间")
    types = [t for t in (params.get("types") or ["single"]) if t in VALID_TYPES]
    if not types:
        raise ApiException(
            "INVALID_TYPES",
            "请至少选择一种题型：single/multi/judge/fill/short/comprehensive",
        )
    difficulty = params.get("difficulty") if params.get("difficulty") in DIFFICULTIES else None
    cognitive = params.get("cognitive") if params.get("cognitive") in COGNITIVE_LEVELS else None
    chapters = params.get("chapters") or []

    evidence = retrieval.sample_chunks(
        doc, max_chunks=min(12, count * 2 + 2), sections=[str(c)[:60] for c in chapters]
    )
    if not evidence:
        raise ApiException(
            "NO_EVIDENCE",
            "所选章节没有可命题的内容，请更换章节或先上传课件",
            422,
        )
    allowed_labels = {c.get("location_label") for c in evidence if c.get("location_label")}
    allowed_pages = retrieval.valid_pages(doc)

    def _gen(want: int, feedback: str = "", offset: int = 0) -> tuple[list[dict], dict]:
        prompt = (
            f"课件《{doc['filename']}》以下为带来源定位的课件片段：\n{retrieval.render(evidence)}\n\n"
            f"请生成 {want} 道题，题型覆盖：{'、'.join(types)}。"
            + (("难度统一为 " + difficulty + "。") if difficulty else "")
            + ((f"认知层次为 {cognitive}。") if cognitive else "")
            + (f"\n上一轮以下问题未通过审核，请避免同类问题并重新命题：{feedback}" if feedback else "")
            + "\n\n" + _schema(types)
        )
        result = run(
            GenerationRequest(
                task="exam_questions", prompt=prompt, system=SYSTEM, evidence=evidence,
                params={"count": want, "types": types, "difficulty": difficulty, "cognitive": cognitive, "offset": offset},
            )
        )
        raw_list = result.data.get("questions") or result.data.get("items") or []
        qs = []
        for raw in raw_list:
            q = _normalize(raw, allowed_labels, allowed_pages)
            if q:
                qs.append(q)
        return qs, result.info()

    questions, provider_info = _gen(count)
    if not questions:
        raise ApiException("LLM_ERROR", "AI 未能生成有效题目，请重试", 502)

    def _blockers(issues: list[str]) -> list[str]:
        return [x for x in issues if not x.startswith("warning:")]

    audit_out = audit(questions, evidence)
    failed = {i for i, issues in enumerate(audit_out["issues"]) if _blockers(issues)}
    regenerated = 0
    if failed:
        keep = [q for i, q in enumerate(questions) if i not in failed]
        need = max(count - len(keep), len(failed))
        feedback = "; ".join(
            f"题{i + 1}：{'，'.join(audit_out['issues'][i])}" for i in sorted(failed)
        )[:2000]
        retry_qs, provider_info = _gen(need, feedback, offset=count)
        regenerated = len(retry_qs)
        candidates = (keep + retry_qs)[: max(count, len(keep))]
        questions = candidates
        audit_out = audit(candidates, evidence)
    else:
        questions = questions[:count]

    final_issues = audit_out["issues"]
    passed, excluded = [], []
    for i, q in enumerate(questions):
        entry = dict(q)
        issues = final_issues[i] if i < len(final_issues) else []
        if _blockers(issues):
            entry["quality"] = {"status": "excluded", "issues": issues}
            excluded.append(entry)
        else:
            entry["quality"] = {"status": "passed_with_warnings" if issues else "passed", "issues": issues}
            passed.append(entry)
    for n, q in enumerate(passed, start=1):
        q["id"] = n
    return {
        "questions": passed[:count],
        "excluded": excluded,
        "review": {
            "checked": len(questions),
            "passed": len(passed),
            "excluded": len(excluded),
            "regenerated": regenerated,
            "audit_provider": audit_out["provider"],
            "rule_only_fallback": audit_out["rule_only"],
        },
        "params": {"count": count, "types": types, "difficulty": difficulty,
                   "cognitive": cognitive, "chapters": chapters},
        "provider": provider_info,
        "evidence_chunks": len(evidence),
    }
