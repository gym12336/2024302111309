"""Export the Chinese oral acceptance guide to Word using python-docx."""
import pathlib
import re
import sys

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "labs/lab2/验收演示说明书-口语版.md"
OUTPUT = SOURCE.with_suffix(".docx")


def font(target, name="宋体", size=11):
    target.font.name = name
    target.font.size = Pt(size)
    target._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), name)


def inline(paragraph, text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    for fragment in re.split(r"(\*\*.*?\*\*|`[^`]+`)", text):
        if not fragment:
            continue
        if fragment.startswith("**") and fragment.endswith("**"):
            run = paragraph.add_run(fragment[2:-2])
            run.bold = True
        elif fragment.startswith("`") and fragment.endswith("`"):
            run = paragraph.add_run(fragment[1:-1])
            font(run, "Consolas", 10)
        else:
            paragraph.add_run(fragment)


def shade(paragraph, color):
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), color)
    paragraph._p.get_or_add_pPr().append(element)


def field(paragraph, instruction):
    element = OxmlElement("w:fldSimple")
    element.set(qn("w:instr"), instruction)
    paragraph._p.append(element)


def main():
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    section.header_distance = section.footer_distance = Cm(0.8)

    normal = document.styles["Normal"]
    font(normal, "宋体", 11)
    normal.paragraph_format.line_spacing = 1.18
    normal.paragraph_format.space_after = Pt(5)
    for name, size in (("Title", 20), ("Heading 1", 15), ("Heading 2", 12)):
        style = document.styles[name]
        font(style, "微软雅黑", size)
        style.font.color.rgb = RGBColor.from_string("17365D")
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
    for name in ("List Bullet", "List Number"):
        font(document.styles[name], "宋体", 11)
    footer = section.footer.paragraphs[0]
    footer.alignment = 2
    footer.add_run("实验2验收演示 · 高一鸣　|　第 ")
    field(footer, "PAGE")
    footer.add_run(" 页 / 共 ")
    field(footer, "NUMPAGES")
    footer.add_run(" 页")
    for run in footer.runs:
        font(run, "宋体", 9)
    document.core_properties.title = "实验2验收演示说明书（口语版）"
    document.core_properties.author = "高一鸣"
    document.core_properties.subject = "依据Lab2学生版V2说明书，含现场操作、流程介绍和三道思考题"

    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            index += 1
            block = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            for position, value in enumerate(block):
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.05
                paragraph.paragraph_format.keep_with_next = position < len(block) - 1
                shade(paragraph, "F2F4F7")
                run = paragraph.add_run(value or " ")
                font(run, "Consolas", 9)
                run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            columns = len(rows[0])
            widths = {2: [4.2, 12.8], 3: [4.4, 5.4, 7.2], 4: [1.2, 4.4, 5.7, 5.7]}[columns]
            table = document.add_table(rows=0, cols=columns)
            table.style = "Table Grid"
            table.autofit = False
            for column, width in zip(table.columns, widths):
                column.width = Cm(width)
            for number, values in enumerate(rows):
                row = table.add_row()
                properties = row._tr.get_or_add_trPr()
                properties.append(OxmlElement("w:cantSplit"))
                if number == 0:
                    properties.append(OxmlElement("w:tblHeader"))
                for cell, value, width in zip(row.cells, values, widths):
                    cell.width = Cm(width)
                    paragraph = cell.paragraphs[0]
                    paragraph.paragraph_format.space_after = Pt(3)
                    paragraph.paragraph_format.space_before = Pt(3)
                    paragraph.paragraph_format.line_spacing = 1.05
                    inline(paragraph, value)
                    for run in paragraph.runs:
                        font(run, "宋体", 10)
                        run.bold = number == 0
                    if number == 0:
                        fill = OxmlElement("w:shd")
                        fill.set(qn("w:fill"), "DFEAF5")
                        cell._tc.get_or_add_tcPr().append(fill)
            document.add_paragraph().paragraph_format.space_after = Pt(1)
            continue
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match:
            depth = len(match[1])
            paragraph = document.add_paragraph(style="Title" if depth == 1 else f"Heading {depth-1}")
            inline(paragraph, match[2])
        elif line.startswith(">"):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.4)
            paragraph.paragraph_format.right_indent = Cm(0.2)
            shade(paragraph, "F3F7FC")
            inline(paragraph, line[1:].lstrip())
        elif line.startswith("- "):
            inline(document.add_paragraph(style="List Bullet"), line[2:])
        else:
            inline(document.add_paragraph(), line)
        index += 1
    document.save(OUTPUT)
    print(f"Created: {OUTPUT}")
    print(f"Source: {len(lines)} lines; Word: {len(document.paragraphs)} paragraphs, {len(document.tables)} tables")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
