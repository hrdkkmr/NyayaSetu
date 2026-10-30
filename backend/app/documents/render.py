"""Render structured document content to PDF and DOCX.

Rendering is deterministic: the same version content always yields the same
document, so files are produced on demand instead of being stored.
"""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _pdf_text(text: str) -> str:
    # The built-in PDF fonts have no rupee glyph.
    return escape(text.replace("₹", "Rs. "))


def render_pdf(content: dict[str, Any], *, version_label: str, draft: bool) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Times-Roman", fontSize=11.5, leading=16)
    heading = ParagraphStyle("heading", parent=body, fontName="Times-Bold", fontSize=12.5, alignment=TA_CENTER,
                             spaceAfter=6)
    sub = ParagraphStyle("sub", parent=heading, fontSize=11.5)
    notice = ParagraphStyle("notice", parent=body, fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
                            textColor=colors.HexColor("#7a4b00"), backColor=colors.HexColor("#fff6e0"),
                            borderPadding=5, spaceAfter=8)

    def on_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        footer = f"{content.get('title', '')} — {version_label}"
        if draft:
            footer += " — DRAFT, NOT APPROVED"
        canvas.drawString(18 * mm, 10 * mm, footer)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    flow: list[Any] = []
    number = 0
    for block in content.get("blocks", []):
        kind, text = block.get("type"), block.get("text", "")
        if kind == "notice":
            flow.append(Paragraph(_pdf_text(text), notice))
        elif kind == "heading":
            flow.append(Paragraph(_pdf_text(text), heading))
        elif kind == "subheading":
            flow.append(Spacer(1, 4))
            flow.append(Paragraph(f"<u>{_pdf_text(text)}</u>", sub))
        elif kind == "parties":
            for item in block.get("items", []):
                style = sub if item == "Versus" else body
                flow.append(Paragraph(_pdf_text(item), style))
            flow.append(Spacer(1, 6))
        elif kind == "numbered":
            number += 1
            flow.append(Paragraph(f"{number}. {_pdf_text(text)}", body))
            flow.append(Spacer(1, 4))
        elif kind == "list":
            items = [ListItem(Paragraph(_pdf_text(i), body), leftIndent=12) for i in block.get("items", [])]
            flow.append(ListFlowable(items, bulletType="a", start="a", leftIndent=18))
        elif kind == "table":
            rows = [[Paragraph(_pdf_text(c), body) for c in row] for row in block.get("rows", [])]
            if rows:
                table = Table(rows, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                flow.append(table)
        elif kind == "signature":
            flow.append(Spacer(1, 14))
            for item in block.get("items", []):
                flow.append(Paragraph(_pdf_text(item), body))
        else:
            flow.append(Paragraph(_pdf_text(text), body))
            flow.append(Spacer(1, 4))

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=18 * mm, title=content.get("title", "Document"),
                            author="Prepared with NyayaSetu")
    doc.build(flow, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


def render_docx(content: dict[str, Any], *, version_label: str, draft: bool) -> bytes:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    number = 0
    for block in content.get("blocks", []):
        kind, text = block.get("type"), block.get("text", "")
        if kind == "notice":
            p = document.add_paragraph()
            run = p.add_run(text)
            run.italic = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x7A, 0x4B, 0x00)
        elif kind in ("heading", "subheading"):
            p = document.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.underline = kind == "subheading"
        elif kind == "parties":
            for item in block.get("items", []):
                p = document.add_paragraph(item)
                if item == "Versus":
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif kind == "numbered":
            number += 1
            document.add_paragraph(f"{number}. {text}")
        elif kind == "list":
            for i, item in enumerate(block.get("items", [])):
                document.add_paragraph(f"({chr(97 + i)}) {item}")
        elif kind == "table":
            rows = block.get("rows", [])
            if rows:
                table = document.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, cell in enumerate(row):
                        table.cell(r, c).text = cell
        elif kind == "signature":
            document.add_paragraph()
            for item in block.get("items", []):
                document.add_paragraph(item)
        else:
            document.add_paragraph(text)
    footer = document.sections[0].footer.paragraphs[0]
    footer.text = f"{content.get('title', '')} — {version_label}" + (" — DRAFT, NOT APPROVED" if draft else "")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
