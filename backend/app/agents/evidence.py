"""AI evidence extraction: structured fields from an uploaded bill, invoice, warranty card or screenshot.

Runs after OCR / PDF text extraction and the pattern-based extractor, only when the user has
consented to external AI. The document text is untrusted (`safety.wrap_untrusted`). A field is kept
only if its supporting quote really appears in the document text; nothing becomes a case fact until
the user accepts it in the review step (`documents.accept_fields`).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agents.llm import LLMProvider, LLMRefusalError, LLMUnavailableError
from app.agents.safety import wrap_untrusted

logger = logging.getLogger(__name__)

# Field name → what it means. Names match the pattern extractor where both find the same thing.
EVIDENCE_FIELDS = {
    "seller_name": "the seller or service provider who issued the document",
    "brand_name": "the brand or manufacturer of the product",
    "product": "the product or service bought",
    "purchase_date": "the invoice / purchase date, as YYYY-MM-DD",
    "invoice_number": "the invoice or bill number",
    "amount_paid": "the total amount paid in rupees, digits only",
    "seller_gstin": "the seller's 15-character GSTIN",
    "defect_summary": "a short description of a defect or problem the document shows (screenshots, chats)",
}


class EvidenceField(BaseModel):
    name: str = Field(description="One of the allowed field names.")
    value: str
    quote: str = Field(description="The exact words in the document that show this value.")


class EvidenceExtraction(BaseModel):
    fields: list[EvidenceField]


SYSTEM = (
    "You read one document a consumer uploaded (a bill, invoice, warranty card, order page or a screenshot "
    "of a defect or chat) and list the facts it shows. Only report what the document itself says; never "
    "guess. For every field give the exact quote from the document. Allowed fields:\n"
    + "\n".join(f"- {k}: {v}" for k, v in EVIDENCE_FIELDS.items())
    + "\nLeave out any field the document does not show."
)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _valid(name: str, value: str) -> bool:
    if name == "amount_paid":
        return re.fullmatch(r"\d{1,12}(\.\d{1,2})?", value) is not None
    if name == "purchase_date":
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None
    if name == "seller_gstin":
        return re.fullmatch(r"[0-9A-Z]{15}", value) is not None
    return 0 < len(value) <= 300


async def extract_with_llm(llm: LLMProvider, text: str) -> dict[str, Any]:
    """Fields the model found and the document text supports. Empty on any LLM failure."""
    if not text.strip():
        return {}
    try:
        result = await llm.structured(
            system=SYSTEM, messages=[{"role": "user", "content": wrap_untrusted("upload", text, limit=8000)}],
            schema=EvidenceExtraction, max_tokens=1200,
        )
    except (LLMUnavailableError, LLMRefusalError) as exc:
        logger.info("AI evidence extraction skipped: %s", exc)
        return {}
    document = _norm(text)
    out: dict[str, Any] = {}
    for f in result.value.fields:
        name, value, quote = f.name.strip(), f.value.strip(), f.quote.strip()
        if name not in EVIDENCE_FIELDS or name in out or not quote or not _valid(name, value):
            continue
        if _norm(quote) not in document:  # the model must point at real text in the upload
            continue
        out[name] = {"value": value, "excerpt": quote[:300], "method": "ai"}
    return out


def merge_fields(pattern_fields: dict[str, Any], ai_fields: dict[str, Any]) -> dict[str, Any]:
    """Pattern matches win (they quote the text directly); AI fills only the gaps."""
    return {**ai_fields, **pattern_fields}
