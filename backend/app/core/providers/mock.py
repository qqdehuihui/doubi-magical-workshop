"""Mock Provider：完全基于检索到的课件原文片段生成结构化结果。

- 输出使用证据中的真实文本（原句、变形干扰项、挖空术语），不编造课件之外的内容
- 明确标记 provider=mock；不模拟“真实模型推理”，也不虚构历年考频
- 支持任务：keypoints_v2（五层重难点）、exam_questions（六题型）、exam_review（自审）、qa
"""

from __future__ import annotations

import re

from app.core import retrieval
from app.core.providers.base import BaseProvider, GenerationRequest, GenerationResult
from app.modules.review import rules as R

MOCK_PREFIX = "[MOCK 测试数据]"
MOCK_EVIDENCE_LIMIT = 8

_POLARITY = [
    ("必须", "无需"), ("可以", "不可以"), ("都会", "都不会"), ("增加", "减少"),
    ("大于", "小于"), ("高于", "低于"), ("正比", "反比"), ("吸收", "释放"),
    ("属于", "不属于"), ("导致", "不会导致"), ("上升", "下降"), ("输入", "输出"),
]
_DIFF_RE = re.compile(r"(易混|区别|对比|注意|常见错误|误解|推导|证明|复杂|条件|误区)")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?.])\s*|\n+", text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 8]


def _pool(evidence: list[dict]) -> list[dict]:
    """[{s, label, page, text}] 句子级证据池，来自真实片段。"""
    pool: list[dict] = []
    for chunk in evidence:
        label = chunk.get("location_label") or f"第{chunk.get('page_no')}页"
        for sent in _sentences(chunk["text"])[:3]:
            pool.append({"s": sent[:100], "label": label, "page": chunk.get("page_no"), "text": chunk["text"]})
    return pool


