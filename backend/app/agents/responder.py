"""Composes the assistant's replies from structured agent results.

Replies are assembled from templates and grounded rule outcomes first. If an LLM is
available and allowed, it may rephrase the reply to sound more natural, but the
rephrased text is rejected if it cites a provision that was not retrieved, makes a
guarantee, or drops the pending question.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMProvider, LLMRefusalError, LLMUnavailableError
from app.agents.resources import resource
from app.agents.safety import makes_guarantee, unsupported_citations
from app.domains.consumer.slots import SLOT_BY_KEY
from app.legal.retrieval import search

ACKS = {
    "en": ["Thank you.", "Understood.", "Got it.", "Thanks, that helps.", "I've noted that."],
    "hi": ["धन्यवाद।", "ठीक है, नोट कर लिया है।", "समझ में आया।", "शुक्रिया, इससे मदद मिलेगी।", "ठीक है।"],
}
EMPATHY = {
    "frustrated": {
        "en": "That sounds stressful. Let's take it one step at a time.",
        "hi": "यह परेशान करने वाला है। चलिए एक-एक कदम करके चलते हैं।",
    },
    "confused": {
        "en": "No problem — I'll keep it simple.",
        "hi": "कोई बात नहीं — मैं इसे आसान रखूँगी।",
    },
    "distressed": {
        "en": "I'm sorry you're going through this. Let's work through it together.",
        "hi": "मुझे खेद है कि आप इससे गुज़र रहे हैं। चलिए साथ मिलकर इसे सुलझाते हैं।",
    },
}
DISCLAIMER = {
    "en": "This is general legal information from official sources, not advice from a lawyer.",
    "hi": "यह आधिकारिक स्रोतों से सामान्य कानूनी जानकारी है, वकील की सलाह नहीं।",
}


def L(lang: str) -> str:
    return "hi" if lang == "hi" else "en"


# How each fact is referred to in a confirmation sentence.
NOUNS: dict[str, tuple[str, str]] = {
    "product_or_service": ("what you bought", "आपने क्या खरीदा"),
    "seller_name": ("the seller", "विक्रेता"),
    "purchase_mode": ("how you bought it", "खरीदने का तरीका"),
    "purchase_date": ("the purchase date", "खरीद की तारीख"),
    "amount_paid": ("the amount paid", "भुगतान की राशि"),
    "problem_date": ("when the problem started", "समस्या शुरू होने की तारीख"),
    "desired_remedy": ("what you want", "आप क्या चाहते हैं"),
    "evidence": ("the proof you have", "आपके सबूत"),
    "commercial_purpose": ("why you bought it", "खरीदने का उद्देश्य"),
    "complainant_location": ("your district and state", "आपका ज़िला और राज्य"),
    "contacted_seller": ("your contact with the seller", "विक्रेता से संपर्क"),
}

FORMAT_HINTS: dict[str, tuple[str, str]] = {
    "date": ("You can say something like “15 March 2026” or “two weeks ago”.",
             "आप ऐसे बता सकते हैं: “15 मार्च 2026” या “दो हफ्ते पहले”।"),
    "money": ("You can say an amount like “₹45,000” or “45 thousand rupees”.",
              "आप ऐसे बता सकते हैं: “₹45,000” या “45 हज़ार रुपये”।"),
    "choice": ("A short answer is fine.", "छोटा सा जवाब काफ़ी है।"),
}


def question_for(slot_key: str, language: str, confirm_value: str | None = None, first_time: bool = True,
                 retry: bool = False) -> str:
    slot = SLOT_BY_KEY[slot_key]
    lang = L(language)
    if confirm_value is not None:
        shown = _display_value(slot_key, confirm_value, lang)
        noun = NOUNS.get(slot_key, (slot.label_en.lower(), slot.label_hi))
        return (f"मैंने {noun[1]} “{shown}” समझा है। क्या यह सही है?" if lang == "hi"
                else f"I noted {noun[0]} as “{shown}”. Is that right?")
    question = slot.question_hi if lang == "hi" else slot.question_en
    if retry:
        hint = FORMAT_HINTS.get(slot.value_type)
        skip = ("अगर आपको नहीं पता, तो “आगे बढ़ें” कह दीजिए।" if lang == "hi"
                else "If you're not sure, just say “skip”.")
        lead = "माफ़ कीजिए, मैं यह ठीक से समझ नहीं पाई।" if lang == "hi" else "Sorry, I didn't quite catch that."
        return " ".join(p for p in [lead, question, hint[1 if lang == "hi" else 0] if hint else None, skip] if p)
    explain = slot.explain_hi if lang == "hi" else slot.explain_en
    if first_time and explain:
        return f"{explain} {question}"
    return question


def batch_confirmation(keys: list[str], slots: dict[str, Any], language: str) -> str:
    lang = L(language)
    parts = []
    for key in keys:
        noun = NOUNS.get(key, (SLOT_BY_KEY[key].label_en.lower(), SLOT_BY_KEY[key].label_hi))
        shown = _display_value(key, slots[key]["value"], lang)
        parts.append(f"{noun[1]}: {shown}" if lang == "hi" else f"{noun[0]}: {shown}")
    if lang == "hi":
        return "मैंने ये बातें नोट की हैं — " + "; ".join(parts) + "। क्या ये सब सही हैं?"
    return "Here's what I noted — " + "; ".join(parts) + ". Is all of that correct?"


def _display_value(slot_key: str, value: str, lang: str) -> str:
    slot = SLOT_BY_KEY[slot_key]
    if slot.value_type == "date":
        from datetime import date

        try:
            d = date.fromisoformat(value)
            return d.strftime("%d-%m-%Y") if lang == "hi" else d.strftime("%d %B %Y")
        except ValueError:
            return value
    if slot.value_type == "money":
        from decimal import Decimal

        from app.domains.consumer.rules import _inr

        try:
            return _inr(Decimal(value))
        except (ArithmeticError, ValueError):
            return value
    choices = {
        "online": ("ऑनलाइन", "online"), "offline": ("दुकान से", "in a shop"),
        "personal": ("निजी उपयोग", "personal use"), "commercial": ("व्यापारिक उपयोग", "business use"),
        "livelihood": ("स्व-रोज़गार", "self-employment livelihood"),
    }
    if value in choices:
        return choices[value][0 if lang == "hi" else 1]
    return value


def intake_reply(language: str, turn: int, tone: str, question: str | None, noted: list[str],
                 is_first: bool) -> str:
    lang = L(language)
    parts: list[str] = []
    if tone in EMPATHY:
        parts.append(EMPATHY[tone][lang])
    elif is_first:
        parts.append("मुझे बताने के लिए धन्यवाद। मैं इसे समझने और अगले कदम तैयार करने में आपकी मदद करूँगी।"
                     if lang == "hi" else
                     "Thank you for telling me. I'll help you understand this and prepare the next steps.")
    elif noted:
        parts.append(ACKS[lang][turn % len(ACKS[lang])])
    if question:
        parts.append(question)
    return " ".join(parts)


def analysis_reply(language: str, outcomes: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    lang = L(language)
    key = "explanation_hi" if lang == "hi" else "explanation_en"
    lines: list[str] = []
    cards: list[dict[str, Any]] = []
    for name in ("consumer_status", "pecuniary_forum", "territorial_options", "limitation", "filing_fee"):
        outcome = outcomes.get(name)
        if not outcome:
            continue
        if outcome.get("grounded"):
            lines.append(outcome[key])
        cards.append({"type": "rule_outcome", "key": name, "grounded": outcome.get("grounded"),
                      "text": outcome[key], "basis": outcome.get("basis", []), "caveats": outcome.get("caveats", [])})
    intro = ("मैंने आधिकारिक स्रोतों में आपकी स्थिति देखी है। मुख्य बातें:" if lang == "hi"
             else "I've checked your situation against the official sources. The key points:")
    outro = ("अगला कदम: मैं आपकी शिकायत का ड्राफ़्ट और सहायक दस्तावेज़ तैयार कर सकती हूँ। आप चाहें तो पहले अपने सबूत "
             "(बिल, ऑर्डर, फोटो) अपलोड कर दीजिए।" if lang == "hi" else
             "Next step: I can prepare a draft complaint and supporting documents. You may want to upload your "
             "proof (bill, order details, photos) first.")
    text = " ".join([intro, *lines, outro, DISCLAIMER[lang]])
    return text, cards


def referral_reply(language: str, category: str, reasons: list[str]) -> tuple[str, list[dict[str, Any]]]:
    lang = L(language)
    from app.agents.classification import REFERRAL_RESOURCES

    keys = REFERRAL_RESOURCES.get(category, ["legal_aid"])
    labels = {
        "criminal_matter": ("a police / criminal matter", "पुलिस / आपराधिक मामला"),
        "cyber_fraud": ("a cyber fraud matter", "साइबर धोखाधड़ी का मामला"),
        "family_matter": ("a family law matter", "पारिवारिक कानून का मामला"),
        "employment": ("an employment matter", "रोज़गार से जुड़ा मामला"),
        "property_tenancy": ("a property or tenancy matter", "संपत्ति या किरायेदारी का मामला"),
        "other": ("a matter outside consumer law", "उपभोक्ता कानून से बाहर का मामला"),
        "not_consumer": ("a matter where the Consumer Protection Act may not apply",
                         "ऐसा मामला जहाँ उपभोक्ता संरक्षण अधिनियम शायद लागू न हो"),
    }
    label = labels.get(category, labels["other"])[1 if lang == "hi" else 0]
    res = [resource(k, lang) for k in keys]
    if lang == "hi":
        text = (f"आपने जो बताया, वह {label} लगता है। NyayaSetu अभी पूरी प्रक्रिया केवल उपभोक्ता विवादों के लिए "
                "चलाता है, इसलिए मैं इसे गलत रास्ते पर नहीं ले जाना चाहती। ये आधिकारिक सहायता मदद कर सकती हैं: "
                + "; ".join(f"{r['name']} — {r['phone'] or r['url']}" for r in res)
                + "। मैंने आपके मामले को पेशेवर समीक्षा के लिए चिह्नित कर दिया है।")
    else:
        text = (f"From what you've described, this looks like {label}. NyayaSetu currently runs its full guided "
                "process only for consumer disputes, so I don't want to send you down the wrong route. These "
                "official services can help: "
                + "; ".join(f"{r['name']} — {r['phone'] or r['url']}" for r in res)
                + ". I've marked your case for professional review.")
    return text, [{"type": "resources", "items": res, "reasons": reasons}]


def safety_reply(language: str) -> tuple[str, list[dict[str, Any]]]:
    lang = L(language)
    res = [resource("emergency", lang), resource("mental_health", lang)]
    text = ("अगर आप या कोई और अभी खतरे में है, तो कृपया तुरंत 112 पर कॉल करें। बात करने के लिए टेली-मानस 14416 "
            "पर 24x7 मुफ़्त सहायता उपलब्ध है। जब आप तैयार हों, मैं कानूनी मामले में मदद के लिए यहीं हूँ।"
            if lang == "hi" else
            "If you or someone else is in danger right now, please call 112 immediately. Tele-MANAS (14416) offers "
            "free 24x7 support if you'd like to talk to someone. I'm here to help with the legal side whenever "
            "you're ready.")
    return text, [{"type": "resources", "items": res, "urgent": True}]


async def answer_question(db: AsyncSession, question: str, language: str, outcomes: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Answer a user's question from rule outcomes or retrieved official text."""
    lang = L(language)
    key = "explanation_hi" if lang == "hi" else "explanation_en"
    q = question.lower()
    topic_map = [
        (r"how long|time limit|deadline|last date|kitne din|समय सीमा|कब तक|limitation", "limitation"),
        (r"fee|fees|cost|charge|फीस|शुल्क|kitna paisa", "filing_fee"),
        (r"which (court|commission|forum)|where (can|do|should) i|कहाँ|कहां|kahan|jurisdiction", "pecuniary_forum"),
        (r"appeal|अपील", "appeal_period"),
        (r"what can i (get|ask|claim)|relief|compensation|refund|मुआवज|क्या मिल", "available_reliefs"),
    ]
    for pattern, outcome_key in topic_map:
        if re.search(pattern, q) and outcomes.get(outcome_key, {}).get("grounded"):
            o = outcomes[outcome_key]
            return o[key], [{"type": "rule_outcome", "key": outcome_key, "grounded": True, "text": o[key],
                             "basis": o.get("basis", []), "caveats": o.get("caveats", [])}]
    result = await search(db, question, legal_domain="consumer_protection", limit=3)
    if not result.results or result.confidence in ("none", "low"):
        text = ("मुझे इस सवाल के लिए आधिकारिक स्रोतों में भरोसेमंद जानकारी नहीं मिली, इसलिए मैं अंदाज़ा नहीं "
                "लगाऊँगी। मुफ़्त कानूनी सलाह के लिए नालसा हेल्पलाइन 15100 पर संपर्क कर सकते हैं।"
                if lang == "hi" else
                "I couldn't find reliable information in the official sources for that question, so I won't guess. "
                "For free legal advice you can call the NALSA helpline at 15100.")
        return text, [{"type": "resources", "items": [resource("legal_aid", lang)]}]
    top = result.results[0]
    snippet = " ".join(top.text.split())[:260]
    if lang == "hi":
        ref_hi = (top.section_ref or "").replace("Section", "धारा").replace("Rule", "नियम")
        text = (f"इससे जुड़ा आधिकारिक प्रावधान {ref_hi} ({top.document_title}) है। मूल अंग्रेज़ी पाठ कहता है: "
                f"“{snippet}…” {DISCLAIMER['hi']}")
    else:
        text = f"The relevant official provision is {top.section_ref} of {top.document_title}. It says: “{snippet}…” {DISCLAIMER['en']}"
    return text, [{"type": "sources", "confidence": result.confidence, "items": [r.as_dict() for r in result.results]}]


