"""模拟考试升级：六题型、难度/认知层次、章节范围、禁用表述、审核重生成与排除。"""

import pytest

from app.modules.review import rules as R

ALL_TYPES = ["single", "multi", "judge", "fill", "short", "comprehensive"]


def gen(client, doc_id, **params):
    resp = client.post(f"/api/documents/{doc_id}/questions", json=params)
    return resp


class TestSixTypes:
    def test_all_six_types_generated(self, client, sample_doc):
        resp = gen(client, sample_doc["doc_id"], count=6, types=ALL_TYPES)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        questions = body["questions"]
        assert len(questions) == 6
        assert {q["type"] for q in questions} == set(ALL_TYPES)
        for q in questions:
            assert q["stem"] and q["knowledge_point"] and q["location"]
            assert q["difficulty"] in R.DIFFICULTIES
            assert q["cognitive"] in R.COGNITIVE_LEVELS
            assert q["quality"]["status"] in ("passed", "passed_with_warnings")

    def test_type_specific_fields(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=6, types=ALL_TYPES).json()
        by_type = {q["type"]: q for q in body["questions"]}
        assert len(by_type["single"]["answer"]) == 1
        assert len(by_type["multi"]["answer"]) >= 2
        assert [o["text"] for o in by_type["judge"]["options"]] == ["正确", "错误"]
        assert "____" in by_type["fill"]["stem"] or "(" in by_type["fill"]["stem"]
        assert by_type["fill"]["answers"]
        assert by_type["short"]["reference_answer"] and len(by_type["short"]["scoring_points"]) >= 2
        assert by_type["comprehensive"]["reference_answer"] and by_type["comprehensive"]["scoring_points"]

    def test_wrong_options_all_explained(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=6, types=["single", "multi", "judge"]).json()
        for q in body["questions"]:
            if q["type"] in ("single", "multi"):
                labels = {o["label"] for o in q["options"]}
                wrong = labels - set(q["answer"])
                noted = {n["label"] for n in q["wrong_option_notes"]}
                assert wrong <= noted, "每个错误选项都必须给出为何错误"
                assert all(n["why_wrong"] for n in q["wrong_option_notes"])


class TestParamsValidation:
    def test_count_bounds(self, client, sample_doc):
        for bad in (0, 21):
            resp = gen(client, sample_doc["doc_id"], count=bad, types=["single"])
            assert resp.status_code == 400
            assert resp.json()["code"] == "INVALID_COUNT"

    def test_invalid_types(self, client, sample_doc):
        resp = gen(client, sample_doc["doc_id"], count=3, types=["essay"])
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TYPES"

    def test_difficulty_and_cognitive_respected_and_echoed(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=4, types=["single", "judge"],
                   difficulty="hard", cognitive="analyze").json()
        assert body["params"]["difficulty"] == "hard"
        assert body["params"]["cognitive"] == "analyze"
        assert all(q["difficulty"] == "hard" and q["cognitive"] == "analyze" for q in body["questions"])

    def test_invalid_enum_falls_back_to_none(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=2, types=["single"],
                   difficulty="impossible", cognitive="quantum").json()
        assert body["params"]["difficulty"] is None
        assert body["params"]["cognitive"] is None


class TestChapterScope:
    def test_chapter_filter_selects_only_that_evidence(self, client, sample_doc):
        resp = gen(client, sample_doc["doc_id"], count=3, types=["single"], chapters=["Chapter 2"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["questions"]
        for q in body["questions"]:
            assert q["location"] == "第2页" or "energy" in q["stem"].lower() or "conserv" in q["stem"].lower()

    def test_unknown_chapter_returns_no_evidence(self, client, sample_doc):
        resp = gen(client, sample_doc["doc_id"], count=3, types=["single"], chapters=["第十九章 光学"])
        assert resp.status_code == 422
        assert resp.json()["code"] == "NO_EVIDENCE"


class TestQualityRules:
    def test_banned_fillers_absent_from_output(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=6, types=ALL_TYPES).json()
        import json as _json
        text = _json.dumps(body["questions"], ensure_ascii=False)
        for word in ("以上都是", "以上均不对", "选项占位"):
            assert word not in text

    def test_distractors_are_mutated_content(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=3, types=["single"]).json()
        for q in body["questions"]:
            texts = [o["text"] for o in q["options"]]
            assert len(set(texts)) == len(texts), "干扰项不得与正确项或其他项重复"

    def test_rules_flag_bad_question(self):
        bad = {
            "type": "single",
            "stem": "下列关于能量说法正确的是？",
            "options": [{"label": "A", "text": "甲"}, {"label": "B", "text": "以上都是"}],
            "answer": ["C"],
            "explanation": "x",
            "knowledge_point": "能量",
            "location": "第9页",
            "difficulty": "medium",
            "cognitive": "understand",
            "wrong_option_notes": [{"label": "B", "why_wrong": "y"}],
        }
        issues = R.check_question(bad, ["能量守恒的表述"], {"第1页"})
        joined = "；".join(issues)
        assert "选项使用固定填充「以上都是」" in joined
        assert "答案与选项标签不匹配" in joined
        assert "可能编造" in joined

    def test_rules_accept_good_question_without_blockers(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=2, types=["single"]).json()
        q = body["questions"][0]
        issues = R.check_question(
            q,
            ["Total mechanical energy E = K + U is conserved."],
            {q["location"]},
        )
        assert all(i.startswith("warning:") for i in issues), issues

    def test_duplicate_detection(self):
        q = {"type": "single", "stem": "机械能守恒定律的适用条件是什么？"}
        same = {"type": "single", "stem": "机械能守恒定律的适用条件是什么?"}
        other = {"type": "single", "stem": "功率的单位是什么？"}
        assert R.find_duplicates([q, same]) == [(0, 1)]
        assert R.find_duplicates([q, other]) == []


class TestReviewRetryAndExclude:
    def test_failing_questions_regenerated_then_excluded(self, client, sample_doc, monkeypatch):
        original = R.check_question

        def harsh(q, evidence_texts, evidence_labels):
            issues = original(q, evidence_texts, evidence_labels)
            if q.get("type") == "single":
                issues.append("审核判定：存在多个正确答案")
            return issues

        monkeypatch.setattr(R, "check_question", harsh)
        body = gen(client, sample_doc["doc_id"], count=6, types=ALL_TYPES).json()
        assert body["review"]["regenerated"] >= 1
        assert body["review"]["excluded"] >= 1
        assert all(q["type"] != "single" for q in body["questions"])
        for q in body["excluded"]:
            assert q["quality"]["status"] == "excluded"
            assert any("多个正确答案" in i for i in q["quality"]["issues"])

    def test_review_summary_shape(self, client, sample_doc):
        body = gen(client, sample_doc["doc_id"], count=3, types=["single", "judge"]).json()
        review = body["review"]
        assert set(review) >= {"checked", "passed", "excluded", "regenerated"}
        assert review["checked"] >= 3
        assert body["provider"]["mock"] is True
        assert [q["id"] for q in body["questions"]] == list(range(1, len(body["questions"]) + 1))
