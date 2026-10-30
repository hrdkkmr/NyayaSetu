"""Intake agent: turns a user message into candidate facts for the case.

Two implementations share one output contract:
  * LLM extraction (Claude, structured output) when configured and the user has
    consented to external AI processing.
  * Rule-based extraction otherwise (and as fallback on any LLM failure).

Provenance policy:
  * A direct answer to the question we just asked → USER_STATED.
  * The user's own description of the problem → USER_STATED (it is their words).
  * Amounts written with a currency marker in the narrative → USER_STATED.
  * Anything the system derives or guesses from narrative → AI_INFERENCE, which the
    user must confirm before it is used in a document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.agents import extract as ex
from app.agents.llm import LLMProvider, LLMRefusalError, LLMUnavailableError
from app.agents.state import SlotValue
from app.domains.consumer.slots import SLOT_BY_KEY, SLOTS
from app.legal.text import contains_devanagari
from app.models.enums import FactProvenance

SlotKey = Literal[
    "grievance", "product_or_service", "seller_name", "purchase_mode", "purchase_date",
    "amount_paid", "problem_date", "contacted_seller", "desired_remedy", "evidence",
    "complainant_location", "commercial_purpose", "seller_address", "complainant_name",
    "complainant_address",
]

DONT_KNOW = re.compile(
    r"^\s*(i\s*don'?t\s*know|not sure|no idea|skip|pata nahi|pata nahin|पता नहीं|मालूम नहीं|याद नहीं|nahi pata|"
    r"आगे बढ़ें|aage badhen)(?![\wऀ-ॿ])",
    re.IGNORECASE,
)
FRUSTRATION = re.compile(
    r"frustrat|fed up|angry|annoyed|useless|cheated|harass|pareshan|परेशान|गुस्सा|तंग आ|धोखा|"
    r"thak gaya|थक गया|थक गई|बहुत दिक्कत", re.IGNORECASE,
)
CONFUSION = re.compile(r"confus|don'?t understand|what do you mean|samajh nahi|समझ नहीं|क्या मतलब", re.IGNORECASE)
QUESTION = re.compile(
    r"\?|^(how|what|which|when|where|can i|do i|should i|is it|will i|kya|kaise|kab|kahan|kitna|"
    r"क्या|कैसे|कब|कहाँ|कहां|कितना|कितने)(?![\wऀ-ॿ])", re.IGNORECASE,
)


@dataclass
class FactCandidate:
    key: str
    value: str
    provenance: FactProvenance
    excerpt: str | None
    value_type: str = "text"
    confidence: float = 0.7


@dataclass
class IntakeResult:
    facts: list[FactCandidate] = field(default_factory=list)
    language: str = "en"
    tone: str = "calm"
    is_question: bool = False
    skipped_slot: str | None = None
    confirmation: bool | None = None
    method: str = "rules"


def detect_language(text: str, default: str) -> str:
    if contains_devanagari(text):
        return "hi"
    hinglish = re.findall(r"\b(mera|meri|mujhe|maine|kya|hai|nahi|kar|raha|rahi|tha|thi|liya|diya|aur|ke|ki|ko|se)\b", text.lower())
    if len(hinglish) >= 3:
        return "hi"
    return default if default in ("en", "hi") else "en"


def _tone(text: str) -> str:
    if FRUSTRATION.search(text):
        return "frustrated"
    if CONFUSION.search(text):
        return "confused"
    return "calm"


def _iso(d: date) -> str:
    return d.isoformat()


def _slot_answer(slot_key: str, message: str, today: date) -> FactCandidate | None:
    slot = SLOT_BY_KEY[slot_key]
    text = message.strip()
    if slot.value_type == "date":
        dates = ex.find_dates(text, today)
        if dates:
            d, excerpt, approx = dates[0]
            return FactCandidate(slot_key, _iso(d), FactProvenance.USER_STATED,
                                 excerpt + (" (approximate)" if approx else ""), "date", 0.9 if not approx else 0.6)
        return None
    if slot.value_type == "money":
        amounts = ex.find_amounts(text)
        if amounts:
            return FactCandidate(slot_key, str(amounts[0][0]), FactProvenance.USER_STATED, amounts[0][1], "money", 0.9)
        bare = re.search(r"\b\d[\d,]{1,12}(?:\.\d{1,2})?\b", ex.normalise_digits(text))
        if bare:
            return FactCandidate(slot_key, bare.group(0).replace(",", ""), FactProvenance.USER_STATED, text[:120], "money", 0.8)
        return None
    if slot_key == "purchase_mode":
        hits = ex.keyword_hits(text, ex.PURCHASE_MODE_KEYWORDS)
        if len(hits) == 1:
            return FactCandidate(slot_key, hits[0], FactProvenance.USER_STATED, text[:200], "choice", 0.9)
        return None
    if slot_key == "desired_remedy":
        hits = ex.keyword_hits(text, ex.REMEDY_KEYWORDS)
        if hits:
            return FactCandidate(slot_key, ", ".join(hits), FactProvenance.USER_STATED, text[:200], "choice", 0.9)
        return None
    if slot_key == "commercial_purpose":
        value = ex.commercial_purpose(text)
        if value:
            return FactCandidate(slot_key, value, FactProvenance.USER_STATED, text[:200], "choice", 0.85)
        return None
    if slot_key == "evidence":
        hits = ex.keyword_hits(text, ex.EVIDENCE_KEYWORDS)
        value = ", ".join(hits) if hits else text[:300]
        return FactCandidate(slot_key, value, FactProvenance.USER_STATED, text[:300], "text", 0.8)
    if len(text) < 2:
        return None
    return FactCandidate(slot_key, text[:500], FactProvenance.USER_STATED, text[:300], "text", 0.85)


_PRODUCT = re.compile(
    r"\b(?:bought|purchased|ordered|booked|got|subscribed to|took)\s+(?:a|an|the|my|one|new)?\s*"
    r"(?P<item>[a-z0-9][a-z0-9 \-]{1,40}?)(?=\s+(?:from|on|for|online|at|which|that|but|and|in|worth|costing|of rs|of ₹)\b|[,.!]|$)",
    re.IGNORECASE,
)
_PRODUCT_HI = re.compile(r"(?P<item>[\wऀ-ॿ]{2,20})\s+(?:खरीदा|ख़रीदा|मंगवाया|ऑर्डर किया|kharida|mangwaya)")
_SELLER = re.compile(
    r"\b(?:from|seller|vendor|company|shop|store|dealer|by)\s+(?:named\s+|called\s+)?"
    r"(?P<name>[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})",
)
_KNOWN_PLATFORMS = re.compile(
    r"\b(amazon|flipkart|myntra|meesho|ajio|nykaa|snapdeal|tata cliq|jiomart|bigbasket|swiggy|zomato|"
    r"croma|reliance digital|vijay sales|paytm mall|makemytrip|irctc|ola|uber)\b", re.IGNORECASE,
)


def _narrative(message: str, slots: dict[str, SlotValue], today: date) -> list[FactCandidate]:
    out: list[FactCandidate] = []
    text = message.strip()
    lowered = text.lower()

    if "grievance" not in slots and len(text) >= 25:
        out.append(FactCandidate("grievance", text[:2000], FactProvenance.USER_STATED, None, "text", 0.95))

    if "product_or_service" not in slots:
        m = _PRODUCT.search(text) or _PRODUCT_HI.search(text)
        if m:
            item = m.group("item").strip(" -")
            if item and item.lower() not in {"it", "this", "that", "something", "product"}:
                out.append(FactCandidate("product_or_service", item, FactProvenance.AI_INFERENCE,
                                         ex._excerpt(text, m.start(), m.end()), "text", 0.6))

    if "seller_name" not in slots:
        m = _KNOWN_PLATFORMS.search(text)
        if m:
            out.append(FactCandidate("seller_name", m.group(1).title(), FactProvenance.AI_INFERENCE,
                                     ex._excerpt(text, m.start(), m.end()), "text", 0.6))
        else:
            m2 = _SELLER.search(text)
            if m2:
                out.append(FactCandidate("seller_name", m2.group("name"), FactProvenance.AI_INFERENCE,
                                         ex._excerpt(text, m2.start(), m2.end()), "text", 0.5))

    if "purchase_mode" not in slots:
        hits = ex.keyword_hits(text, ex.PURCHASE_MODE_KEYWORDS)
        if len(hits) == 1:
            out.append(FactCandidate("purchase_mode", hits[0], FactProvenance.AI_INFERENCE, None, "choice", 0.6))

    if "amount_paid" not in slots:
        amounts = ex.find_amounts(text)
        if len(amounts) == 1:
            out.append(FactCandidate("amount_paid", str(amounts[0][0]), FactProvenance.USER_STATED,
                                     amounts[0][1], "money", 0.8))
        elif len(amounts) > 1:
            out.append(FactCandidate("amount_paid", str(amounts[0][0]), FactProvenance.AI_INFERENCE,
                                     amounts[0][1], "money", 0.4))

    dates = ex.find_dates(text, today)
    for d, excerpt, _approx in dates:
        ctx = excerpt.lower()
        if "purchase_date" not in slots and re.search(r"bought|purchas|order|paid|booked|खरीद|ऑर्डर|kharid", ctx):
            out.append(FactCandidate("purchase_date", _iso(d), FactProvenance.AI_INFERENCE, excerpt, "date", 0.6))
        elif "problem_date" not in slots and re.search(r"deliver|receiv|broke|stop|damag|defect|refus|मिला|खराब|टूट|बंद", ctx):
            out.append(FactCandidate("problem_date", _iso(d), FactProvenance.AI_INFERENCE, excerpt, "date", 0.55))

    if "desired_remedy" not in slots:
        hits = ex.keyword_hits(lowered, ex.REMEDY_KEYWORDS)
        if hits and re.search(r"want|need|demand|asking|expect|chahta|chahti|चाहता|चाहती|चाहिए", lowered):
            out.append(FactCandidate("desired_remedy", ", ".join(hits), FactProvenance.USER_STATED, None, "choice", 0.7))

    if "evidence" not in slots:
        hits = ex.keyword_hits(lowered, ex.EVIDENCE_KEYWORDS)
        if hits and re.search(r"\bhave\b|\bgot\b|है|hai|attached|saved|kept", lowered):
            out.append(FactCandidate("evidence", ", ".join(hits), FactProvenance.AI_INFERENCE, None, "text", 0.5))

    if "commercial_purpose" not in slots:
        cp = ex.commercial_purpose(text)
        if cp:
            out.append(FactCandidate("commercial_purpose", cp, FactProvenance.AI_INFERENCE, None, "choice", 0.5))
    return out


def extract_offline(
    message: str, asked_slot: str | None, slots: dict[str, SlotValue], today: date, default_language: str
) -> IntakeResult:
    result = IntakeResult(language=detect_language(message, default_language), tone=_tone(message))
    result.is_question = bool(QUESTION.search(message.strip()))

    if asked_slot:
        current = slots.get(asked_slot)
        if current and current.get("provenance") == FactProvenance.AI_INFERENCE:
            # We asked the user to confirm an inferred value.
            yn = ex.yes_no(message)
            if yn is True:
                result.confirmation = True
                result.facts.append(FactCandidate(asked_slot, current["value"], FactProvenance.USER_CONFIRMED,
                                                  current.get("excerpt"), SLOT_BY_KEY[asked_slot].value_type, 1.0))
            else:
                answer = _slot_answer(asked_slot, message, today)
                if yn is False and (answer is None or len(message.split()) <= 2):
                    result.confirmation = False
                elif answer:
                    result.facts.append(answer)
        elif DONT_KNOW.search(message):
            result.skipped_slot = asked_slot
        else:
            answer = _slot_answer(asked_slot, message, today)
            if answer:
                result.facts.append(answer)
            # If the user answered with a question instead, don't store the question as a fact.
            if result.is_question and answer and answer.value_type == "text" and asked_slot != "grievance":
                result.facts.remove(answer)

    filled = {**slots, **{f.key: SlotValue(value=f.value) for f in result.facts}}
    result.facts.extend(_narrative(message, filled, today))
    return result


# ---- LLM path -------------------------------------------------------------------------------


class LLMFact(BaseModel):
    slot: SlotKey
    value: str = Field(description="Normalised value. Dates as YYYY-MM-DD, money as digits only.")
    excerpt: str = Field(description="Exact words from the user's message that support this value.")
    is_inference: bool = Field(description="True if the user did not explicitly say this.")


class LLMIntake(BaseModel):
    facts: list[LLMFact]
    language: Literal["en", "hi"]
    tone: Literal["calm", "confused", "frustrated", "distressed"]
    is_question: bool
    answered_asked_slot: bool
    confirms_inference: bool | None = None
    wants_to_skip: bool = False


INTAKE_SYSTEM = """You extract facts for a consumer-dispute intake in India. You do not give legal advice.

