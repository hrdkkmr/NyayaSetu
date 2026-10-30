"""Legal research agent: retrieves official provisions and grounds rule outcomes.

Tool access: read-only knowledge base retrieval and the deterministic consumer rules.
It cannot modify facts, documents, approvals or filings.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMProvider, LLMRefusalError, LLMUnavailableError
from app.agents.state import SlotValue
from app.domains.consumer import rules
from app.legal.retrieval import search
from app.models import LegalCitation
from app.services.facts import parse_date, parse_money

# Topics researched for every consumer case, with the query used for retrieval.
TOPICS: dict[str, str] = {
    "consumer_definition": "definition of consumer buys goods hires services consideration commercial purpose",
    "defect_deficiency": "definition defect deficiency fault imperfection shortcoming quality",
    "where_to_file": "complaint instituted district commission local limits jurisdiction complainant resides",
    "pecuniary_limits": "jurisdiction district commission value of goods services paid as consideration fifty lakh",
    "how_to_file": "complaint filed with District Commission by consumer filed electronically",
    "limitation": "limitation complaint filed within two years cause of action arisen",
    "filing_fee": "fee payable value of goods or services paid as consideration table",
    "reliefs": "District Commission order opposite party replace goods return price compensation",
    "appeal": "appeal against order District Commission State Commission forty-five days",
}

# Reviewed plain-language explanations for frequently cited provisions.
EXPLANATIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("cpa_2019", "Section 2(7)"): (
        "Defines who is a 'consumer': someone who buys goods or pays for a service for their own use, "
        "including online purchases. Buying for resale or a commercial purpose is excluded, except to earn "
        "a livelihood through self-employment.",
        "'उपभोक्ता' की परिभाषा: जो अपने उपयोग के लिए सामान खरीदता है या सेवा के लिए भुगतान करता है, ऑनलाइन खरीद "
        "सहित। दोबारा बेचने या व्यापारिक उद्देश्य से खरीद बाहर है, सिवाय स्व-रोज़गार से आजीविका के।",
    ),
    ("cpa_2019", "Section 2(10)"): (
        "Defines a 'defect' in goods: any fault, imperfection or shortcoming in quality, quantity, potency, "
        "purity or standard.",
        "सामान में 'दोष' की परिभाषा: गुणवत्ता, मात्रा, शुद्धता या मानक में कोई कमी या खराबी।",
    ),
    ("cpa_2019", "Section 2(11)"): (
        "Defines 'deficiency' in a service: any fault or shortcoming in the quality or manner of performance "
        "that was required or promised.",
        "सेवा में 'कमी' की परिभाषा: सेवा की गुणवत्ता या तरीके में कोई कमी जो ज़रूरी थी या वादा की गई थी।",
    ),
    ("cpa_2019", "Section 34"): (
        "Says where a complaint can be filed: where the seller lives or does business or has a branch, where "
        "the problem arose, or where you live or work. Note: the money limit printed in 34(1) was later changed.",
        "बताता है कि शिकायत कहाँ दर्ज हो सकती है: जहाँ विक्रेता रहता/व्यापार करता है, जहाँ समस्या हुई, या जहाँ आप "
        "रहते/काम करते हैं। ध्यान दें: 34(1) में लिखी राशि सीमा बाद में बदल दी गई।",
    ),
    ("cpa_2019", "Section 35"): (
        "Says who can file a complaint with the District Commission (including the consumer), that it may be "
        "filed electronically, and that a fee may be prescribed.",
        "बताता है कि ज़िला आयोग में शिकायत कौन कर सकता है (उपभोक्ता सहित), कि शिकायत ऑनलाइन दर्ज की जा सकती है, "
        "और फीस तय की जा सकती है।",
    ),
    ("cpa_2019", "Section 39"): (
        "Lists the orders the District Commission can make, such as removing the defect, replacing goods, "
        "returning the price with interest, and paying compensation and costs.",
        "ज़िला आयोग कौन से आदेश दे सकता है: दोष दूर करना, सामान बदलना, ब्याज सहित पैसे लौटाना, मुआवज़ा और खर्च।",
    ),
    ("cpa_2019", "Section 41"): (
        "An appeal against a District Commission order goes to the State Commission within 45 days.",
        "ज़िला आयोग के आदेश के ख़िलाफ़ अपील 45 दिन के अंदर राज्य आयोग में होती है।",
    ),
    ("cpa_2019", "Section 69"): (
        "A complaint must be filed within two years from when the cause of action arose. A late complaint "
        "can be accepted only if the Commission is satisfied there was sufficient cause for the delay.",
        "शिकायत विवाद का कारण बनने के दो साल के अंदर दर्ज करनी होती है। देर से शिकायत तभी स्वीकार होगी जब आयोग "
        "देरी का पर्याप्त कारण माने।",
    ),
    ("cp_jurisdiction_rules_2021", "Rule 3"): (
        "District Commissions hear complaints where the amount paid is up to ₹50 lakh.",
        "ज़िला आयोग ₹50 लाख तक के भुगतान वाली शिकायतें सुनता है।",
    ),
    ("cp_jurisdiction_rules_2021", "Rule 4"): (
        "State Commissions hear complaints where the amount paid is above ₹50 lakh and up to ₹2 crore.",
        "राज्य आयोग ₹50 लाख से ₹2 करोड़ तक के भुगतान वाली शिकायतें सुनता है।",
    ),
    ("cp_jurisdiction_rules_2021", "Rule 5"): (
        "The National Commission hears complaints where the amount paid is above ₹2 crore.",
        "राष्ट्रीय आयोग ₹2 करोड़ से अधिक के भुगतान वाली शिकायतें सुनता है।",
    ),
    ("cp_cdrc_amendment_rules_2023", "Rule 2"): (
        "Sets the filing fee table: no fee up to ₹5 lakh, then a fee that rises with the amount paid.",
        "फीस तालिका: ₹5 लाख तक कोई फीस नहीं, उसके बाद भुगतान की राशि के अनुसार फीस।",
    ),
}


class LLMExplanation(BaseModel):
    explanation: str
    supported_by_text: bool


async def _explain(llm: LLMProvider, allow_llm: bool, doc_key: str, ref: str | None, text: str,
                   language: str) -> tuple[str, str]:
    base_ref = (ref or "").split("(")[0] if ref and not ref.startswith("Section 2(") else (ref or "")
    template = EXPLANATIONS.get((doc_key, ref or "")) or EXPLANATIONS.get((doc_key, base_ref))
    if template:
        return (template[1] if language == "hi" else template[0]), "reviewed_template"
    if allow_llm and llm.available:
        try:
            lang = "simple Hindi" if language == "hi" else "simple English"
            result = await llm.structured(
                system=("Explain an Indian legal provision to a citizen in 2 short sentences in "
                        f"{lang}. Use only the provision text given. Do not add rules, numbers or "
                        "conditions that are not in the text. If the text is unclear, say so."),
                messages=[{"role": "user", "content": f"Provision ({ref}):\n{text[:3000]}"}],
                schema=LLMExplanation, max_tokens=600,
            )
            if result.value.supported_by_text:
                return result.value.explanation, "llm_from_source_text"
        except (LLMUnavailableError, LLMRefusalError):
            pass
    snippet = " ".join(text.split())[:220]
    if language == "hi":
        return f"इस प्रावधान का मूल अंग्रेज़ी पाठ: “{snippet}…”", "source_excerpt"
    return f"The provision says: “{snippet}…”", "source_excerpt"


async def compute_rule_outcomes(db: AsyncSession, slots: dict[str, SlotValue], today: date) -> dict[str, dict]:
    outcomes: dict[str, dict] = {}
    amount = parse_money(slots.get("amount_paid", {}).get("value"))
    if amount is not None and amount > Decimal(0):
        outcomes["pecuniary_forum"] = (await rules.ground(db, rules.pecuniary_forum(amount))).as_dict()
        outcomes["filing_fee"] = (await rules.ground(db, rules.filing_fee(amount))).as_dict()
    cause = parse_date(slots.get("problem_date", {}).get("value")) or parse_date(
        slots.get("purchase_date", {}).get("value"))
    if cause:
        outcome = rules.limitation(cause, today)
        if "problem_date" not in slots:
            outcome.caveats.append("Estimated from the purchase date because the problem date is not known yet.")
        outcomes["limitation"] = (await rules.ground(db, outcome)).as_dict()
    district = slots.get("complainant_location", {}).get("value")
    outcomes["territorial_options"] = (await rules.ground(db, rules.territorial_options(district))).as_dict()
    commercial = slots.get("commercial_purpose", {}).get("value")
    grievance = (slots.get("grievance", {}).get("value") or "").lower()
    free_service = any(w in grievance for w in ("free of cost", "free service", "मुफ़्त", "मुफ्त", "without paying"))
    personal_service = any(w in grievance for w in ("my employer", "my salary", "मेरी नौकरी"))
    outcomes["consumer_status"] = (
        await rules.ground(db, rules.consumer_status(commercial, free_service, personal_service))
    ).as_dict()
    remedies = [r.strip() for r in (slots.get("desired_remedy", {}).get("value") or "").split(",") if r.strip()]
    outcomes["available_reliefs"] = (await rules.ground(db, rules.available_reliefs(remedies))).as_dict()
    outcomes["appeal_period"] = (await rules.ground(db, rules.appeal_period())).as_dict()
    return outcomes


async def research_case(
    db: AsyncSession, llm: LLMProvider, allow_llm: bool, case_id: uuid.UUID, language: str,
    topics: list[str] | None = None,
) -> list[dict]:
    """Retrieve sources for each topic and store them as the case's citations."""
    topics = topics or list(TOPICS)
    await db.execute(delete(LegalCitation).where(LegalCitation.case_id == case_id))
    citations: list[dict] = []
    seen: set[str] = set()
    for topic in topics:
        result = await search(db, TOPICS[topic], legal_domain="consumer_protection", limit=2)
        for item in result.results[:2 if topic in ("pecuniary_limits", "reliefs") else 1]:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            explanation, method = await _explain(llm, allow_llm, item.document_key, item.section_ref,
                                                 item.text, language)
            row = LegalCitation(
                case_id=case_id, chunk_id=uuid.UUID(item.chunk_id), topic=topic, query=TOPICS[topic],
                score=item.score, explanation=explanation, explanation_language=language,
                explanation_generated_by=method,
            )
            db.add(row)
            citations.append({**item.as_dict(), "topic": topic, "explanation": explanation,
                              "explanation_method": method, "retrieval_confidence": result.confidence})
    await db.flush()
    return citations
