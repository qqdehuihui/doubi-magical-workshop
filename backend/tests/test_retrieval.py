from app.core import retrieval


def _doc():
    return {
        "doc_id": "abc123",
        "page_count": 3,
        "total_chars": 600,
        "filename": "x.pdf",
        "pages": [
            {"no": 1, "text": "Chapter 1: Newton's Laws. Key formula: F = m * a (second law)."},
            {"no": 2, "text": "Chapter 2: Conservation of Energy. E = K + U. Kinetic energy K = 1/2 m v^2."},
            {"no": 3, "text": "摩擦力方向与相对运动方向相反。静摩擦系数 mu 决定最大静摩擦力 f = mu * N。"},
        ],
    }


def test_chunks_keep_doc_id_and_page_no():
    chunks = retrieval.build_chunks(_doc())
    assert chunks
    for c in chunks:
        assert c["doc_id"] == "abc123"
        assert c["page_no"] in (1, 2, 3)
        assert c["text"]


def test_long_page_split_into_multiple_chunks():
    doc = _doc()
    doc["pages"][0]["text"] = "A" * 1200
    chunks = retrieval.build_chunks(doc)
    page1 = [c for c in chunks if c["page_no"] == 1]
    assert len(page1) >= 3
    assert max(len(c["text"]) for c in page1) <= retrieval.CHUNK_SIZE


def test_search_finds_relevant_page_for_formula_query():
    chunks = retrieval.search(_doc(), "What is the formula F = m * a?")
    assert chunks
    assert any(c["page_no"] == 1 for c in chunks)


def test_search_handles_cjk_query():
    chunks = retrieval.search(_doc(), "静摩擦系数和最大静摩擦力的关系是什么？")
    assert chunks
    assert all(c["page_no"] == 3 for c in chunks)


def test_search_irrelevant_query_returns_no_evidence():
    assert retrieval.search(_doc(), "红楼梦的作者是谁？") == []


def test_sample_chunks_covers_document_within_budget():
    doc = _doc()
    doc["pages"] = [{"no": i + 1, "text": ("句子。" * 200)} for i in range(1, 10)]
    doc["total_chars"] = sum(len(p["text"]) for p in doc["pages"])
    chunks = retrieval.sample_chunks(doc)
    assert chunks
    assert sum(len(c["text"]) for c in chunks) <= 12000
    assert len({c["page_no"] for c in chunks}) >= 2