Rules:
- Extract only what the user's latest message supports. Never invent names, dates, amounts or places.
- `excerpt` must be copied exactly from the user's message.
- Set is_inference=true for anything the user did not state explicitly (for example, guessing the purchase was
  online because a marketplace name appears).
- Dates: YYYY-MM-DD. If only a month/year is given, use the 1st of that month and set is_inference=true.
- Money: digits only, in rupees (convert lakh/hazaar).
- slot meanings: grievance=the user's description of the problem; product_or_service; seller_name; purchase_mode
  (online|offline); purchase_date; amount_paid; problem_date (when the problem happened); contacted_seller;
  desired_remedy (replacement|refund|repair|compensation, comma-separated); evidence; complainant_location
  (district, state); commercial_purpose (personal|commercial|livelihood); seller_address; complainant_name;
  complainant_address.
- language: "hi" if the user writes in Hindi or Hinglish, else "en".
"""


async def extract_with_llm(
    llm: LLMProvider, message: str, asked_slot: str | None, slots: dict[str, SlotValue], today: date,
    default_language: str,
) -> IntakeResult:
    known = {k: v.get("value") for k, v in slots.items()}
    asked = SLOT_BY_KEY[asked_slot].question_en if asked_slot else "none (first message)"
    prompt = (
        f"Today's date: {today.isoformat()}\n"
        f"Facts already known (do not repeat unless corrected): {known}\n"
        f"Question we just asked: {asked}\n"
        f"Asked slot key: {asked_slot}\n\n"
        f"User's latest message:\n<<<\n{message}\n>>>"
    )
    result = await llm.structured(
        system=INTAKE_SYSTEM, messages=[{"role": "user", "content": prompt}], schema=LLMIntake, max_tokens=2000
    )
    parsed = result.value
    out = IntakeResult(language=parsed.language, tone=parsed.tone, is_question=parsed.is_question, method="llm")
    if asked_slot and parsed.wants_to_skip:
        out.skipped_slot = asked_slot
    current = slots.get(asked_slot or "")
    if asked_slot and current and current.get("provenance") == FactProvenance.AI_INFERENCE:
        if parsed.confirms_inference is True:
            out.confirmation = True
            out.facts.append(FactCandidate(asked_slot, current["value"], FactProvenance.USER_CONFIRMED,
                                           current.get("excerpt"), SLOT_BY_KEY[asked_slot].value_type, 1.0))
        elif parsed.confirms_inference is False:
            out.confirmation = False
    norm_msg = " ".join(message.lower().split())
    for f in parsed.facts:
        if f.slot not in SLOT_BY_KEY:
            continue
        excerpt_ok = " ".join(f.excerpt.lower().split()) in norm_msg if f.excerpt else False
        provenance = FactProvenance.AI_INFERENCE if (f.is_inference or not excerpt_ok) else FactProvenance.USER_STATED
        if f.slot == asked_slot and parsed.answered_asked_slot and excerpt_ok and not f.is_inference:
            provenance = FactProvenance.USER_STATED
        out.facts.append(FactCandidate(f.slot, f.value, provenance, f.excerpt if excerpt_ok else None,
                                       SLOT_BY_KEY[f.slot].value_type, 0.8))
    return out


async def run_intake(
    llm: LLMProvider, allow_llm: bool, message: str, asked_slot: str | None, slots: dict[str, SlotValue],
    today: date, default_language: str,
) -> tuple[IntakeResult, str | None]:
    """Returns the intake result and, if the LLM path failed, the reason it fell back."""
    if allow_llm and llm.available:
        try:
            return await extract_with_llm(llm, message, asked_slot, slots, today, default_language), None
        except (LLMUnavailableError, LLMRefusalError) as exc:
            return extract_offline(message, asked_slot, slots, today, default_language), str(exc)
    return extract_offline(message, asked_slot, slots, today, default_language), None


def next_slot(slots: dict[str, SlotValue], skipped: list[str]) -> tuple[str | None, bool]:
    """Pick the next slot to ask about. Returns (slot_key, is_confirmation)."""
    for slot in SLOTS:
        if slot.key in skipped:
            continue
        current = slots.get(slot.key)
        if current is None:
            return slot.key, False
        if current.get("provenance") == FactProvenance.AI_INFERENCE:
            return slot.key, True
    return None, False


def missing_required(slots: dict[str, SlotValue]) -> list[str]:
    from app.domains.consumer.slots import REQUIRED_FOR_DRAFT

    return [
        key for key in REQUIRED_FOR_DRAFT
        if key not in slots or slots[key].get("provenance") == FactProvenance.AI_INFERENCE
    ]
