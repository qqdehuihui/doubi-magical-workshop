"""生成冒烟测试用的样本文件（手写最小 PDF，不依赖第三方库）。

用法: python scripts/make_samples.py
输出到 scripts/samples/:
  normal.pdf  2 页文本 PDF（验证页码解析）
  scanned.pdf 3 页全空白（验证 SCANNED_PDF 提示）
  empty.pdf   0 字节（验证 EMPTY_FILE 提示）
  fake.pdf    内容是文本的假 PDF（扩展名 .pdf 但魔数不符，验证 INVALID_FILE 提示）
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent / "samples"


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    font_obj = 3
    first_page_obj = 4
    kids = " ".join(f"{first_page_obj + i * 2} 0 R" for i in range(len(pages)))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for lines in pages:
        page_num = len(objects) + 1
        content_num = page_num + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {font_obj} 0 R >> >> "
                f"/MediaBox [0 0 612 792] /Contents {content_num} 0 R >>"
            ).encode()
        )
        show_text = "\n".join(
            f"1 0 0 1 60 {720 - idx * 16} Tm ({_esc(line)}) Tj" for idx, line in enumerate(lines)
        )
        stream = f"BT\n/F1 12 Tf\n{show_text}\nET\n"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}endstream".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "normal.pdf").write_bytes(
        make_pdf(
            [
                [
                    "Chapter 1: Newton's Laws of Motion",
                    "The first law: an object stays at rest unless acted upon.",
                    "Key formula: F = m * a (second law).",
                ],
                [
                    "Chapter 2: Conservation of Energy",
                    "Total mechanical energy E = K + U is conserved.",
                    "Kinetic energy K = 1/2 m v^2. Potential energy U = m g h.",
                ],
            ]
        )
    )
    (OUT / "scanned.pdf").write_bytes(make_pdf([[], [], []]))
    (OUT / "empty.pdf").write_bytes(b"")
    (OUT / "fake.pdf").write_bytes(b"this is not a pdf, just text pretending to be one.")
    print("samples written to", OUT)


if __name__ == "__main__":
    main()
