"""题目质量规则审核（确定性检查，与 Provider 审查互补）。

每条规则返回 issue 列表；空列表代表通过。规则不依赖任何模型，Mock/真实模式同样生效。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

TYPES = {"single", "multi", "judge", "fill", "short", "comprehensive"}
OPTION_TYPES = {"single", "multi", "judge"}
DIFFICULTIES = {"basic", "medium", "hard", "challenge"}
COGNITIVE_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}

BANNED_PHRASES = [
    "以上都是", "以上都对", "以上均不正确", "以上都不对", "A和B都对",
    "正确答案", "非正确答案干扰项", "干扰项", "选项占位",
]
_DIFF_RE = re.compile(r"(易混|区别|对比|注意|常见错误|误解|推导|证明|复杂)")


def check_question(q: dict, evidence_texts: list[str], evidence_labels: set[str]) -> list[str]:
    issues: list[str] = []
    stem = str(q.get("stem") or "")
    qtype = q.get("type")
    if qtype not in TYPES:
        issues.append(f"题型非法：{qtype}")
        return issues
    if len(stem) < 8:
        issues.append("题干过短，可能表意不清")
    for word in BANNED_PHRASES:
        if word in stem:
            issues.append(f"题干包含禁用表述「{word}」")

    options = q.get("options") or []
    labels = [str(o.get("label")) for o in options if isinstance(o, dict)]
    texts = [str(o.get("text") or "").strip() for o in options if isinstance(o, dict)]
    answer = [str(a) for a in (q.get("answer") or [])]

    if qtype in OPTION_TYPES:
        if len(options) < 2:
            issues.append("选项不足 2 个")
        if len(set(labels)) != len(labels):
            issues.append("选项标签重复")
        if len(set(texts)) != len(texts):
            issues.append("存在内容重复的选项")
        for t in texts:
            if len(t) < 2:
                issues.append("存在空或过短的选项")
            for word in BANNED_PHRASES:
                if t == word or t.startswith(word):
                    issues.append(f"选项使用固定填充「{word}」")
        if not answer or any(a not in labels for a in answer):
            issues.append("答案与选项标签不匹配")
        if qtype == "single" and len(answer) != 1:
            issues.append("单选题答案应恰好 1 项")
        if qtype == "multi" and len(answer) < 2:
            issues.append("多选题答案应至少 2 项")
        if qtype == "judge" and sorted(labels) != ["A", "B"]:
            issues.append("判断题选项应固定为 正确/错误")
        wrong_notes = q.get("wrong_option_notes") or []
        wrong_labels = {str(n.get("label")) for n in wrong_notes if isinstance(n, dict)}
        missing = [lb for lb in labels if lb not in answer and lb not in wrong_labels]
        if missing:
            issues.append(f"错误选项缺少解析：{'、'.join(missing)}")
    if qtype == "fill":
        if "____" not in stem and not re.search(r"[（(]\s*[)）]", stem):
            issues.append("填空题缺少空位标记")
        if not q.get("answers"):
            issues.append("填空题缺少可接受答案")
    if qtype in ("short", "comprehensive"):
        if not str(q.get("reference_answer") or "").strip():
            issues.append("缺少参考答案")
        if len(q.get("scoring_points") or []) < 1:
            issues.append("缺少评分要点")

    if not str(q.get("knowledge_point") or "").strip():
        issues.append("缺少对应知识点")
    loc = str(q.get("location") or "").strip()
    if not loc:
        issues.append("缺少原文来源定位")
    elif evidence_labels and loc not in evidence_labels:
        issues.append(f"来源定位「{loc}」不在证据片段中，可能编造")
    if not str(q.get("explanation") or "").strip() and qtype in OPTION_TYPES | {"fill"}:
        issues.append("缺少解析")
    if q.get("difficulty") not in DIFFICULTIES:
        issues.append(f"难度非法：{q.get('difficulty')}")
    if q.get("cognitive") not in COGNITIVE_LEVELS:
        issues.append(f"认知层次非法：{q.get('cognitive')}")

    if evidence_texts:
        joined = "\n".join(evidence_texts)
        sm = SequenceMatcher(None, stem[:400], joined[:12000], autojunk=False)
        m = sm.find_longest_match(0, min(len(stem), 400), 0, min(len(joined), 12000))
        kp = str(q.get("knowledge_point") or "")
        grounded = m.size >= 12 or (len(kp) >= 2 and kp in joined)
        if not grounded:
            issues.append("warning: 题干与课件原文直接重合较少，请人工复核是否超纲")
    return issues


def find_duplicates(questions: list[dict], threshold: float = 0.8) -> list[tuple[int, int]]:
    stems = [re.sub(r"\s+", "", str(q.get("stem") or "")) for q in questions]
    dup = []
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            if SequenceMatcher(None, stems[i], stems[j]).ratio() >= threshold:
                dup.append((i, j))
    return dup
