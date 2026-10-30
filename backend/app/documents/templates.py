"""Deterministic document templates for consumer complaints.

Templates assemble documents from (a) facts the user stated or confirmed, (b)
grounded rule outcomes, and (c) the evidence index. The LLM never writes clauses,
headings or formats. Every block records the facts/citations it was built from.
Unknown values are rendered as visible placeholders "[●]" that the verifier flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domains.consumer.rules import REMEDY_TO_CLAUSE, _inr

TEMPLATE_VERSION = "1.0"
PLACEHOLDER = "[●]"

DRAFT_NOTICE = (
    "DRAFT prepared with NyayaSetu for the complainant's review. It is not legal advice and has not been "
    "reviewed by an advocate. Check it carefully, correct anything that is wrong, and confirm the "
    "current format required by the Commission or the e-Jagriti portal before filing."
)

DOC_TYPES: dict[str, str] = {
    "consumer_complaint": "Consumer Complaint (Draft)",
    "memo_of_parties": "Memo of Parties",
    "list_of_dates": "List of Dates and Events",
    "evidence_index": "Index of Documents / Annexures",
    "filing_checklist": "Filing Checklist",
}

FORUM_NAMES = {
    "district": "DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION",
    "state": "STATE CONSUMER DISPUTES REDRESSAL COMMISSION",
    "national": "NATIONAL CONSUMER DISPUTES REDRESSAL COMMISSION",
}


@dataclass
class DraftContext:
    slots: dict[str, dict[str, Any]]
    outcomes: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    today: date

    def fact(self, key: str) -> str | None:
        slot = self.slots.get(key)
        if not slot or slot.get("provenance") == "ai_inference":
            return None
        return slot.get("value")

    def fact_id(self, key: str) -> str | None:
        slot = self.slots.get(key)
        return slot.get("fact_id") if slot else None

    def outcome(self, key: str) -> dict[str, Any] | None:
        o = self.outcomes.get(key)
        return o if o and o.get("grounded") else None


def _v(value: str | None) -> str:
    return value if value else PLACEHOLDER


def _date(value: str | None) -> str:
    if not value:
        return PLACEHOLDER
    try:
        return date.fromisoformat(value[:10]).strftime("%d %B %Y")
    except ValueError:
        return value


def _money(value: str | None) -> str:
    if not value:
        return PLACEHOLDER
    try:
        return _inr(Decimal(value))
    except (ArithmeticError, ValueError):
        return value


def _block(kind: str, text: str = "", *, block_id: str, facts: list[str | None] | None = None,
           refs: list[str] | None = None, items: list[str] | None = None, editable: bool = True,
           rows: list[list[str]] | None = None) -> dict[str, Any]:
    return {
        "id": block_id, "type": kind, "text": text, "items": items or [], "rows": rows or [],
        "editable": editable, "sources": {"facts": [f for f in (facts or []) if f], "refs": refs or []},
    }


def _ref(outcome: dict[str, Any] | None) -> list[str]:
    if not outcome:
        return []
    return [f"{b['document_key']}:{b['section_ref']}" for b in outcome.get("basis", [])]


def consumer_complaint(ctx: DraftContext) -> dict[str, Any]:
    forum_outcome = ctx.outcome("pecuniary_forum")
    forum = forum_outcome["value"] if forum_outcome else None
    location = ctx.fact("complainant_location")
    forum_line = FORUM_NAMES.get(forum or "", "CONSUMER DISPUTES REDRESSAL COMMISSION " + PLACEHOLDER)
    if forum == "district":
        forum_line += f", {location.upper() if location else PLACEHOLDER}"

    name, address = ctx.fact("complainant_name"), ctx.fact("complainant_address")
    seller, seller_addr = ctx.fact("seller_name"), ctx.fact("seller_address")
    product, amount = ctx.fact("product_or_service"), ctx.fact("amount_paid")
    purchase_date, problem_date = ctx.fact("purchase_date"), ctx.fact("problem_date")
    mode = ctx.fact("purchase_mode")
    mode_phrase = {"online": " through an online purchase", "offline": " from the Opposite Party's premises"}.get(mode or "", "")

    blocks: list[dict[str, Any]] = [
        _block("notice", DRAFT_NOTICE, block_id="notice", editable=False),
        _block("heading", f"BEFORE THE {forum_line}", block_id="forum", refs=_ref(forum_outcome), editable=False),
        _block("subheading", "CONSUMER COMPLAINT NO. ______ OF ______", block_id="case_no", editable=False),
        _block("parties", "", block_id="parties", facts=[ctx.fact_id(k) for k in
               ("complainant_name", "complainant_address", "seller_name", "seller_address")], items=[
            f"{_v(name)}, residing at {_v(address)} ... Complainant",
            "Versus",
            f"{_v(seller)}, {('having its address at ' + seller_addr) if seller_addr else 'address ' + PLACEHOLDER} ... Opposite Party",
        ], editable=False),
        _block("subheading", "COMPLAINT UNDER SECTION 35 OF THE CONSUMER PROTECTION ACT, 2019",
               block_id="title", refs=["cpa_2019:Section 35"], editable=False),
        _block("para", "The Complainant most respectfully submits as follows:", block_id="intro"),
    ]

    facts_paras = [
        (f"The Complainant purchased/availed {_v(product)} from the Opposite Party{mode_phrase} on "
         f"{_date(purchase_date)} and paid {_money(amount)} for it. The Complainant did so for personal use and "
         "is a consumer within the meaning of section 2(7) of the Consumer Protection Act, 2019.",
         ["product_or_service", "purchase_mode", "purchase_date", "amount_paid", "commercial_purpose"],
         ["cpa_2019:Section 2(7)"]),
        (f"The Complainant's grievance, in the Complainant's own words: {_v(ctx.fact('grievance'))}",
         ["grievance"], []),
        (f"The problem arose on or about {_date(problem_date)}.", ["problem_date"], []),
    ]
    contacted = ctx.fact("contacted_seller")
    if contacted:
        facts_paras.append((f"The Complainant raised the matter with the Opposite Party: {contacted}",
                            ["contacted_seller"], []))
    facts_paras.append((
        "The acts and omissions of the Opposite Party amount to a defect in goods and/or deficiency in service "
        "within the meaning of sections 2(10) and 2(11) of the Act. [Edit this paragraph to describe exactly "
        "how the goods were defective or the service was deficient.]",
        [], ["cpa_2019:Section 2(10)", "cpa_2019:Section 2(11)"]))
    if ctx.evidence:
        facts_paras.append(("Copies of the documents relied upon by the Complainant are filed with this "
                             "complaint as listed in the Index of Documents.", [], []))

    for i, (text, keys, refs) in enumerate(facts_paras, start=1):
        blocks.append(_block("numbered", text, block_id=f"fact_{i}", facts=[ctx.fact_id(k) for k in keys], refs=refs))

    n = len(facts_paras)
    juris_parts = []
    if forum_outcome:
        juris_parts.append(
            f"The value of the goods/services paid as consideration is {_money(amount)}, which is within the "
            "pecuniary jurisdiction of this Commission under the Consumer Protection (Jurisdiction of the District "
            "Commission, the State Commission and the National Commission) Rules, 2021.")
    else:
        juris_parts.append(f"Pecuniary jurisdiction: {PLACEHOLDER} (amount paid not yet confirmed).")
    juris_parts.append(
        f"This Commission has territorial jurisdiction under section 34(2) of the Act as the Complainant resides "
        f"or personally works for gain at {_v(location)}. [Edit if you are relying on a different ground.]")
    blocks.append(_block("numbered", " ".join(juris_parts), block_id="jurisdiction",
                         facts=[ctx.fact_id("amount_paid"), ctx.fact_id("complainant_location")],
                         refs=_ref(forum_outcome) + ["cpa_2019:Section 34"]))

    lim = ctx.outcome("limitation")
    if lim:
        lim_text = (f"The cause of action arose on or about {_date(problem_date or purchase_date)}. The complaint is "
                    "filed within two years as required by section 69 of the Act.")
        if lim["value"]["status"] == "expired":
            lim_text = (f"The cause of action arose on or about {_date(problem_date or purchase_date)}. The "
                        "Complainant seeks condonation of delay under section 69(2) of the Act for the following "
                        f"sufficient cause: {PLACEHOLDER}")
    else:
        lim_text = f"Limitation: {PLACEHOLDER} (date of cause of action not yet confirmed)."
    blocks.append(_block("numbered", lim_text, block_id="limitation",
                         facts=[ctx.fact_id("problem_date"), ctx.fact_id("purchase_date")], refs=_ref(lim)))

    fee = ctx.outcome("filing_fee")
    fee_text = (f"The Complainant will pay the fee applicable under rule 7 of the Consumer Protection (Consumer "
                f"Disputes Redressal Commissions) Rules, 2020, which for this value is Rs. {fee['value']}."
                if fee and fee["value"] else
                "No fee is payable for this value under rule 7 of the Consumer Protection (Consumer Disputes "
                "Redressal Commissions) Rules, 2020, as amended." if fee else f"Fee: {PLACEHOLDER}")
    blocks.append(_block("numbered", fee_text, block_id="fee", facts=[ctx.fact_id("amount_paid")], refs=_ref(fee)))

    remedies = [r.strip() for r in (ctx.fact("desired_remedy") or "").split(",") if r.strip()]
    prayer: list[str] = []
    for remedy in remedies:
        if remedy == "replacement":
            prayer.append(f"direct the Opposite Party to replace the {_v(product)} with a new one free from defect;")
        elif remedy == "refund":
            prayer.append(f"direct the Opposite Party to refund {_money(amount)} with interest as this Commission "
                          "deems fit;")
        elif remedy == "repair":
            prayer.append("direct the Opposite Party to remove the defect / deficiency;")
        elif remedy == "compensation":
            prayer.append(f"direct the Opposite Party to pay compensation of Rs. {PLACEHOLDER} for the loss and "
                          "harassment suffered;")
    if not prayer:
        prayer.append(f"grant the following relief: {PLACEHOLDER};")
    prayer.append("award the costs of this complaint; and")
    prayer.append("pass any other order that this Commission deems fit in the interest of justice.")
    blocks.append(_block("subheading", "PRAYER", block_id="prayer_head", editable=False))
    blocks.append(_block("para", "In view of the above, the Complainant prays that this Commission may be pleased to:",
                         block_id="prayer_intro"))
    blocks.append(_block("list", "", block_id="prayer", items=prayer, facts=[ctx.fact_id("desired_remedy")],
                         refs=[f"cpa_2019:{REMEDY_TO_CLAUSE[r][0]}" for r in remedies if r in REMEDY_TO_CLAUSE]))
    blocks.append(_block("signature", "", block_id="signature", items=[
        f"Place: {_v(location)}", "Date: ____________", f"Signature of the Complainant ({_v(name)})"], editable=False))
    blocks.append(_block("subheading", "VERIFICATION", block_id="verification_head", editable=False))
    blocks.append(_block("para",
                         f"I, {_v(name)}, the Complainant, verify that the contents of paragraphs 1 to {n + 3} are "
                         "true and correct to my knowledge and belief, and nothing material has been concealed.",
                         block_id="verification", facts=[ctx.fact_id("complainant_name")]))
    blocks.append(_block("notice", "The Commission or portal may require this complaint to be supported by an "
                         "affidavit. NyayaSetu does not sign, notarise or file on your behalf.",
                         block_id="affidavit_note", editable=False))
    return {"title": DOC_TYPES["consumer_complaint"], "doc_type": "consumer_complaint", "blocks": blocks}


def memo_of_parties(ctx: DraftContext) -> dict[str, Any]:
    rows = [
        ["Complainant", _v(ctx.fact("complainant_name")), _v(ctx.fact("complainant_address"))],
        ["Opposite Party", _v(ctx.fact("seller_name")), _v(ctx.fact("seller_address"))],
    ]
    return {"title": DOC_TYPES["memo_of_parties"], "doc_type": "memo_of_parties", "blocks": [
        _block("notice", DRAFT_NOTICE, block_id="notice", editable=False),
        _block("heading", "MEMO OF PARTIES", block_id="head", editable=False),
        _block("table", "", block_id="parties", rows=[["Party", "Name", "Address"], *rows],
               facts=[ctx.fact_id(k) for k in ("complainant_name", "complainant_address", "seller_name",
                                               "seller_address")], editable=False),
    ]}


def list_of_dates(ctx: DraftContext) -> dict[str, Any]:
    events: list[tuple[str, str, str | None]] = []
    if ctx.fact("purchase_date"):
        events.append((ctx.fact("purchase_date") or "", f"Purchase / payment of {_money(ctx.fact('amount_paid'))} "
                       f"for {_v(ctx.fact('product_or_service'))}", ctx.fact_id("purchase_date")))
    if ctx.fact("problem_date"):
        events.append((ctx.fact("problem_date") or "", "Problem with the goods/service arose", ctx.fact_id("problem_date")))
    for item in ctx.evidence:
        if item.get("evidence_date"):
            events.append((item["evidence_date"], f"{item['label']}: {item['title']}", None))
    events.sort(key=lambda e: e[0])
    rows = [["Date", "Event"]] + [[_date(d), text] for d, text, _ in events]
    if len(rows) == 1:
        rows.append([PLACEHOLDER, PLACEHOLDER])
    return {"title": DOC_TYPES["list_of_dates"], "doc_type": "list_of_dates", "blocks": [
        _block("notice", DRAFT_NOTICE, block_id="notice", editable=False),
        _block("heading", "LIST OF DATES AND EVENTS", block_id="head", editable=False),
        _block("table", "", block_id="dates", rows=rows, facts=[e[2] for e in events], editable=False),
    ]}


def evidence_index(ctx: DraftContext) -> dict[str, Any]:
    rows = [["Annexure", "Document", "Date"]]
    for item in ctx.evidence:
        rows.append([item["label"], item["title"], _date(item.get("evidence_date")) if item.get("evidence_date") else "—"])
    blocks = [
        _block("notice", DRAFT_NOTICE, block_id="notice", editable=False),
        _block("heading", "INDEX OF DOCUMENTS", block_id="head", editable=False),
    ]
    if len(rows) == 1:
        blocks.append(_block("para", "No documents have been added to the evidence list yet. Upload your bill, "
                             "order confirmation, photos and messages, then regenerate this index.",
                             block_id="empty", editable=False))
    else:
        blocks.append(_block("table", "", block_id="index", rows=rows, editable=False))
    return {"title": DOC_TYPES["evidence_index"], "doc_type": "evidence_index", "blocks": blocks}


def filing_checklist(ctx: DraftContext) -> dict[str, Any]:
    forum = ctx.outcome("pecuniary_forum")
    fee = ctx.outcome("filing_fee")
    lim = ctx.outcome("limitation")
    items = [
        f"Forum: {forum['explanation_en'] if forum else PLACEHOLDER}",
        f"Fee: {fee['explanation_en'] if fee else PLACEHOLDER}",
        f"Time limit: {lim['explanation_en'] if lim else PLACEHOLDER}",
        "Complaint reviewed and approved by you in NyayaSetu.",
        "Index of documents, list of dates and memo of parties approved.",
        "Each document saved as a PDF. The e-Jagriti upload screen accepts PDF files only and states a "
        "25 MB limit per file (as shown on the portal on 30 Oct 2026; check the portal for changes).",
        "Your mobile number available for OTP login on e-Jagriti. You complete login and CAPTCHA yourself.",
        "Signature on the complaint; affidavit or notarisation if the portal asks for it.",
        "After submission, note the reference/diary number and download the acknowledgement.",
    ]
    return {"title": DOC_TYPES["filing_checklist"], "doc_type": "filing_checklist", "blocks": [
        _block("heading", "FILING CHECKLIST — e-JAGRITI", block_id="head", editable=False),
        _block("list", "", block_id="items", items=items, refs=_ref(forum) + _ref(fee) + _ref(lim), editable=False),
    ]}


BUILDERS = {
    "consumer_complaint": consumer_complaint,
    "memo_of_parties": memo_of_parties,
    "list_of_dates": list_of_dates,
    "evidence_index": evidence_index,
    "filing_checklist": filing_checklist,
}
