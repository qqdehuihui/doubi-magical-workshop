from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / "scripts" / "samples"


def test_normal_pdf_upload_keeps_pages(client):
    body = client.post(
        "/api/documents", files={"file": ("normal.pdf", (SAMPLES / "normal.pdf").read_bytes())}
    ).json()
    assert body["page_count"] == 2
    detail = client.get(f"/api/documents/{body['doc_id']}").json()
    assert [p["no"] for p in detail["pages"]] == [1, 2]
    assert "Newton" in detail["pages"][0]["text"]
    assert "Energy" in detail["pages"][1]["text"]


def test_non_pdf_rejected(client):
    resp = client.post("/api/documents", files={"file": ("fake.pdf", b"plain text not pdf")})
    assert resp.status_code == 415
    assert resp.json()["code"] == "INVALID_FILE"


def test_empty_file_rejected(client):
    resp = client.post("/api/documents", files={"file": ("empty.pdf", b"")})
    assert resp.status_code == 400
    assert resp.json()["code"] == "EMPTY_FILE"


def test_scanned_pdf_hint(client):
    resp = client.post("/api/documents", files={"file": ("scanned.pdf", (SAMPLES / "scanned.pdf").read_bytes())})
    assert resp.status_code == 415
    assert resp.json()["code"] == "SCANNED_PDF"


def test_missing_document(client):
    resp = client.post("/api/documents/00000000000000000000000000000000/key-points")
    assert resp.status_code == 404
    assert resp.json()["code"] == "DOC_NOT_FOUND"


def test_invalid_question_count(client, sample_doc):
    resp = client.post(
        f"/api/documents/{sample_doc['doc_id']}/questions", json={"count": 99, "types": ["single"]}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_COUNT"
