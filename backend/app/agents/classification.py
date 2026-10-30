"""Classification agent: decides whether the matter fits the consumer-dispute workflow.

It never forces a matter into the consumer route. When the description points to a
criminal, cyber-fraud, family, employment or property matter - or the user may not be
a "consumer" under section 2(7) - the case is routed to the appropriate help and
flagged for professional review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.agents import extract as ex
from app.agents.llm import LLMProvider, LLMRefusalError, LLMUnavailableError

Category = Literal[
    "consumer_dispute", "criminal_matter", "cyber_fraud", "family_matter", "employment",
    "property_tenancy", "other", "unclear",
]

SUPPORTED = {"consumer_dispute"}

REFERRAL_RESOURCES: dict[str, list[str]] = {
    "criminal_matter": ["emergency", "legal_aid"],
    "cyber_fraud": ["cyber_crime", "legal_aid"],
    "family_matter": ["legal_aid"],
    "employment": ["legal_aid"],
    "property_tenancy": ["legal_aid"],
    "other": ["legal_aid"],
}


@dataclass
class Classification:
    category: str
    confidence: float
    supported: bool
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, int] = field(default_factory=dict)
    method: str = "rules"
    secondary: list[str] = field(default_factory=list)


def classify_offline(text: str) -> Classification:
    scores = ex.category_scores(text)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score == 0:
        return Classification("unclear", 0.2, False, ["No clear signals yet."], scores)
    margin = top_score - second_score
    confidence = min(0.9, 0.4 + 0.15 * top_score + 0.1 * margin)
    secondary = [c for c, s in ranked[1:] if s > 0]
    reasons = [f"Matched {top_score} indicator(s) for {top.replace('_', ' ')}."]
    if secondary:
        reasons.append("Also mentions: " + ", ".join(c.replace("_", " ") for c in secondary) + ".")
    return Classification(top, round(confidence, 2), top in SUPPORTED, reasons, scores, secondary=secondary)


class LLMClassification(BaseModel):
    category: Category
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(description="Short reasons grounded in the user's words.")
    secondary_categories: list[Category] = []


CLASSIFY_SYSTEM = """Classify a citizen's legal problem in India into one category for routing.
consumer_dispute = a person paid for goods or a service and has a grievance against the seller/provider
(defect, deficiency in service, unfair trade practice, refund/replacement). criminal_matter = violence,
theft, threats, offences needing police. cyber_fraud = online fraud, hacked accounts, OTP/UPI scams.
family_matter, employment, property_tenancy as named. Use "unclear" if there is not enough information.
This is routing only - do not give legal conclusions. Base reasons only on the user's words."""


async def classify(llm: LLMProvider, allow_llm: bool, text: str) -> Classification:
    rules = classify_offline(text)
    if not (allow_llm and llm.available):
        return rules
    try:
        result = await llm.structured(
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": f"Citizen's description:\n<<<\n{text[:6000]}\n>>>"}],
            schema=LLMClassification,
            max_tokens=800,
        )
    except (LLMUnavailableError, LLMRefusalError):
        return rules
    v = result.value
    # If the two methods disagree on a non-consumer category, keep the more cautious result.
    category: str = v.category
    if rules.category in REFERRAL_RESOURCES and rules.category != "other" and v.category == "consumer_dispute":
        category = rules.category if rules.signals.get(rules.category, 0) >= 2 else v.category
    return Classification(
        category=category,
        confidence=round(min(v.confidence, 0.95), 2),
        supported=category in SUPPORTED,
        reasons=v.reasons[:4],
        signals=rules.signals,
        method="llm",
        secondary=[c for c in v.secondary_categories if c != category],
    )