def _terms(text: str) -> list[str]:
    out: list[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", text):
        if len(w) >= 2 and w not in out:
            out.append(w)
    for seg in re.split(r"[^一-鿿]+", text):
        for part in re.findall(r"[一-鿿]{2,4}", seg)[:3]:
            if part not in out:
                out.append(part)
    return out


def _distractor(sent: str, other_sent: str | None, salt: int) -> tuple[str, str]:
    """对真实句子做有据可依的变形，返回 (干扰项文本, 错误原因)。"""
    for a, b in _POLARITY:
        if a in sent:
            return sent.replace(a, b, 1), f"把原文断言「{a}」颠倒为「{b}」，与出处内容矛盾"
    m = re.search(r"\d+(?:\.\d+)?", sent)
    if m:
        n = float(m.group()) + 1
        repl = str(int(n)) if n == int(n) else f"{n:.1f}"
        return sent[: m.start()] + repl + sent[m.end() :], "篡改了原文中的数值参数"
    if other_sent:
        t1 = _terms(other_sent)[:1]
        t2 = [t for t in _terms(sent) if t != t1[0]] if t1 else []
        if t1 and t2 and t1[0] in (sent or "") + (other_sent or "") and t2[0] in sent:
            return sent.replace(t2[0], t1[0], 1), f"用另一知识点中的「{t1[0]}」替换了「{t2[0]}」，属于概念混淆"
    return f"只要满足任一条件，{sent}就一定成立", "把原文的适用条件绝对化，属于常见理解偏差"


def _is_a(sent: str) -> bool:
    return bool(re.search(r"定律|原理|机制|定义|是指|称为|所谓|法则", sent))


def _has_formula(sent: str) -> bool:
    return bool(re.search(r"[=＝]", sent)) and bool(re.search(r"[A-Za-z0-9]", sent))


def _kind_of(sent: str) -> str:
    if _has_formula(sent):
        return "formula"
    if re.search(r"定义|是指|称为|所谓", sent):
        return "definition"
    if re.search(r"定律|原理|机制|法则|过程", sent):
        return "principle"
    if re.search(r"因此|所以|表明|结论|说明", sent):
        return "conclusion"
    return "key_fact"


class MockProvider(BaseProvider):
    name = "mock"

    @property
    def model_name(self) -> str:
        return "mock-v2"

    def health_check(self) -> dict:
        return {
            "provider": self.name,
            "model": self.model_name,
            "configured": True,
            "mock": True,
            "detail": "Mock Provider 无需 API Key，输出为基于课件原文的测试数据（非真实 AI 推理）",
        }

    def generate_text(self, req: GenerationRequest) -> GenerationResult:
        pool = _pool(req.evidence)
        preview = "；".join(p["s"] for p in pool[:3]) or "（无证据片段）"
        text = (
            f"{MOCK_PREFIX} 任务={req.task}，基于 {len(req.evidence)} 个课件原文片段生成。"
            f"证据摘录：{preview}"
        )
        return self._make(text=text, mock=True, prompt_tokens=len(text), completion_tokens=len(text))

    def generate_json(self, req: GenerationRequest) -> GenerationResult:
        handler = {
            "keypoints": self._keypoints_v2,
            "keypoints_v2": self._keypoints_v2,
            "questions": self._exam_questions,
            "exam_questions": self._exam_questions,
            "exam_review": self._exam_review,
            "qa": self._qa,
        }.get(req.task)
        if handler is None:
            raise ValueError(f"MockProvider 不支持任务类型: {req.task}")
        data = handler(req)
        text = str(data)
        return self._make(data=data, text=text, mock=True, prompt_tokens=len(text), completion_tokens=len(str(data)))

    # -- 五层重难点分析 --

    def _keypoints_v2(self, req: GenerationRequest) -> dict:
        pool = _pool(req.evidence)
        if not pool:
            return {"insufficient_evidence": True}
        headings = req.params.get("headings") or []
        sections = req.params.get("sections") or []
        topic = headings[0] if headings else (sections[0].get("title") if sections else pool[0]["s"][:40])

        chapters = []
        for s in sections[:12]:
            chapters.append({
                "title": s.get("title"),
                "location": f"第{s.get('start_page')}页" if s.get("start_page") else s.get("path") or s.get("title"),
                "summary": next((p["s"] for p in pool if (s.get("title") or "")[:4] and (s.get("title") or "")[:4] in p["text"]), pool[len(chapters) % len(pool)]["s"][:60]),
            })
        if not chapters:
            labels = []
            for p in pool:
                if p["label"] not in labels:
                    labels.append(p["label"])
            chapters = [{"title": lb, "location": lb, "summary": next((p["s"] for p in pool if p["label"] == lb), "")[:60]} for lb in labels[:8]]
        relations = [
            {"from": chapters[i]["title"], "to": chapters[i + 1]["title"], "relation": "内容依次展开（Mock 依据原文顺序）"}
            for i in range(len(chapters) - 1)
        ]

        texts = [c["text"] for c in req.evidence]
        core, seen = [], set()
        for p in pool:
            if p["s"] in seen:
                continue
            seen.add(p["s"])
            kind = _kind_of(p["s"])
            occ = sum(1 for t in texts if p["s"][:20] in t)
            emphasis = "高" if occ >= 2 or kind in ("formula", "definition") else ("中" if kind != "key_fact" else "低")
            core.append({
                "item": p["s"][:40],
                "kind": kind,
                "content": f"{MOCK_PREFIX} 原文依据（{p['label']}）：“{p['s']}”",
                "location": p["label"],
                "importance": "高" if kind in ("formula", "definition", "principle") else "中",
                "emphasis": emphasis,
            })
            if len(core) >= MOCK_EVIDENCE_LIMIT:
                break

        difficult = []
        for i, p in enumerate(pool):
            why = []
            if _DIFF_RE.search(p["s"]):
                why.append("需要重点理解的机制/推导")
            other = pool[(i + 3) % len(pool)]
            confusable = None
            if other is not p:
                da, why_txt = _distractor(p["s"], other["s"], i)
                if "矛盾" in why_txt or "概念混淆" in why_txt:
                    confusable = {"with": other["s"][:40], "difference": why_txt}
                    why.append("容易混淆/常见理解错误")
            if _has_formula(p["s"]):
                why.append("公式与计算方法的适用条件")
            if not why:
                continue
            d = {
                "item": p["s"][:40],
                "content": f"{MOCK_PREFIX} 依据（{p['label']}）：“{p['s']}”",
                "why": why,
                "location": p["label"],
            }
            if confusable:
                d["confusion"] = confusable
            difficult.append(d)
            if len(difficult) >= 6:
                break
        if not difficult and pool:
            difficult = [{"item": pool[0]["s"][:40], "content": f"{MOCK_PREFIX} 该段信息密度较高（{pool[0]['label']}）",
                          "why": ["需要重点理解的内容"], "location": pool[0]["label"]}]

        predictions = []
        for c in core:
            basis = []
            if c["kind"] in ("formula", "definition"):
                basis.append("课件中给出明确定义/公式（强调度高）")
            if c["emphasis"] == "高":
                basis.append("同一内容在课件中多处出现")
            if not basis:
                basis.append("课件一次性提及")
            priority = "高" if len(basis) >= 2 else ("中" if c["emphasis"] != "低" else "低")
            predictions.append({
                "item": c["item"],
                "priority": priority,
                "basis": basis,
                "location": c["location"],
                "emphasis": c["emphasis"],
                "note": "仅基于课件强调程度的推测，不代表历年真实考频",
            })

        return {
            "course_framework": {"topic": topic, "chapters": chapters, "relations": relations},
            "core_knowledge": core,
            "difficult_points": difficult,
            "exam_predictions": predictions,
            "historical_frequent": None,
        }

    # -- 六题型生成 --

    def _exam_questions(self, req: GenerationRequest) -> dict:
        pool = _pool(req.evidence)
        if not pool:
            return {"questions": [], "insufficient_evidence": True}
        count = int(req.params.get("count", 5))
        types = [t for t in (req.params.get("types") or ["single"]) if t in R.TYPES] or ["single"]
        difficulty_pref = req.params.get("difficulty") or None
        cognitive_pref = req.params.get("cognitive") or None
        offset = int(req.params.get("offset", 0))
        questions = []
        used_stems = set()
        i = 0
        guard = 0
        while len(questions) < count and guard < count * 4:
            guard += 1
            qtype = types[i % len(types)]
            p = pool[(i + offset) % len(pool)]
            other = pool[(i + 1 + offset) % len(pool)]
            diff = difficulty_pref or ["basic", "medium", "hard", "challenge"][i % 4]
            cog = cognitive_pref or {"single": "understand", "multi": "analyze", "judge": "understand",
                                     "fill": "remember", "short": "apply", "comprehensive": "evaluate"}[qtype]
            q = self._build_question(qtype, p, other, i, diff, cog, pool)
            if q and q["stem"] not in used_stems:
                used_stems.add(q["stem"])
                questions.append(q)
            i += 1
        return {"questions": questions}

    def _loc_page(self, p: dict):
        return p.get("page")

    def _build_question(self, qtype: str, p: dict, other: dict, i: int, diff: str, cog: str, pool: list[dict]) -> dict | None:
        sent, label = p["s"], p["label"]
        terms = _terms(sent)
        point = terms[0] if terms else sent[:12]
        base = {"type": qtype, "difficulty": diff, "cognitive": cog,
                "knowledge_point": point, "location": label, "pages": [p["page"]] if p.get("page") else []}

        openers = [f"根据{label}", f"结合{label}的内容", f"关于「{point}」", f"依据课件（{label}）"]
        opener = openers[i % len(openers)]

        if qtype == "judge":
            flip = i % 2 == 1
            claim, why = (sent, "该表述与原文一致") if not flip else _distractor(sent, other["s"], i)
            ans = ["A"] if not flip else ["B"]
            jstem = [
                f"{opener}的表述：「{claim[:120]}」。该说法是否正确？",
                f"课件（{label}）在讲「{point}」。判断以下说法是否与原文相符：「{claim[:120]}」",
                f"关于「{point}」，有人提出：「{claim[:120]}」。依据{label}，这一判断成立吗？",
                f"阅读{label}相关内容（{point}），判断：「{claim[:120]}」是否准确。",
            ][i % 4]
            return {
                **base, "id": None,
                "stem": jstem,
                "options": [{"label": "A", "text": "正确"}, {"label": "B", "text": "错误"}],
                "answer": ans,
                "explanation": f"{MOCK_PREFIX} {why}。原文（{label}）：“{sent[:80]}”",
                "wrong_option_notes": [{"label": ans[0] == "A" and "B" or "A", "why_wrong": f"与原文矛盾，原文为：“{sent[:60]}”"}],
            }

        if qtype == "fill":
            if terms:
                term = max(terms, key=len)
                if term in sent and len(term) <= 30:
                    blanked = sent.replace(term, "____", 1)
                    fstem = [
                        f"{opener}按原文填空：{blanked[:200]}",
                        f"课件原文（{label}）写道：{blanked[:200]}（请填写空缺术语）",
                        f"补全{label}中关于「{point}」的表述：{blanked[:200]}",
                    ][i % 3]
                    return {
                        **base, "id": None,
                        "stem": fstem,
                        "options": [],
                        "answer": [term],
                        "answers": [term],
                        "explanation": f"{MOCK_PREFIX} 原文（{label}）该处为「{term}」。",
                    }
            fallback = f"{opener}：原文关键术语填写，句子「{sent[:60]}」中的核心概念为____。"
            return {**base, "id": None, "stem": fallback, "options": [], "answer": [point],
                    "answers": [point], "explanation": f"{MOCK_PREFIX} 依据原文（{label}）。"}

        if qtype in ("short", "comprehensive"):
            follow = [x[:100] for x in _sentences(p["text"]) if x != sent][:2]
            ref = sent + ("；" + "；".join(follow) if follow else "")
            if qtype == "comprehensive":
                stem = [
                    f"{opener}，请结合「{point}」说明其含义、成立条件，并分析一个典型应用场景。",
                    f"以{label}中「{point}」为核心，解释其机理，推导在给定条件下会发生什么，并指出常见误用。",
                    f"课件（{label}）给出了「{point}」。请综合分析：它解决什么问题、需要什么条件、结论如何得出。",
                ][i % 3]
            else:
                stem = [
                    f"{opener}，简述「{point}」的主要内容与要点。",
                    f"什么是{label}中提到的「{point}」？请用自己的话概括其要点。",
                    f"请解释课件（{label}）中「{point}」的含义及其关键信息。",
                ][i % 3]
            return {
                **base, "id": None, "stem": stem, "options": [], "answer": [],
                "reference_answer": f"{MOCK_PREFIX} 参考答案（源自原文 {label}）：{ref[:400]}",
                "scoring_points": ["答出原文核心表述得基础分"] + (["答出关联要点/适用条件得附加分"] if follow else []) + ["能用原文术语，不要求逐字一致"],
                "explanation": f"{MOCK_PREFIX} 本题依据（{label}）原文构造，Mock 模式不代表真实评分能力。",
            }

        # single / multi
        n_distract = 3 if qtype == "single" else 2
        distract = []
        for k in range(1, n_distract + 1):
            src = pool[(i + k) % len(pool)]
            dt, why = _distractor(src["s"], src["s"] if k % 2 else sent, i + k)
            distract.append((dt, why, src))
        texts = [sent] + [d[0] for d in distract]
        if len(texts) < 4:
            texts += [f"{sent}的同时，还满足了另一个未在原文明确给出的额外条件"] * (4 - len(texts))
        texts = texts[:4]
        seen_t, uniq = set(), []
        for t in texts:
            if t not in seen_t:
                seen_t.add(t)
                uniq.append(t)
        texts = uniq
        labels = [chr(ord("A") + j) for j in range(len(texts))]
        answer = ["A"]
        notes = []
        for j in range(1, len(texts)):
            why = distract[j - 1][1] if j - 1 < len(distract) else "对原文条件做了未经支持的扩展"
            notes.append({"label": labels[j], "why_wrong": f"{why}（对照原文 {label}）"})
        if qtype == "multi":
            extra = pool[(i + 2) % len(pool)]
            correct_texts = [sent, extra["s"]]
            distract = []
            for k in range(2):
                src = pool[(i + 3 + k) % len(pool)]
                dt, why = _distractor(src["s"], sent, i + k)
                distract.append((dt, why))
            texts = correct_texts + [d[0] for d in distract]
            seen_t, uniq = set(), []
            for t in texts:
                if t not in seen_t:
                    seen_t.add(t)
                    uniq.append(t)
            texts = uniq
            labels = [chr(ord("A") + j) for j in range(len(texts))]
            answer = sorted(labels[: len(correct_texts)])
            notes = []
            for j, (dt, why) in enumerate(distract):
                lb = labels[len(correct_texts) + j] if len(correct_texts) + j < len(labels) else None
                if lb and lb not in answer:
                    notes.append({"label": lb, "why_wrong": f"{why}（对照原文 {label}）"})
            stem = [
                f"{opener}，{point}相关内容中，哪些表述与原文一致？（多选）",
                f"关于「{point}」，以下{label}原文支持的说法有哪些？（多选）",
                f"{label}涉及「{point}」。选出所有与原文一致的表述。（多选）",
            ][i % 3]
            return {
                **base, "id": None, "stem": stem,
                "options": [{"label": lb, "text": t[:200]} for lb, t in zip(labels, texts)],
                "answer": answer,
                "explanation": f"{MOCK_PREFIX} 选项 {'、'.join(answer)} 摘自原文；其余为对真实原文句的可解释变形（{label}）。",
                "wrong_option_notes": notes,
            }
        q_verb = "下列哪一项" if qtype == "single" else "下列哪些项"
        stem = [
            f"{opener}，{q_verb}表述与原文一致？（关于「{point}」）",
            f"以下关于「{point}」的说法，{q_verb}能在{label}原文中找到依据？",
            f"{label}讲解了「{point}」，{q_verb}选项与原文相符？",
            f"就「{point}」而言，{q_verb}说法符合{opener}的原始表述？",
        ][i % 4]
        return {
            **base, "id": None,
            "stem": stem,
            "options": [{"label": lb, "text": t[:200]} for lb, t in zip(labels, texts)],
            "answer": answer if qtype == "single" else sorted(set(answer)),
            "explanation": f"{MOCK_PREFIX} 正确项摘自原文（{label}）：“{sent[:70]}”；错误项均为对真实原文句的可解释变形。",
            "wrong_option_notes": notes,
        }

    # -- Mock 自审：运行确定性规则审核并如实返回问题 --
    def _exam_review(self, req: GenerationRequest) -> dict:
        questions = req.params.get("questions") or []
        evidence_texts = [c["text"] for c in req.evidence]
        evidence_labels = {c.get("location_label") for c in req.evidence if c.get("location_label")}
        reviews = []
        for idx, q in enumerate(questions):
            issues = R.check_question(q, evidence_texts, evidence_labels)
            reviews.append({"index": idx, "issues": issues})
        return {"reviews": reviews, "note": f"{MOCK_PREFIX} 审查结果来自确定性规则，与真实模型的语义审查等价性未验证"}

    # -- 问答 --

    def _qa(self, req: GenerationRequest) -> dict:
        pool = _pool(req.evidence)
        if not pool:
            return {
                "answer": f"{MOCK_PREFIX} 证据不足：课件中未找到与该问题相关的内容，无法回答。",
                "pages": [], "locations": [], "insufficient_evidence": True,
            }
        best = "；".join(p["s"] for p in pool[:MOCK_EVIDENCE_LIMIT])
        pages = sorted({p["page"] for p in pool if p.get("page")})
        labels = retrieval.locations(req.evidence)
        src = "、".join(labels) if labels else "、".join(f"第{pg}页" for pg in pages)
        return {
            "answer": f"{MOCK_PREFIX} 依据课件原文（{src}）：{best}。（Mock 摘录，非真实 AI 推理）",
            "pages": pages, "locations": labels,
        }
