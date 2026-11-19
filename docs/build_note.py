#!/usr/bin/env python3
"""Build the circulating copy of the Plane integration note.

pandoc produces the document; this script fixes what pandoc leaves to Word defaults — A4 with sane
margins, a readable type pairing, table columns that fit their content, header rows that repeat across
page breaks, and table rows that never split mid-row (which is what produced a half-row of prose
orphaned at the top of a page).

Usage:  python docs/build_note.py <markdown> <output.docx>
Requires: pandoc on PATH, python-docx.
"""
import os
import subprocess
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "Calibri"
HEAD_FONT = "Georgia"
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x44, 0x4C, 0x56)

# Column fractions per table, in document order. Each tuple sums to 1.0.
COLUMN_PLANS = [
    (0.18, 0.41, 0.41),               # §1  where the boundary sits
    (0.28, 0.72),                     # §2  the instance as it stands
    (0.24, 0.18, 0.10, 0.48),         # §4  field mapping
    (0.22, 0.44, 0.34),               # §5  secrets and where they live
    (0.12, 0.40, 0.16, 0.32),         # §7.6 endpoint map
    (0.34, 0.66),                     # §10 build record
]


def rgb(hex_str):
    return RGBColor(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def strip_theme(style):
    """Remove theme colour/font references.

    Pandoc's docx carries `w:themeColor="accent1"` and `w:asciiTheme="minorHAnsi"` on the heading
    styles. Those beat an explicit colour/font in some renderers, which is why a note styled for dark
    ink came out in Word's default blue sans.
    """
    rpr = style.element.find(qn("w:rPr"))
    if rpr is None:
        return
    color = rpr.find(qn("w:color"))
    if color is not None:
        for attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
            if color.get(qn(attr)) is not None:
                del color.attrib[qn(attr)]
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is not None:
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            if rfonts.get(qn(attr)) is not None:
                del rfonts.attrib[qn(attr)]


def set_cell_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "D5D9DE")
        borders.append(el)
    tbl_pr.append(borders)


def find_style(doc, name):
    """Look up a style by display name.

    `doc.styles["Heading 1"]` raises KeyError on documents whose built-in style is stored as
    "heading 1" — the display name and the lookup key do not always agree. Iterating is the reliable
    way in, and a missing style must never silently skip formatting.
    """
    for style in doc.styles:
        if style.name == name:
            return style
    return None


def style_paragraph(style, font, size, color=INK, bold=None, space_before=0, space_after=6,
                    line=1.25):
    style.font.name = font
    style.font.size = Pt(size)
    style.font.color.rgb = color
    if bold is not None:
        style.font.bold = bold
    style.paragraph_format.space_before = Pt(space_before)
    style.paragraph_format.space_after = Pt(space_after)
    style.paragraph_format.line_spacing = line
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), font)
    strip_theme(style)


def repeat_header_and_lock_rows(table):
    for i, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        tr_pr.append(cant)
        if i == 0:
            header = OxmlElement("w:tblHeader")
            tr_pr.append(header)
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.font.bold = True
                        run.font.size = Pt(9.5)


def set_column_widths(table, fractions, usable_cm):
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(fractions):
                cell.width = Cm(usable_cm * fractions[idx])


def tighten_code_paragraphs(doc):
    """Monospace blocks: no double spacing, and never split a block across a page break.

    A command that breaks mid-line across pages is unreadable, and this note's runbook sections are
    mostly commands.
    """
    runs, current = [], []
    prev = None

    def is_code(para):
        return para.style.name.lower().startswith(("source code", "verbatim", "preformatted"))

    for para in doc.paragraphs:
        if is_code(para):
            if not current and prev is not None:
                # the sentence introducing a command block should not be left stranded at a page foot
                prev.paragraph_format.keep_with_next = True
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.keep_together = True
            current.append(para)
            for run in para.runs:
                run.font.name = "Consolas"
                run.font.size = Pt(8.5)
        else:
            if current:
                runs.append(current)
                current = []
            prev = para
    if current:
        runs.append(current)

    for block in runs:
        for para in block[:-1]:
            para.paragraph_format.keep_with_next = True


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    md, out = sys.argv[1], sys.argv[2]
    raw = out.replace(".docx", ".raw.docx")

    subprocess.run(
        ["pandoc", md, "-f", "markdown", "-t", "docx", "-o", raw,
         "--metadata", "title=Agentic PMO — Plane Integration",
         "--metadata", "subtitle=Technical note and operating runbook",
         "--metadata", "date=19 November 2026"],
        check=True,
    )

    doc = Document(raw)

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)
        usable_cm = (section.page_width - section.left_margin - section.right_margin) / 360000

    styles = doc.styles
    normal = find_style(doc, "Normal")
    if normal is not None:
        style_paragraph(normal, BODY_FONT, 10, MUTED, space_after=6, line=1.25)

    # Inline code must stay monospaced: this note is mostly field names and paths, and losing the
    # distinction turns scannable text into prose.
    for name, size in (("Verbatim Char", 9), ("Verbatim", 9)):
        style = find_style(doc, name)
        if style is not None:
            style.font.name = "Consolas"
            style.font.size = Pt(size)
            style.font.color.rgb = INK
    strong = find_style(doc, "Strong")
    if strong is not None:
        strong.font.bold = True
        strong.font.name = BODY_FONT

    for name, size, before, after in (("Heading 1", 16, 16, 6), ("Heading 2", 12.5, 12, 4),
                                      ("Heading 3", 11, 10, 3)):
        style = find_style(doc, name)
        if style is not None:
            style_paragraph(style, HEAD_FONT, size, INK, bold=True,
                            space_before=before, space_after=after, line=1.15)

    # cover block: serif title, muted subtitle/date, then a page break before the body
    for name, size, colour, bold in (("Title", 26, INK, True),
                                     ("Subtitle", 13, MUTED, False),
                                     ("Date", 10, MUTED, False)):
        style = find_style(doc, name)
        if style is not None:
            style_paragraph(style, HEAD_FONT if name != "Date" else BODY_FONT, size, colour,
                            bold=bold, space_before=0, space_after=8 if name == "Title" else 4,
                            line=1.1)

    first_paras = list(doc.paragraphs)
    if first_paras:
        # push the title block down so the cover reads as a cover, not a header
        first_paras[0].paragraph_format.space_before = Pt(170)
    for para in first_paras:
        if para.style.name == "Date":
            para.add_run().add_break(WD_BREAK.PAGE)
            break
    # the markdown H1 repeats the cover title; keep it in the repo copy, drop it from the document
    for para in list(doc.paragraphs):
        if para.style.name == "Heading 1" and para.text.strip().lower().startswith("plane integration"):
            para._element.getparent().remove(para._element)
            break

    for i, table in enumerate(doc.tables):
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        if i < len(COLUMN_PLANS) and len(COLUMN_PLANS[i]) == len(table.columns):
            plan = COLUMN_PLANS[i]
        else:
            plan = tuple(1.0 / len(table.columns) for _ in table.columns)
        set_column_widths(table, plan, usable_cm)
        set_cell_borders(table)
        repeat_header_and_lock_rows(table)
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(0)
                    para.paragraph_format.line_spacing = 1.05
                    for run in para.runs:
                        run.font.size = run.font.size or Pt(8.5)

    tighten_code_paragraphs(doc)
    doc.save(out)
    os.remove(raw)
    print("wrote", out, "| tables:", len(doc.tables))


if __name__ == "__main__":
    main()
