"""生成多格式测试样例：课件 PPTX/DOCX（python-pptx/python-docx）与历年试卷。

用法: python scripts/make_office_samples.py
输出到 scripts/samples/:
  normal.pptx      3 张幻灯片（含表格）课件
  normal.docx      带两级标题与表格的课件
  exam_2022.docx   2022 年试卷（选择/填空/简答，题干含分值）
  exam_2023.docx   2023 年试卷（与 2022 有相同考点的不同表述，验证归一化）
  exam_2021.pdf    英文单选题 PDF 试卷（验证 PDF 拆题；分值/章节标未知）
"""

from pathlib import Path

from docx import Document
from make_samples import make_pdf
from pptx import Presentation
from pptx.util import Inches, Pt

OUT = Path(__file__).resolve().parent / "samples"


def _pptx():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Chapter 1: Newton's Laws"
    tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(3))
    tf = tb.text_frame
    tf.text = "The first law: an object stays at rest unless acted upon."
    p = tf.add_paragraph()
    p.text = "Key formula: F = m * a (second law)."
    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    slide2.shapes.title.text = "Chapter 2: Conservation of Energy"
    tb2 = slide2.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
    tb2.text_frame.text = "Total mechanical energy E = K + U is conserved."
    tbl = slide2.shapes.add_table(3, 2, Inches(1), Inches(4), Inches(6), Inches(1.5)).table
    tbl.cell(0, 0).text = "概念"
    tbl.cell(0, 1).text = "公式"
    tbl.cell(1, 0).text = "动能"
    tbl.cell(1, 1).text = "K = 1/2 m v^2"
    tbl.cell(2, 0).text = "势能"
    tbl.cell(2, 1).text = "U = m g h"
    slide3 = prs.slides.add_slide(prs.slide_layouts[5])
    slide3.shapes.title.text = "Chapter 3: Work and Power"
    tb3 = slide3.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(2))
    tf3 = tb3.text_frame
    tf3.text = "Work W = F * d * cos(theta) defines energy transfer."
    p3 = tf3.add_paragraph()
    p3.text = "Power P = W / t measures the rate of doing work."
    prs.save(OUT / "normal.pptx")


def _docx():
    doc = Document()
    doc.add_heading("力学与能量课件", level=1)
    doc.add_heading("第一章 牛顿运动定律", level=2)
    doc.add_paragraph("牛顿第一定律：物体在不受外力作用时保持静止或匀速直线运动状态。")
    doc.add_paragraph("牛顿第二定律说明加速度与合外力的关系，关键公式 F = m * a，其中 m 为质量。")
    doc.add_heading("第二章 能量守恒", level=2)
    doc.add_paragraph("机械能守恒定律：在只有保守力做功时，系统总机械能 E = K + U 保持不变。")
    doc.add_paragraph("动能公式 K = 1/2 m v^2，重力势能公式 U = m g h。")
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "物理量"
    table.cell(0, 1).text = "单位"
    table.cell(1, 0).text = "力 F"
    table.cell(1, 1).text = "牛顿（N）"
    table.cell(2, 0).text = "能量 E"
    table.cell(2, 1).text = "焦耳（J）"
    doc.add_heading("第三章 功与功率", level=2)
    doc.add_paragraph("功的定义 W = F * d * cos(theta)，表示力在位移方向上的能量传递。")
    doc.add_paragraph("功率 P = W / t 描述做功的快慢，单位为瓦特。")
    doc.save(OUT / "normal.docx")


def _exam_docx(name: str, lines: list[str]):
    doc = Document()
    doc.add_heading(lines[0], level=1)
    for line in lines[1:]:
        doc.add_paragraph(line)
    doc.save(OUT / name)


def _exams():
    _exam_docx(
        "exam_2022.docx",
        [
            "2022年春季学期物理期末考试试卷",
            "一、单项选择题（每题5分）",
            "1. 牛顿第二定律表达了力与加速度的关系，其公式为（5分）",
            "A. F = m * a",
            "B. F = m * v",
            "C. F = 1/2 m v^2",
            "D. F = m g h",
            "2. 关于机械能守恒，下列说法正确的是（5分）",
            "A. 总机械能 E = K + U 保持不变",
            "B. 动能一定不断增大",
            "C. 势能一定不断减小",
            "D. 摩擦力做正功时守恒",
            "二、填空题（每空3分）",
            "1. 重力势能的公式是 U = ____。（3分）",
            "2. 动能的计算公式为 K = ____。（3分）",
            "三、简答题（每题10分）",
            "1. 简述牛顿第一定律的内容及其适用条件。（10分）",
        ],
    )
    _exam_docx(
        "exam_2023.docx",
        [
            "2023年秋季学期物理期末考试试卷",
            "一、单项选择题（每题5分）",
            "1. 描述加速度与合外力关系的牛顿第二定律公式是（5分）",
            "A. F = m * a",
            "B. F = m * v^2",
            "C. E = K + U",
            "D. P = W / t",
            "2. 关于动能的计算，正确的是（5分）",
            "A. K = 1/2 m v^2",
            "B. K = m g h",
            "C. K = F * d",
            "D. K = P * t",
            "二、填空题（每空3分）",
            "1. 机械能守恒定律指出总机械能 E = ____。（3分）",
            "2. 功率的计算公式为 P = ____。（3分）",
            "三、简答题（每题10分）",
            "1. 什么是机械能守恒定律？（10分）",
        ],
    )
    (OUT / "exam_2021.pdf").write_bytes(
        make_pdf(
            [
                [
                    "2021 Final Exam - Mechanics (English sample)",
                    "1. Newton's second law is written as: (5 pts)",
                    "A. F = m * a   B. F = m * v   C. F = U   D. F = K",
                    "2. Kinetic energy equals: (5 pts)",
                    "A. K = 1/2 m v^2   B. K = mgh   C. K = Fd   D. K = Pt",
                ],
                [
                    "3. The law of energy conservation states E = K + U is constant. (5 pts)",
                    "A. True   B. False",
                    "4. Potential energy near earth surface is: (5 pts)",
                    "A. U = mgh   B. U = 1/2 mv^2   C. U = Ft   D. U = Pv",
                ],
            ]
        )
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    _pptx()
    _docx()
    _exams()
    print("office samples written to", OUT)


if __name__ == "__main__":
    main()
