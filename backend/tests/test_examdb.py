"""历年考试资料库：拆题、考点归一化、统计口径与固定提示、删除与联动。"""

import uuid
from pathlib import Path

import pytest

from app.modules.examdb.extract import PointNormalizer, detect_year, point_candidates
from app.modules.examdb.service import frequent_points

SAMPLES = Path(__file__).resolve().parents[1] / "scripts" / "samples"

NO_HISTORY_NOTICE = (
    "当前仅基于教师课件分析，尚未导入历年考试资料，无法统计真实考频。"
    "上传往年试卷后可生成历年高频考点分析。"
)


def upload_exam(client, name: str, course: str, material_type: str = "试卷", year: str | None = None):
    data = {"course_id": course, "material_type": material_type}
    if year:
        data["year"] = year
    resp = client.post(
        "/api/exams",
        files={"file": (name, (SAMPLES / name).read_bytes())},
        data=data,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def course() -> str:
    return f"物理基础-{uuid.uuid4().hex[:8]}"


class TestExtract:
    def test_docx_exam_splits_questions_with_scores(self, client, course):
        out = upload_exam(client, "exam_2022.docx", course)
        assert out["extracted_questions"] == 5
        assert out["year"] == 2022
        assert out["material_type"] == "试卷"
        assert out["file_type"] == "docx"

    def test_year_from_filename_when_not_given(self, client, course):
        out = upload_exam(client, "exam_2023.docx", course)
        assert out["year"] == 2023

    def test_manual_year_overrides(self, client, course):
        out = upload_exam(client, "exam_2022.docx", course, year="1999")
        assert out["year"] == 1999

    def test_detect_year_prefers_reliable_sources(self):
        assert detect_year("期末_2021年.pdf", "") == 2021
        assert detect_year("期末试卷.pdf", "…2019 年 6 月…") == 2019
        assert detect_year("无年份文件.pdf", "正文没有年份") is None

    def test_english_exam_score_marked_unknown_not_guessed(self, client, course):
        upload_exam(client, "exam_2021.pdf", course)
        stats = frequent_points(course)
        english = [p for p in stats["points"] if p["point"] in {"newton", "kinetic", "energy", "law"}]
        assert english, "英文题干也应被拆题统计"
        assert all(p["score_total"] == "未知" for p in english)

    def test_material_type_unknown_when_unrecognized(self, client, course):
        out = upload_exam(client, "exam_2022.docx", course, material_type="神秘资料")
        assert out["material_type"] == "未知"


class TestPointNormalization:
    def test_same_concept_different_wording_merges(self):
        n = PointNormalizer()
        a, ka = n.normalize("牛顿第二定律表达了力与加速度的关系（5分）")
        b, kb = n.normalize("描述加速度与合外力关系的牛顿第二定律公式是（5分）")
        assert a == b == "牛顿第二定律"
        assert ka == kb

    def test_different_concepts_not_merged(self):
        n = PointNormalizer()
        a, _ = n.normalize("牛顿第二定律表达了力与加速度的关系（5分）")
        c, _ = n.normalize("功率的单位是什么（3分）")
        assert a != c

    def test_candidates_strip_score_and_function_words(self):
        cands = point_candidates("物体机械能守恒的条件是____（5分）")
        assert any("机械能守恒" in c for c in cands)
        assert not any("5" in c or "条件" in c for c in cands)

    def test_no_candidates_gives_generic_label(self):
        n = PointNormalizer()
        name, key = n.normalize("（2分）")
        assert (name, key) == ("综合考点", "misc")


class TestStats:
    def test_multi_paper_statistics(self, client, course):
        upload_exam(client, "exam_2022.docx", course)
        upload_exam(client, "exam_2023.docx", course)
        stats = frequent_points(course)
        assert stats["available"] is True
        assert stats["paper_count"] == 2
        assert stats["question_total"] == 10
        assert set(stats["by_year"]) == {"2022", "2023"}
        newton = [p for p in stats["points"] if p["point"] == "牛顿第二定律"]
        assert newton and newton[0]["count"] >= 2
        assert {"2022", "2023"} <= set(newton[0]["years"])
        assert newton[0]["score_total"] != "未知"
        assert stats["notice"] is None

    def test_type_distribution_counts(self, client, course):
        upload_exam(client, "exam_2022.docx", course)
        stats = frequent_points(course)
        assert sum(stats["by_type"]["types"].values()) == 5
        assert stats["by_type"]["labels"] == {
            k: {"single": "单选", "multi": "多选", "judge": "判断", "fill": "填空",
                "short": "简答", "comprehensive": "综合", "unknown": "未标注"}[k]
            for k in stats["by_type"]["types"]
        }, "题型标签必须来自 _QTYPE_LABEL 中文映射，不得回退为原始代码"

    def test_course_isolation(self, client, course):
        other = course + "-B"
        upload_exam(client, "exam_2022.docx", course)
        stats = frequent_points(other)
        assert stats["available"] is False
        assert stats["points"] == []

    def test_empty_course_returns_fixed_notice(self, client, course):
        stats = frequent_points(course)
        assert stats["available"] is False
        assert stats["points"] == []
        assert stats["notice"] == NO_HISTORY_NOTICE

    def test_frequent_points_api_and_list_and_delete(self, client, course):
        out = upload_exam(client, "exam_2022.docx", course)
        listed = client.get("/api/exams", params={"course_id": course}).json()
        assert listed["exam_count"] == 1
        assert listed["exams"][0]["exam_doc_id"] == out["exam_doc_id"]
        fp = client.get("/api/exams/frequent-points", params={"course_id": course}).json()
        assert fp["available"] is True
        assert client.delete(f"/api/exams/{out['exam_doc_id']}").status_code == 200
        assert client.get("/api/exams", params={"course_id": course}).json()["exam_count"] == 0

    def test_delete_missing_or_non_exam_404(self, client, sample_doc):
        resp = client.delete(f"/api/exams/{sample_doc['doc_id']}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "EXAM_NOT_FOUND"


class TestKeyPointsHistoryLink:
    def test_history_injected_only_after_exam_import(self, client, course):
        doc = client.post(
            "/api/documents",
            files={"file": ("normal.pdf", (SAMPLES / "normal.pdf").read_bytes())},
            data={"course_id": course},
        ).json()

        body = client.post(f"/api/documents/{doc['doc_id']}/key-points").json()
        hist = body["historical_frequent"]
        assert hist["available"] is False
        assert hist["items"] == []
        assert hist["notice"] == NO_HISTORY_NOTICE

        upload_exam(client, "exam_2022.docx", course)
        upload_exam(client, "exam_2023.docx", course)
        body2 = client.post(f"/api/documents/{doc['doc_id']}/key-points").json()
        hist2 = body2["historical_frequent"]
        assert hist2["available"] is True
        assert hist2["items"]
        assert any(it["count"] >= 2 for it in hist2["items"])
        # 历史考点只来自服务端统计，与模型输出的推测考查价值分列两个字段
        assert hist2["source"] == "examdb_statistics"
        assert all(p["priority"] in ("高", "中", "低") for p in body2["exam_predictions"])
