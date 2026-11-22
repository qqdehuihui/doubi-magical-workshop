"""多格式解析：魔数识别、旧格式拒绝、统一 DocumentBlock 结构与来源定位不混用。"""

from pathlib import Path

import pytest

from app.core.documents import parse_document, sniff_format, validate_upload
from app.core.documents.blocks import LOC_HEADING, LOC_PAGE, LOC_SLIDE, LOC_TABLE
from app.core.errors import ApiException

SAMPLES = Path(__file__).resolve().parents[1] / "scripts" / "samples"


def read(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


class TestSniffAndValidate:
    def test_magic_bytes_win_over_extension(self):
        assert sniff_format(read("normal.pdf"), "renamed.pptx") == "pdf"
        assert sniff_format(read("normal.pptx"), "renamed.pdf") == "pptx"
        assert sniff_format(read("normal.docx"), "whatever") == "docx"

    def test_legacy_ppt_rejected_with_saveas_hint(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"\xd0\xcf\x11\xe0binary old format", "old.ppt")
        assert exc.value.code == "UNSUPPORTED_FORMAT"
        assert "另存" in exc.value.message
        assert exc.value.status_code == 415

    def test_legacy_doc_rejected(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"\xd0\xcf\x11\xe0binary old format", "old.doc")
        assert exc.value.code == "UNSUPPORTED_FORMAT"
        assert "Word 97-2003" in exc.value.message

    def test_extension_content_mismatch(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"plain text pretending to be pptx", "slide.pptx")
        assert exc.value.code == "INVALID_FILE"
        assert exc.value.status_code == 415

    def test_fake_pdf_rejected(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(read("fake.pdf"), "fake.pdf")
        assert exc.value.code == "INVALID_FILE"

    def test_empty_file(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"", "a.pdf")
        assert exc.value.code == "EMPTY_FILE"

    def test_corrupt_zip(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"PK\x03\x04then garbage", "a.docx")
        assert exc.value.code == "INVALID_FILE"

    def test_unknown_extension(self):
        with pytest.raises(ApiException) as exc:
            validate_upload(b"some notes in plain text", "notes.txt")
        assert exc.value.code == "UNSUPPORTED_FORMAT"


class TestPdfParsing:
    def test_page_number_blocks(self):
        doc = parse_document(read("normal.pdf"), "normal.pdf", "d-pdf")
        assert doc["file_type"] == "pdf"
        assert doc["schema_version"] == 2
        assert doc["unit_label"] == "页"
        assert doc["page_count"] == 2
        assert {b["location_type"] for b in doc["blocks"]} == {LOC_PAGE}
        assert {b["location_label"] for b in doc["blocks"]} == {"第1页", "第2页"}
        assert len(doc["pages"]) == 2
        assert "F = m * a" in doc["pages"][0]["text"]

    def test_sections_detected_from_pages(self):
        doc = parse_document(read("normal.pdf"), "normal.pdf", "d-pdf2")
        titles = [s["title"] for s in doc["sections"]]
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)

    def test_scanned_pdf_rejected_no_ocr_claim(self):
        with pytest.raises(ApiException) as exc:
            parse_document(read("scanned.pdf"), "scanned.pdf", "d-scan")
        assert exc.value.code == "SCANNED_PDF"
        assert "OCR" in exc.value.message


class TestPptxParsing:
    def test_slide_number_blocks_and_order(self):
        doc = parse_document(read("normal.pptx"), "normal.pptx", "d-ppt")
        assert doc["file_type"] == "pptx"
        assert doc["unit_label"] == "幻灯片"
        assert {b["location_type"] for b in doc["blocks"]} == {LOC_SLIDE}
        labels = {b["location_label"] for b in doc["blocks"]}
        assert "第1张幻灯片" in labels
        assert all(not lbl.endswith("页") for lbl in labels), "PPTX 不得混入页码来源"
        seqs = [b["sequence"] for b in doc["blocks"]]
        assert seqs == sorted(seqs)

    def test_titles_tables_and_sections(self):
        doc = parse_document(read("normal.pptx"), "normal.pptx", "d-ppt2")
        assert any(b["block_type"] == "title" for b in doc["blocks"])
        tables = [b for b in doc["blocks"] if b["block_type"] == "table"]
        assert tables and " | " in tables[0]["content"]
        assert doc["sections"] and doc["sections"][0]["slide"] == 1


class TestDocxParsing:
    def test_heading_hierarchy_and_paragraph_location(self):
        doc = parse_document(read("normal.docx"), "normal.docx", "d-doc")
        assert doc["file_type"] == "docx"
        headings = [b for b in doc["blocks"] if b["block_type"] == "heading"]
        assert len(headings) >= 2
        paths = {b["location_value"] for b in headings}
        assert all("/" in p for p in paths)
        texts = [b for b in doc["blocks"] if b["block_type"] == "text"]
        assert any(b["location_type"] == LOC_HEADING for b in texts)
        labels = {b["location_label"] for b in texts}
        assert all(lbl.startswith("章节 ") for lbl in labels)
        assert any("第" in lbl and "段" in lbl for lbl in labels)

    def test_table_blocks_indexed(self):
        doc = parse_document(read("normal.docx"), "normal.docx", "d-doc2")
        tables = [b for b in doc["blocks"] if b["block_type"] == "table"]
        assert tables
        assert tables[0]["location_type"] == LOC_TABLE
        assert tables[0]["location_value"] == 1
        assert "表格1" in tables[0]["location_label"]
        assert "|" in tables[0]["content"]

    def test_headings_keep_document_order(self):
        doc = parse_document(read("normal.docx"), "normal.docx", "d-doc3")
        seqs = [b["sequence"] for b in doc["blocks"]]
        assert seqs == sorted(seqs)


class TestUploadApi:
    def test_upload_pptx_and_docx_ok(self, client):
        for name, ftype in (("normal.pptx", "pptx"), ("normal.docx", "docx")):
            resp = client.post("/api/documents", files={"file": (name, read(name))})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["file_type"] == ftype
            assert body["unit_label"] == ("幻灯片" if ftype == "pptx" else "文档块")

    def test_upload_legacy_ppt_415(self, client):
        resp = client.post("/api/documents", files={"file": ("old.ppt", b"\xd0\xcf\x11\xe0junk")})
        assert resp.status_code == 415
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"

    def test_upload_txt_415(self, client):
        resp = client.post("/api/documents", files={"file": ("notes.txt", b"hello world notes")})
        assert resp.status_code == 415
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"

    def test_empty_pdf_upload(self, client):
        resp = client.post("/api/documents", files={"file": ("empty.pdf", b"")})
        assert resp.status_code == 400
        assert resp.json()["code"] == "EMPTY_FILE"
