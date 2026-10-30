"""Verification agent: checks drafts for completeness, consistency and support.

Deterministic checks only - the result must be reproducible and explainable.
Severity "blocker" prevents approval; "warning" must be acknowledged by the user.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from app.documents.templates import PLACEHOLDER
from app.models.enums import FactProvenance
from app.services.facts import parse_date, parse_money


def _issue(code: str, severity: str, message_en: str, message_hi: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message_en": message_en, "message_hi": message_hi, **extra}


def _all_text(content: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in content.get("blocks", []):
        parts.append(block.get("text", ""))
        parts.extend(block.get("items", []))
        for row in block.get("rows", []):
            parts.extend(row)
    return "\n".join(parts)


def verify_document(
    content: dict[str, Any],
    *,
    facts: list[dict[str, Any]],
    outcomes: dict[str, Any],
    evidence: list[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    text = _all_text(content)
    doc_type = content.get("doc_type")

    placeholders = text.count(PLACEHOLDER)
    if placeholders:
        missing_blocks = [b["id"] for b in content.get("blocks", [])
                          if PLACEHOLDER in (b.get("text", "") + "".join(b.get("items", []))
                                             + "".join("".join(r) for r in b.get("rows", [])))]
        issues.append(_issue(
            "missing_fields", "blocker",
            f"{placeholders} required detail(s) are still missing (shown as {PLACEHOLDER}).",
            f"{placeholders} ज़रूरी जानकारी अभी बाकी है ({PLACEHOLDER} से दिखाई गई)।",
            blocks=missing_blocks,
        ))

    by_key: dict[str, list[dict[str, Any]]] = {}
    for f in facts:
        by_key.setdefault(f["key"], []).append(f)

    # Unconfirmed inferences must not reach a document.
    for key, items in by_key.items():
        if items and all(i["provenance"] == FactProvenance.AI_INFERENCE for i in items):
            issues.append(_issue(
                "unconfirmed_inference", "warning",
                f"'{key.replace('_', ' ')}' was guessed by NyayaSetu and has not been confirmed by you.",
                f"'{key}' का अनुमान NyayaSetu ने लगाया है, आपने इसकी पुष्टि नहीं की है।", fact_key=key,
            ))

    # Conflicting values between sources (e.g. user said ₹45,000; invoice shows ₹42,999).
    for key in ("amount_paid", "purchase_date", "seller_name"):
        values: dict[str, str] = {}
        for f in by_key.get(key, []):
            values.setdefault(f["value"].strip().lower(), f["provenance"])
        if key == "amount_paid":
            amounts = {str(parse_money(v)) for v in values}
            conflict = len(amounts) > 1
        else:
            conflict = len(values) > 1
        if conflict:
            issues.append(_issue(
                "conflicting_facts", "blocker",
                f"Different values were found for '{key.replace('_', ' ')}': "
                + "; ".join(f"{v} ({p.replace('_', ' ')})" for v, p in values.items())
                + ". Please confirm the correct one.",
                f"'{key}' के लिए अलग-अलग जानकारी मिली है। कृपया सही जानकारी की पुष्टि करें।", fact_key=key,
            ))

    purchase = parse_date((by_key.get("purchase_date") or [{}])[-1].get("value"))
    problem = parse_date((by_key.get("problem_date") or [{}])[-1].get("value"))
    if purchase and purchase > today:
        issues.append(_issue("future_date", "blocker", "The purchase date is in the future.",
                             "खरीद की तारीख भविष्य में है।"))
    if purchase and problem and problem < purchase:
        issues.append(_issue("date_order", "blocker",
                             "The problem date is before the purchase date. Please check both dates.",
                             "समस्या की तारीख खरीद की तारीख से पहले है। कृपया दोनों तारीखें जाँचें।"))

    amount = parse_money((by_key.get("amount_paid") or [{}])[-1].get("value"))
    if amount is not None and amount <= Decimal(0):
        issues.append(_issue("invalid_amount", "blocker", "The amount paid must be more than zero.",
                             "भुगतान की राशि शून्य से अधिक होनी चाहिए।"))

    lim = outcomes.get("limitation") or {}
    if lim.get("value", {}).get("status") == "expired":
        issues.append(_issue(
            "limitation_expired", "warning",
            "The two-year time limit appears to have passed. The complaint must explain the delay, and you "
            "should get advice from a lawyer or free legal aid (NALSA 15100).",
            "दो साल की समय सीमा बीत चुकी लगती है। शिकायत में देरी का कारण बताना होगा; वकील या मुफ़्त कानूनी "
            "सहायता (नालसा 15100) से सलाह लें।",
        ))
    status = (outcomes.get("consumer_status") or {}).get("value", {}).get("status")
    if status == "may_not_be_consumer":
        issues.append(_issue(
            "consumer_status", "blocker",
            "Based on your answers you may not be a 'consumer' under the Act. Please get professional advice "
            "before filing.",
            "आपके जवाबों के अनुसार आप कानून के तहत 'उपभोक्ता' नहीं भी हो सकते। शिकायत से पहले पेशेवर सलाह लें।",
        ))
    for key, outcome in outcomes.items():
        if outcome and not outcome.get("grounded"):
            issues.append(_issue(
                "ungrounded_rule", "warning",
                f"The official source for '{key.replace('_', ' ')}' is not available in the knowledge base.",
                f"'{key}' का आधिकारिक स्रोत उपलब्ध नहीं है।",
            ))

    if doc_type == "consumer_complaint":
        if not evidence:
            issues.append(_issue("no_evidence", "warning",
                                 "No evidence has been added. Complaints are much stronger with a bill, "
                                 "order confirmation or photos.",
                                 "कोई सबूत नहीं जोड़ा गया है। बिल, ऑर्डर पुष्टि या फोटो से शिकायत मज़बूत होती है।"))
        if re.search(r"\[Edit this paragraph", text):
            issues.append(_issue("edit_required", "warning",
                                 "One paragraph asks you to describe the defect or deficiency in your own words.",
                                 "एक पैराग्राफ में आपको दोष या कमी अपने शब्दों में लिखनी है।"))
        if amount is not None and str(int(amount)) not in re.sub(r"[,\s]", "", text) and PLACEHOLDER not in text:
            issues.append(_issue("amount_mismatch", "blocker",
                                 "The amount in the draft does not match the confirmed amount paid.",
                                 "ड्राफ़्ट में राशि पुष्टि की गई राशि से मेल नहीं खाती।"))

    blockers = [i for i in issues if i["severity"] == "blocker"]
    return {
        "status": "blocked" if blockers else ("needs_attention" if issues else "ok"),
        "issues": issues,
        "checked_on": today.isoformat(),
    }
