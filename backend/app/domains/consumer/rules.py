"""Deterministic consumer-law rules.

Each rule encodes a specific provision of the ingested official text and returns
the provision it relied on. At runtime `ground()` confirms the provision is present
in the knowledge base; if it is not, the conclusion is withheld rather than asserted
from model memory.

Provisions encoded (all read from the official documents in data/legal_sources):
  * Pecuniary jurisdiction - Consumer Protection (Jurisdiction ...) Rules, 2021, rules 3-5
  * Filing fee            - CDRC (Amendment) Rules, 2023, rule 2 (substituted rule 7(2) table)
  * Limitation            - Consumer Protection Act, 2019, section 69
  * Territorial options   - Consumer Protection Act, 2019, section 34(2)
  * Who is a consumer     - Consumer Protection Act, 2019, section 2(7)
  * Free / personal service exclusion - section 2(42)
  * Orders the Commission may make    - section 39(1)
  * Appeal period         - section 41
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.legal.retrieval import get_chunks_by_ref

LAKH = Decimal(100_000)
CRORE = Decimal(10_000_000)


@dataclass
class Basis:
    document_key: str
    section_ref: str
    summary: str
    chunk_id: str | None = None
    source_url: str | None = None
    document_title: str | None = None
    verification_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class RuleOutcome:
    key: str
    value: Any
    explanation_en: str
    explanation_hi: str
    basis: list[Basis]
    grounded: bool = False
    caveats: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "explanation_en": self.explanation_en,
            "explanation_hi": self.explanation_hi,
            "basis": [b.as_dict() for b in self.basis],
            "grounded": self.grounded,
            "caveats": self.caveats,
        }


def _inr(amount: Decimal) -> str:
    """Format rupees in the Indian numbering system."""
    whole = int(amount)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"₹{s}"


def pecuniary_forum(amount: Decimal) -> RuleOutcome:
    if amount <= 50 * LAKH:
        forum, rule = "district", "Rule 3"
        en = (f"For an amount paid of {_inr(amount)}, the District Commission has jurisdiction, "
              "because it hears complaints where the value paid does not exceed ₹50 lakh.")
        hi = (f"{_inr(amount)} के भुगतान के लिए ज़िला उपभोक्ता आयोग सुनवाई करेगा, क्योंकि वह ₹50 लाख तक "
              "के भुगतान वाले मामले सुनता है।")
    elif amount <= 2 * CRORE:
        forum, rule = "state", "Rule 4"
        en = (f"For an amount paid of {_inr(amount)}, the State Commission has jurisdiction "
              "(more than ₹50 lakh and up to ₹2 crore).")
        hi = f"{_inr(amount)} के भुगतान के लिए राज्य उपभोक्ता आयोग सुनवाई करेगा (₹50 लाख से अधिक और ₹2 करोड़ तक)।"
    else:
        forum, rule = "national", "Rule 5"
        en = f"For an amount paid of {_inr(amount)}, the National Commission has jurisdiction (more than ₹2 crore)."
        hi = f"{_inr(amount)} के भुगतान के लिए राष्ट्रीय उपभोक्ता आयोग सुनवाई करेगा (₹2 करोड़ से अधिक)।"
    return RuleOutcome(
        "pecuniary_forum", forum, en, hi,
        [Basis("cp_jurisdiction_rules_2021", rule,
               "Pecuniary limits of the District, State and National Commissions")],
        caveats=[
            "The limit is based on the value of goods or services paid as consideration, "
            "not on the compensation claimed.",
        ],
    )


# Substituted rule 7(2) table, CDRC (Amendment) Rules, 2023: (upper limit in rupees, fee).
_FEE_TABLE: list[tuple[Decimal | None, int]] = [
    (5 * LAKH, 0),
    (10 * LAKH, 200),
    (20 * LAKH, 400),
    (50 * LAKH, 1000),
    (1 * CRORE, 2000),
    (2 * CRORE, 2500),
    (4 * CRORE, 3000),
    (6 * CRORE, 4000),
    (8 * CRORE, 5000),
    (10 * CRORE, 6000),
    (None, 7500),
]


def filing_fee(amount: Decimal) -> RuleOutcome:
    fee = next(f for limit, f in _FEE_TABLE if limit is None or amount <= limit)
    if fee == 0:
        en = f"No filing fee is payable when the value paid is up to ₹5 lakh (your amount: {_inr(amount)})."
        hi = f"₹5 लाख तक के भुगतान पर कोई फीस नहीं लगती (आपकी राशि: {_inr(amount)})।"
    else:
        en = f"The filing fee for a value paid of {_inr(amount)} is ₹{fee}."
        hi = f"{_inr(amount)} के भुगतान के लिए शिकायत दर्ज करने की फीस ₹{fee} है।"
    return RuleOutcome(
        "filing_fee", fee, en, hi,
        [Basis("cp_cdrc_amendment_rules_2023", "Rule 2",
               "Fee table substituted in rule 7(2) of the CDRC Rules, 2020")],
        caveats=["Fee amounts can be revised by later notifications; confirm on the filing portal."],
    )


def add_years(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # 29 February
        return start.replace(year=start.year + years, day=28)


def limitation(cause_of_action: date, today: date) -> RuleOutcome:
    deadline = add_years(cause_of_action, 2)
    days_left = (deadline - today).days
    if days_left < 0:
        status = "expired"
        en = (f"The two-year period counted from {cause_of_action:%d %B %Y} appears to have ended on "
              f"{deadline:%d %B %Y}. A late complaint can be admitted only if the Commission accepts that "
              "there was sufficient cause for the delay, and records its reasons. Please speak to a lawyer "
              "or free legal aid.")
        hi = (f"{cause_of_action:%d-%m-%Y} से गिनी गई दो साल की अवधि {deadline:%d-%m-%Y} को समाप्त हो गई लगती है। "
              "देर से दायर शिकायत तभी स्वीकार होती है जब आयोग देरी का पर्याप्त कारण माने। कृपया वकील या मुफ़्त "
              "कानूनी सहायता से बात करें।")
    elif days_left <= 90:
        status = "urgent"
        en = (f"File soon: the two-year period counted from {cause_of_action:%d %B %Y} ends on "
              f"{deadline:%d %B %Y} ({days_left} days left).")
        hi = f"जल्दी करें: {cause_of_action:%d-%m-%Y} से गिनी गई दो साल की अवधि {deadline:%d-%m-%Y} को समाप्त होगी ({days_left} दिन बाकी)।"
    else:
        status = "within_time"
        en = (f"You appear to be within time: the two-year period counted from {cause_of_action:%d %B %Y} "
              f"ends on {deadline:%d %B %Y}.")
        hi = f"आप समय सीमा के अंदर लगते हैं: {cause_of_action:%d-%m-%Y} से गिनी गई दो साल की अवधि {deadline:%d-%m-%Y} को समाप्त होगी।"
    return RuleOutcome(
        "limitation",
        {"deadline": deadline.isoformat(), "days_left": days_left, "status": status},
        en, hi,
        [Basis("cpa_2019", "Section 69", "Complaint to be filed within two years of the cause of action")],
        caveats=[
            "The date the 'cause of action' arose is a legal question; this estimate uses the date "
            "you gave for when the problem happened.",
        ],
    )


def territorial_options(complainant_district: str | None) -> RuleOutcome:
    where = complainant_district or "the district where you live or work"
    en = (f"You can file in the District Commission for {where} (where the complainant resides or works "
          "for gain). You may also file where the seller resides, carries on business or has a branch "
          "office, or where the cause of action arose.")
    hi = (f"आप {complainant_district or 'अपने ज़िले'} के ज़िला उपभोक्ता आयोग में शिकायत कर सकते हैं (जहाँ शिकायतकर्ता "
          "रहता या काम करता है)। आप वहाँ भी शिकायत कर सकते हैं जहाँ विक्रेता रहता है, व्यापार करता है या उसकी "
          "शाखा है, या जहाँ विवाद का कारण उत्पन्न हुआ।")
    return RuleOutcome(
        "territorial_options", {"complainant_district": complainant_district}, en, hi,
        [Basis("cpa_2019", "Section 34", "Where a complaint may be instituted (section 34(2))")],
    )


def consumer_status(commercial_purpose: str | None, free_service: bool, personal_service: bool) -> RuleOutcome:
    issues: list[str] = []
    basis = [Basis("cpa_2019", "Section 2(7)", "Definition of 'consumer'")]
    if commercial_purpose == "commercial":
        issues.append("commercial_purpose")
    if free_service:
        issues.append("free_service")
        basis.append(Basis("cpa_2019", "Section 2(42)", "Definition of 'service'"))
    if personal_service:
        issues.append("personal_service")
        basis.append(Basis("cpa_2019", "Section 2(42)", "Definition of 'service'"))
    if not issues:
        value = "likely_consumer" if commercial_purpose == "personal" else "unknown"
        en = ("You appear to be a 'consumer' under the Act: you paid for goods or a service for your own use."
              if value == "likely_consumer" else
              "Whether you count as a 'consumer' depends on whether you paid and bought for personal use.")
        hi = ("आप कानून के अनुसार 'उपभोक्ता' लगते हैं: आपने अपने उपयोग के लिए भुगतान करके सामान या सेवा ली।"
              if value == "likely_consumer" else
              "आप 'उपभोक्ता' माने जाएँगे या नहीं, यह इस पर निर्भर है कि आपने भुगतान किया और निजी उपयोग के लिए खरीदा।")
    else:
        value = "may_not_be_consumer"
        reasons_en = {
            "commercial_purpose": "goods or services obtained for resale or a commercial purpose are excluded "
                                  "(except use to earn a livelihood through self-employment)",
            "free_service": "services rendered free of charge are excluded",
            "personal_service": "services under a contract of personal service (e.g. employment) are excluded",
        }
        en = ("A Consumer Commission may not be the right forum: " + "; ".join(reasons_en[i] for i in issues)
              + ". A lawyer or free legal aid can advise on the right route.")
        hi = ("उपभोक्ता आयोग शायद सही मंच न हो — व्यापारिक उद्देश्य, मुफ़्त सेवा या व्यक्तिगत सेवा अनुबंध (जैसे नौकरी) "
              "इस कानून से बाहर हैं। सही रास्ते के लिए वकील या मुफ़्त कानूनी सहायता से सलाह लें।")
    return RuleOutcome("consumer_status", {"status": value, "issues": issues}, en, hi, basis)


REMEDY_TO_CLAUSE = {
    "repair": ("Section 39", "(a)/(f) remove the defect or deficiency"),
    "replacement": ("Section 39", "(b) replace the goods with new goods free from defect"),
    "refund": ("Section 39", "(c) return the price or charges paid, with interest as decided"),
    "compensation": ("Section 39", "(d) compensation for loss or injury due to negligence"),
}


def available_reliefs(remedies: list[str]) -> RuleOutcome:
    chosen = [r for r in remedies if r in REMEDY_TO_CLAUSE] or ["refund", "compensation"]
    labels = [REMEDY_TO_CLAUSE[r][1] for r in chosen]
    en = "The Commission can order, among other things: " + "; ".join(labels) + ", and costs."
    hi = "आयोग अन्य बातों के साथ यह आदेश दे सकता है: दोष दूर करना, सामान बदलना, पैसे ब्याज सहित लौटाना, मुआवज़ा, और खर्च।"
    return RuleOutcome(
        "available_reliefs", chosen, en, hi,
        [Basis("cpa_2019", "Section 39", "Orders the District Commission may make")],
        caveats=["Whether any relief is granted depends on the evidence and the Commission's findings."],
    )


def appeal_period() -> RuleOutcome:
    return RuleOutcome(
        "appeal_period", 45,
        "An appeal against a District Commission order lies to the State Commission within 45 days of the order.",
        "ज़िला आयोग के आदेश के ख़िलाफ़ अपील आदेश की तारीख से 45 दिन के अंदर राज्य आयोग में की जा सकती है।",
        [Basis("cpa_2019", "Section 41", "Appeal against order of District Commission")],
    )


async def ground(db: AsyncSession, outcome: RuleOutcome) -> RuleOutcome:
    """Attach chunk ids/URLs for each basis and mark the outcome grounded only if every
    cited provision is present in the knowledge base."""
    all_found = True
    for basis in outcome.basis:
        chunks = await get_chunks_by_ref(db, basis.document_key, [basis.section_ref])
        if not chunks:
            all_found = False
            continue
        chunk = chunks[0]
        basis.chunk_id = str(chunk.id)
        basis.source_url = chunk.document.source_url
        basis.document_title = chunk.document.title
        basis.verification_status = chunk.document.verification_status
    outcome.grounded = all_found
    if not all_found:
        outcome.caveats.append(
            "The official source for this conclusion is not loaded in the knowledge base, so it "
            "should not be relied on until the source is ingested."
        )
    return outcome
