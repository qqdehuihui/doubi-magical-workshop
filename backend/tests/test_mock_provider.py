from app.core.providers.base import GenerationRequest
from app.core.providers.mock import MOCK_PREFIX, MockProvider


def test_mock_generate_text_marks_test_data(evidence):
    req = GenerationRequest(task="qa", prompt="问题", evidence=evidence)
    result = MockProvider().generate_text(req)
    assert result.text.startswith(MOCK_PREFIX)
    assert result.mock is True
    assert result.provider == "mock"
    assert "Newton" in result.text  # 使用真实证据文本，而非固定假文字


def test_mock_generate_text_without_evidence():
    req = GenerationRequest(task="qa", prompt="问题", evidence=[])
    result = MockProvider().generate_text(req)
    assert "无证据" in result.text


def test_mock_keypoints_json_uses_real_sentences(evidence):
    req = GenerationRequest(task="keypoints_v2", prompt="提炼考点", evidence=evidence)
    data = MockProvider().generate_json(req).data
    core = data["core_knowledge"]
    assert core, "有证据时应产生核心知识点"
    for kp in core:
        assert kp["location"]
        assert "原文依据" in kp["content"]
    joined = " ".join(kp["content"] + kp["item"] for kp in core)
    assert "F = m * a" in joined  # 包含原文片段
    assert data["course_framework"]["chapters"]
    assert data["exam_predictions"]
    assert data["historical_frequent"] is None  # 历年考频只能由服务端统计注入


def test_mock_questions_json_structure(evidence):
    req = GenerationRequest(
        task="questions", prompt="出题", evidence=evidence, params={"count": 4, "types": ["single", "judge", "multi"]}
    )
    data = MockProvider().generate_json(req).data
    questions = data["questions"]
    assert len(questions) == 4
    for q in questions:
        labels = {o["label"] for o in q["options"]}
        assert q["answer"] and all(a in labels for a in q["answer"])
        assert q["explanation"]
        assert q["pages"] and all(1 <= p <= 3 for p in q["pages"])
        assert MOCK_PREFIX in q["explanation"]
    assert {q["type"] for q in questions} <= {"single", "multi", "judge"}


def test_mock_qa_json_cites_pages(evidence):
    req = GenerationRequest(task="qa", prompt="问题", evidence=evidence)
    data = MockProvider().generate_json(req).data
    assert data["pages"] == [1, 2, 3]
    assert MOCK_PREFIX in data["answer"]
    assert "E = K + U" in data["answer"]


def test_mock_qa_no_evidence_is_explicit():
    req = GenerationRequest(task="qa", prompt="问题", evidence=[])
    data = MockProvider().generate_json(req).data
    assert data["insufficient_evidence"] is True
    assert data["pages"] == []
