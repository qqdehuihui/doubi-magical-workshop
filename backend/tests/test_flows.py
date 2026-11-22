MOCK_PREFIX = "[MOCK 测试数据]"


def test_keypoints_full_flow_marks_mock_and_cites_pages(client, sample_doc):
    resp = client.post(f"/api/documents/{sample_doc['doc_id']}/key-points")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema"] == "keypoints_v2"
    assert body["provider"]["name"] == "mock"
    assert body["provider"]["mock"] is True
    assert "测试数据" in body["provider"]["disclaimer"]
    assert body["evidence_chunks"] >= 1
    # 五层结构齐备
    assert body["course_framework"]["chapters"]
    assert body["core_knowledge"]
    assert body["difficult_points"]
    assert body["exam_predictions"]
    for kp in body["core_knowledge"]:
        assert kp["item"] and kp["content"]
        assert kp["location"].startswith("第") and kp["location"].endswith("页")
        assert kp["importance"] in ("高", "中", "低") and kp["emphasis"] in ("高", "中", "低")
        assert MOCK_PREFIX in kp["content"]
    for pr in body["exam_predictions"]:
        assert pr["priority"] in ("高", "中", "低")
        assert "历年" in pr["note"] or "考频" in pr["note"]
    # 未导入试卷：不得给出任何“高频考点”，必须显示固定提示
    hist = body["historical_frequent"]
    assert hist["available"] is False
    assert hist["items"] == []
    assert "尚未导入历年考试资料" in hist["notice"]
    assert "四个指标" in body["metrics_legend"]["warning"] or "不可混同" in body["metrics_legend"]["warning"]


def test_questions_full_flow_structure(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/questions",
        json={"count": 3, "types": ["single", "judge", "multi"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]["mock"] is True
    questions = body["questions"]
    assert len(questions) == 3
    for q in questions:
        labels = {o["label"] for o in q["options"]}
        assert q["answer"] and all(a in labels for a in q["answer"])
        assert q["explanation"] and MOCK_PREFIX in q["explanation"]
        assert q["pages"] and all(1 <= p <= sample_doc["page_count"] for p in q["pages"])
    if questions[2]["type"] == "multi":
        assert len(questions[2]["answer"]) >= 2


def test_qa_full_flow_cites_evidence_pages(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/chat",
        json={"question": "What is the formula F = m * a in Newton's second law?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"]["name"] == "mock"
    assert body["insufficient_evidence"] is False
    assert 1 in body["cited_pages"], "公式出自第 1 页，引用页码必须包含 1"
    assert all(1 <= p <= sample_doc["page_count"] for p in body["cited_pages"])
    assert "F = m * a" in body["answer"]


def test_qa_result_never_dumps_whole_document(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/chat",
        json={"question": "energy conservation"},
    )
    body = resp.json()
    # 证据片段数远小于页数*全量，且 provider 记录的是检索片段而非全文
    assert body["evidence_chunks"] <= 4
