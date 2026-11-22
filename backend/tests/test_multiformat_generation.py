"""三种格式在 Mock Provider 下的端到端生成与来源引用，验证格式间来源编号不混用。"""

import re
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[1] / "scripts" / "samples"
PDF, PPTX, DOCX = "normal.pdf", "normal.pptx", "normal.docx"


def upload(client, name: str, course: str | None = None) -> dict:
    data = {"course_id": course} if course else {}
    resp = client.post("/api/documents", files={"file": (name, (SAMPLES / name).read_bytes())}, data=data)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def ppt_doc(client):
    return upload(client, PPTX)


@pytest.fixture()
def doc_doc(client):
    return upload(client, DOCX)


LOCATION_PATTERNS = {
    PDF: re.compile(r"^第\d+页$"),
    PPTX: re.compile(r"^第\d+张幻灯片$"),
    DOCX: re.compile(r"^(章节 .+|.+ / 表格\d+)$"),
}


class TestKeypointsAcrossFormats:
    @pytest.mark.parametrize("name", [PDF, PPTX, DOCX])
    def test_mock_keypoints_on_each_format(self, client, name):
        doc = upload(client, name)
        body = client.post(f"/api/documents/{doc['doc_id']}/key-points").json()
        assert body["schema"] == "keypoints_v2"
        assert body["provider"]["mock"] is True
        assert body["course_framework"]["chapters"]
        assert body["core_knowledge"]
        pattern = LOCATION_PATTERNS[name]
        for kp in body["core_knowledge"]:
            assert pattern.match(kp["location"]), f"{name} 的定位标签格式错误: {kp['location']}"

    def test_pptx_locations_never_say_pages(self, client, ppt_doc):
        body = client.post(f"/api/documents/{ppt_doc['doc_id']}/key-points").json()
        assert all("页" not in kp["location"] for kp in body["core_knowledge"])

    def test_docx_locations_use_heading_paths(self, client, doc_doc):
        body = client.post(f"/api/documents/{doc_doc['doc_id']}/key-points").json()
        labels = [kp["location"] for kp in body["core_knowledge"]]
        assert all(LOCATION_PATTERNS[DOCX].match(lbl) for lbl in labels)
        assert not any(re.match(r"^第\d+页$", lbl) for lbl in labels)

    def test_framework_shape_and_confusion_contract(self, client, doc_doc):
        """契约回归：框架层 topic/relations 必须存在；confusion 只允许 {with, difference}
        （曾因 Mock 输出 wrong_claim/why_wrong 被规范化吞成空串，前端永远不显示）；旧 key_points 字段已移除。"""
        body = client.post(f"/api/documents/{doc_doc['doc_id']}/key-points").json()
        fw = body["course_framework"]
        assert isinstance(fw["topic"], str) and fw["topic"]
        assert isinstance(fw["relations"], list)
        for rel in fw["relations"]:
            assert set(rel) == {"from", "to", "relation"}
        assert "key_points" not in body
        for dp in body["difficult_points"]:
            conf = dp.get("confusion")
            if conf:
                assert set(conf) == {"with", "difference"}, f"confusion 契约被破坏: {conf}"
                assert conf["with"], "易混对象不得为空"


class TestQuestionsAcrossFormats:
    @pytest.mark.parametrize("name", [PDF, PPTX, DOCX])
    def test_mock_questions_on_each_format(self, client, name):
        doc = upload(client, name)
        resp = client.post(
            f"/api/documents/{doc['doc_id']}/questions",
            json={"count": 4, "types": ["single", "judge", "fill", "short"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["questions"]) == 4
        for q in body["questions"]:
            assert q["location"]
            assert LOCATION_PATTERNS[name].match(q["location"])
            assert q["quality"]["status"] in ("passed", "passed_with_warnings")


class TestQaAcrossFormats:
    def test_pdf_chat_cites_pages(self, client, sample_doc):
        body = client.post(
            f"/api/documents/{sample_doc['doc_id']}/chat",
            json={"question": "What does F = m * a mean?"},
        ).json()
        assert body["cited_pages"]
        assert all(re.match(r"^第\d+页$", x) for x in body["locations"])

    def test_pptx_chat_cites_slides_not_pages(self, client, ppt_doc):
        body = client.post(
            f"/api/documents/{ppt_doc['doc_id']}/chat",
            json={"question": "Newton's second law F = m * a"},
        ).json()
        assert body["insufficient_evidence"] is False
        assert body["locations"], "必须给出来源定位"
        assert all("幻灯片" in x for x in body["locations"])
        assert not any(re.match(r"^第\d+页$", x) for x in body["locations"])

    def test_docx_chat_cites_heading_path(self, client, doc_doc):
        body = client.post(
            f"/api/documents/{doc_doc['doc_id']}/chat",
            json={"question": "机械能守恒 动能 势能"},
        ).json()
        assert body["insufficient_evidence"] is False
        assert all(x.startswith("章节 ") or "表格" in x for x in body["locations"])

    def test_no_evidence_question_short_circuits(self, client, ppt_doc):
        body = client.post(
            f"/api/documents/{ppt_doc['doc_id']}/chat",
            json={"question": "秦始皇焚书坑儒的具体年份是哪一年"},
        ).json()
        assert body["insufficient_evidence"] is True
        assert body["cited_pages"] == [] and body["locations"] == []
        assert "证据不足" in body["answer"]
        assert body["provider"]["mock"] is False, "短路路径不得调用任何模型"
