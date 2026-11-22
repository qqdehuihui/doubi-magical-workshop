def test_no_evidence_question_returns_explicit_insufficient(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/chat",
        json={"question": "红楼梦前五回的结构安排是什么？"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["insufficient_evidence"] is True
    assert body["cited_pages"] == []
    assert "证据不足" in body["answer"]
    assert body["provider"]["name"] == "rule"
    assert "未调用任何模型" in body["provider"]["disclaimer"]


def test_no_evidence_does_not_disguise_as_model_success(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/chat",
        json={"question": "量子纠缠实验的最新进展？"},
    )
    body = resp.json()
    assert body["evidence_chunks"] == 0
    assert body["provider"].get("mock") is False
