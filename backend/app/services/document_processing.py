"""Uploaded document processing: validation → security checks → extraction → field proposals.

Uploaded files are untrusted. They are validated by content (magic bytes, not the
filename), checked for active content, and their text is only ever treated as data.
Extracted fields are *proposals*; they become case facts only when the user accepts them.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

from app.agents import extract as ex
from app.agents.safety import detect_injection
from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED = {
    "application/pdf": (".pdf",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
}


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ValidatedUpload:
    content_type: str
    safe_name: str
    flags: list[str] = field(default_factory=list)


def sniff_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            return None
    return None


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^\w.\- ()ऀ-ॿ]", "_", base).strip(" .")
    return (base or "document")[:120]


def validate_upload(filename: str, data: bytes) -> ValidatedUpload:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise UploadRejected("empty_file", "The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected("too_large", f"The file is larger than {get_settings().max_upload_mb} MB.")
    content_type = sniff_type(data)
    if content_type is None:
        raise UploadRejected("unsupported_type", "Only PDF, DOCX, JPG and PNG files are supported.")
    name = safe_filename(filename)
    if not name.lower().endswith(ALLOWED[content_type]):
        name = f"{name.rsplit('.', 1)[0]}{ALLOWED[content_type][0]}"
    flags: list[str] = []

    if content_type == "application/pdf":
        head = data[: 2_000_000]
        if re.search(rb"/JavaScript|/JS\s*[(<]|/Launch|/EmbeddedFile|/RichMedia", head):
            raise UploadRejected("active_content", "This PDF contains scripts or embedded files and was rejected "
                                 "for your safety. Please print it to a new PDF and upload that.")
        if b"/Encrypt" in head:
            flags.append("encrypted_pdf")
    elif content_type.startswith("application/vnd.openxml"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if any("vbaProject" in n or n.endswith(".bin") for n in names):
                raise UploadRejected("macros", "Documents with macros are not accepted.")
            total = sum(i.file_size for i in zf.infolist())
            if total > 50 * 1024 * 1024 or len(names) > 2000:
                raise UploadRejected("zip_bomb", "This document is malformed or too large when expanded.")
    else:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 60_000_000
        try:
            with Image.open(io.BytesIO(data)) as img:
                # Explicit limit: Pillow only warns below 2x MAX_IMAGE_PIXELS, and OCR decodes fully.
                if img.width * img.height > 40_000_000:
                    raise UploadRejected("image_too_large", "The image resolution is too large. Please resize it.")
                img.verify()
        except UploadRejected:
            raise
        except Exception as exc:  # noqa: BLE001 - any decoder error means reject
            raise UploadRejected("bad_image", "The image could not be read.") from exc
    return ValidatedUpload(content_type, name, flags)


@dataclass
class ExtractionResult:
    method: str
    text: str
    page_count: int | None
    needs_ocr: bool
    language_hint: str | None
    fields: dict[str, Any]
    document_class: str
    injection_flags: list[str]


def _ocr_image(data: bytes) -> str | None:
    if get_settings().ocr_provider != "tesseract":
        return None
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    if get_settings().tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd
    try:
        with Image.open(io.BytesIO(data)) as img:
            return pytesseract.image_to_string(img, lang="eng+hin")
    except Exception:  # noqa: BLE001 - binary missing or language packs absent
        logger.warning("OCR failed or Tesseract is not installed")
        return None


def ocr_available() -> bool:
    try:
        import shutil

        import pytesseract  # noqa: F401

        return bool(get_settings().tesseract_cmd or shutil.which("tesseract"))
    except ImportError:
        return False


DOC_CLASSES = {
    "invoice": ["tax invoice", "invoice", "bill of supply", "gstin", "invoice no", "बिल"],
    "order_confirmation": ["order id", "order number", "order confirmed", "your order", "order placed"],
    "warranty": ["warranty", "guarantee card", "वारंटी"],
    "communication": ["dear customer", "regards", "from:", "subject:", "wrote:", "ticket"],
    "payment_proof": ["upi", "transaction id", "utr", "debited", "payment successful"],
}


def classify_text(text: str) -> str:
    lowered = text.lower()
    scores = {k: sum(lowered.count(w) for w in words) for k, words in DOC_CLASSES.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "other"


def extract_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    amounts = ex.find_amounts(text)
    total = re.search(r"(?:grand total|total amount|amount paid|total)\s*[:₹rs.\s]*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if total:
        fields["amount_paid"] = {"value": total.group(1).replace(",", ""), "excerpt": ex._excerpt(text, total.start(), total.end())}
    elif amounts:
        top = max(amounts, key=lambda a: a[0])
        fields["amount_paid"] = {"value": str(top[0]), "excerpt": top[1], "note": "largest amount found"}
    dates = ex.find_dates(text)
    if dates:
        fields["purchase_date"] = {"value": dates[0][0].isoformat(), "excerpt": dates[0][1]}
    for key, pattern in (("order_id", ex.ORDER_ID), ("invoice_number", ex.INVOICE_NO)):
        m = pattern.search(text)
        if m:
            fields[key] = {"value": m.group(1), "excerpt": ex._excerpt(text, m.start(), m.end())}
    m = ex.GSTIN.search(text)
    if m:
        fields["seller_gstin"] = {"value": m.group(0), "excerpt": ex._excerpt(text, m.start(), m.end())}
    m = re.search(r"(?:sold by|seller|vendor|billed by)\s*[:\-]?\s*([A-Z][\w&.,\- ]{2,60})", text, re.I)
    if m:
        fields["seller_name"] = {"value": m.group(1).strip(" ,."), "excerpt": ex._excerpt(text, m.start(), m.end())}
    emails = ex.EMAIL.findall(text)
    if emails:
        fields["emails"] = {"value": ", ".join(sorted(set(emails))[:3]), "excerpt": None}
    return fields


def extract_document(content_type: str, data: bytes) -> ExtractionResult:
    text, method, pages, needs_ocr = "", "none", None, False
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                return ExtractionResult("none", "", None, False, None, {}, "other", ["encrypted"])
        pages = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:60])
        method = "pdf_text"
        if len(text.strip()) < 30:
            needs_ocr, method = True, "pdf_text_empty"
    elif content_type.startswith("application/vnd.openxml"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        text, method = "\n".join(parts), "docx"
    else:
        ocr = _ocr_image(data)
        if ocr is None:
            needs_ocr, method = True, "ocr_unavailable"
        else:
            text, method = ocr, "ocr_tesseract"
    text = text[:200_000]
    lang = "hi" if re.search(r"[ऀ-ॿ]", text) else ("en" if text.strip() else None)
    return ExtractionResult(
        method=method, text=text, page_count=pages, needs_ocr=needs_ocr, language_hint=lang,
        fields=extract_fields(text) if text else {}, document_class=classify_text(text) if text else "other",
        injection_flags=detect_injection(text) if text else [],
    )