class Polished(BaseModel):
    reply: str


async def polish(llm: LLMProvider, allow_llm: bool, draft: str, language: str, must_include: str | None,
                 allowed_refs: set[str], voice: bool) -> tuple[str, bool]:
    """Optionally rephrase a templated reply. Returns (text, used_llm)."""
    if not (allow_llm and llm.available):
        return draft, False
    lang = "Hindi (Devanagari script, simple everyday words)" if L(language) == "hi" else "simple English"
    limit = "Keep it under 60 words; it will be spoken aloud." if voice else "Keep it under 120 words."
    system = (
        "You rephrase replies of NyayaSetu, an AI legal-information assistant for Indian citizens. Make the reply "
        f"warm, natural and clear in {lang}. {limit} Rules: keep every fact, number, date and legal reference "
        "exactly; do not add new legal provisions, numbers, promises or advice; do not claim to be a lawyer or "
        "human; ask at most one question and keep the question that is already there; no filler words."
    )
    try:
        result = await llm.structured(system=system, messages=[{"role": "user", "content": draft}],
                                      schema=Polished, max_tokens=800)
    except (LLMUnavailableError, LLMRefusalError):
        return draft, False
    text = result.value.reply.strip()
    if not text or makes_guarantee(text) or unsupported_citations(text, allowed_refs):
        return draft, False
    if must_include and "?" in must_include and "?" not in text and "?" not in text.replace("।", "?"):
        return draft, False
    return text, True
