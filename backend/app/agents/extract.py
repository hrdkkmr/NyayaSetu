"""Deterministic extractors for English, Hindi and Hinglish text.

Used by the offline intake path and by document extraction. Every extracted
value carries the exact source excerpt so users can see where it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

_MONTHS = {
    "jan": 1, "january": 1, "जनवरी": 1, "feb": 2, "february": 2, "फरवरी": 2, "फ़रवरी": 2,
    "mar": 3, "march": 3, "मार्च": 3, "apr": 4, "april": 4, "अप्रैल": 4, "may": 5, "मई": 5,
    "jun": 6, "june": 6, "जून": 6, "jul": 7, "july": 7, "जुलाई": 7, "aug": 8, "august": 8,
    "अगस्त": 8, "sep": 9, "sept": 9, "september": 9, "सितंबर": 9, "सितम्बर": 9, "oct": 10,
    "october": 10, "अक्टूबर": 10, "nov": 11, "november": 11, "नवंबर": 11, "नवम्बर": 11,
    "dec": 12, "december": 12, "दिसंबर": 12, "दिसम्बर": 12,
}
# Word boundary that also understands Devanagari combining marks (\b does not).
_WB = r"(?![\wऀ-ॿ])"
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))


@dataclass
class Extracted:
    key: str
    value: str
    excerpt: str
    confidence: float


def _excerpt(text: str, start: int, end: int, pad: int = 40) -> str:
    return text[max(0, start - pad): min(len(text), end + pad)].strip()


def normalise_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        if y < 100:
            y += 2000
        result = date(y, m, d)
    except ValueError:
        return None
    if result.year < 1950 or result > date.today() + timedelta(days=366):
        return None
    return result


def find_dates(text: str, today: date | None = None) -> list[tuple[date, str, bool]]:
    """Return (date, excerpt, is_approximate) tuples in order of appearance."""
    today = today or date.today()
    t = normalise_digits(text)
    found: list[tuple[int, date, str, bool]] = []
    for m in re.finditer(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", t):
        d = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            found.append((m.start(), d, _excerpt(t, m.start(), m.end()), False))
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append((m.start(), d, _excerpt(t, m.start(), m.end()), False))
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_MONTH_ALT})[a-z]*[,]?\s*(\d{{4}})?", t, re.I):
        year = int(m.group(3)) if m.group(3) else today.year
        d = _safe_date(year, _MONTHS[m.group(2).lower()[:3] if m.group(2).isascii() else m.group(2)], int(m.group(1)))
        if d:
            approx = m.group(3) is None
            if approx and d > today:
                d = _safe_date(year - 1, d.month, d.day) or d
            found.append((m.start(), d, _excerpt(t, m.start(), m.end()), approx))
    for m in re.finditer(rf"\b({_MONTH_ALT})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", t, re.I):
        key = m.group(1).lower()
        d = _safe_date(int(m.group(3)), _MONTHS[key[:3] if key.isascii() else key], int(m.group(2)))
        if d:
            found.append((m.start(), d, _excerpt(t, m.start(), m.end()), False))
    lowered = t.lower()
    relative = [
        (r"\byesterday\b|\bकल\b", 1), (r"\blast week\b|पिछले हफ्ते|पिछले सप्ताह", 7),
        (r"\blast month\b|पिछले महीने", 30), (r"\blast year\b|पिछले साल", 365),
    ]
    for pattern, days in relative:
        rel = re.search(pattern, lowered)
        if rel:
            found.append((rel.start(), today - timedelta(days=days), _excerpt(t, rel.start(), rel.end()), True))
    ago = re.search(r"(\d{1,3})\s*(days?|din|दिन|weeks?|hafte|हफ्ते|months?|mahine|महीने)\s*(ago|pehle|पहले)", lowered)
    if ago:
        m = ago
        n = int(m.group(1))
        unit = m.group(2)
        days = n * (7 if unit.startswith(("week", "haft", "हफ्")) else 30 if unit.startswith(("month", "mahin", "महीन")) else 1)
        found.append((m.start(), today - timedelta(days=days), _excerpt(t, m.start(), m.end()), True))
    found.sort(key=lambda x: x[0])
    seen: set[date] = set()
    out = []
    for _, d, ex, approx in found:
        if d not in seen:
            seen.add(d)
            out.append((d, ex, approx))
    return out


_AMOUNT_PATTERNS = [
    re.compile(r"(?:₹|rs\.?|inr|rupees?|रुपये|रुपए|रु\.?)\s*([\d,]+(?:\.\d{1,2})?)\s*(lakh|lac|लाख|crore|करोड़|k|thousand|हज़ार|हजार)?", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(lakh|lac|लाख|crore|करोड़|thousand|हज़ार|हजार|k)?\s*(?:₹|rs\.?|rupees?|रुपये|रुपए|रु|/-)", re.I),
    re.compile(r"([\d.]+)\s*(lakh|lac|लाख|crore|करोड़|हज़ार|हजार)\b", re.I),
]
_MULTIPLIERS = {
    "lakh": 100_000, "lac": 100_000, "लाख": 100_000, "crore": 10_000_000, "करोड़": 10_000_000,
    "k": 1_000, "thousand": 1_000, "हज़ार": 1_000, "हजार": 1_000,
}


def find_amounts(text: str) -> list[tuple[Decimal, str]]:
    t = normalise_digits(text)
    results: list[tuple[int, Decimal, str]] = []
    taken: list[tuple[int, int]] = []
    for pattern in _AMOUNT_PATTERNS:
        for m in pattern.finditer(t):
            if any(s <= m.start() < e for s, e in taken):
                continue
            raw = m.group(1).replace(",", "")
            if not raw or raw == ".":
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue
            unit = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
            value *= _MULTIPLIERS.get(unit, 1)
            if value <= 0 or value > Decimal("1e11"):
                continue
            taken.append((m.start(), m.end()))
            results.append((m.start(), value.quantize(Decimal("0.01")), _excerpt(t, m.start(), m.end())))
    results.sort(key=lambda x: x[0])
    return [(v, ex) for _, v, ex in results]


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
ORDER_ID = re.compile(r"\b(?:order|ऑर्डर)\s*(?:id|no\.?|number|#|नंबर)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{5,30})\b", re.I)
INVOICE_NO = re.compile(r"\b(?:invoice|bill|tax invoice|बिल)\s*(?:no\.?|number|#|नंबर)\s*[:#]?\s*([A-Z0-9][A-Z0-9/\-]{2,30})\b", re.I)
PINCODE = re.compile(r"\b[1-9]\d{5}\b")


REMEDY_KEYWORDS: dict[str, list[str]] = {
    "replacement": ["replace", "replacement", "exchange", "बदल", "बदली", "badal", "naya", "नया"],
    "refund": ["refund", "money back", "return the money", "paise wapas", "पैसे वापस", "रिफंड", "वापस कर", "wapas"],
    "repair": ["repair", "fix", "मरम्मत", "ठीक कर", "theek"],
    "compensation": ["compensation", "damages", "harassment", "मुआवजा", "मुआवज़ा", "हर्जाना", "muavza"],
}

PURCHASE_MODE_KEYWORDS = {
    "online": ["online", "website", "app", "amazon", "flipkart", "myntra", "meesho", "ऑनलाइन", "ई-कॉमर्स", "e-commerce", "delivered", "delivery", "डिलीवरी"],
    "offline": ["shop", "store", "showroom", "दुकान", "शोरूम", "dukan", "market"],
}

EVIDENCE_KEYWORDS = {
    "invoice": ["invoice", "bill", "receipt", "बिल", "रसीद"],
    "order_confirmation": ["order confirmation", "order id", "order number", "ऑर्डर"],
    "photos": ["photo", "picture", "image", "video", "फोटो", "वीडियो"],
    "communication": ["email", "chat", "whatsapp", "sms", "message", "call recording", "ईमेल", "चैट", "मैसेज"],
    "warranty_card": ["warranty", "guarantee", "वारंटी", "गारंटी"],
    "payment_proof": ["upi", "bank statement", "card statement", "transaction", "payment", "भुगतान"],
}


def keyword_hits(text: str, mapping: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    return [key for key, words in mapping.items() if any(w in lowered for w in words)]


def yes_no(text: str) -> bool | None:
    lowered = text.strip().lower()
    if re.search(r"^(yes|yeah|yep|haan|ha|han|हाँ|हां|जी|ji|sure|correct|right|ok|okay|sahi|सही)" + _WB, lowered):
        return True
    if re.search(r"^(no|nope|nahi|nahin|na|नहीं|नही|ना|गलत|galat|wrong)" + _WB, lowered):
        return False
    return None


def commercial_purpose(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"resale|resell|business|shop stock|for my company|commercial|व्यापार|बेचने|दुकान के लिए|dhandha|dhanda", lowered):
        if re.search(r"self[- ]employ|livelihood|रोज़ी|रोजी|आजीविका|अपनी रोज़ी", lowered):
            return "livelihood"
        return "commercial"
    if re.search(r"personal|myself|my own|family|home|ghar|घर|परिवार|अपने लिए|खुद|self use|own use", lowered):
        return "personal"
    return None


# Category signals. These are routing hints, not legal conclusions.
CATEGORY_SIGNALS: dict[str, list[str]] = {
    "consumer_dispute": [
        "bought", "purchase", "purchased", "seller", "shop", "order", "delivered", "defective", "damaged",
        "refund", "replace", "warranty", "service center", "service centre", "e-commerce", "online",
        "product", "insurance claim", "airline", "flight", "builder", "possession", "courier", "telecom",
        "internet", "electricity bill", "hospital bill", "खरीदा", "विक्रेता", "दुकान", "खराब", "टूटा",
        "रिफंड", "वारंटी", "डिलीवरी", "सामान", "kharida", "kharab", "dukan", "laptop", "phone", "mobile",
        "fridge", "tv", "washing machine", "ऑर्डर", "बीमा",
    ],
    "criminal_matter": [
        "assault", "attack", "beat me", "threat", "murder", "theft", "stolen", "robbery", "kidnap",
        "rape", "molest", "fir", "police", "चोरी", "मारपीट", "धमकी", "पुलिस", "एफआईआर",
    ],
    "cyber_fraud": [
        "otp", "hacked", "phishing", "scam call", "upi fraud", "money debited without", "cyber",
        "fake website", "साइबर", "धोखाधड़ी", "ठगी",
    ],
    "family_matter": [
        "divorce", "maintenance", "custody", "dowry", "domestic violence", "husband", "wife", "in-laws",
        "तलाक", "दहेज", "घरेलू हिंसा", "पति", "पत्नी", "भरण-पोषण",
    ],
    "employment": [
        "salary", "wages", "employer", "fired", "terminated", "gratuity", "provident fund", "pf",
        "वेतन", "तनख्वाह", "नौकरी से निकाल", "मालिक",
    ],
    "property_tenancy": [
        "landlord", "tenant", "rent", "eviction", "property dispute", "land", "encroachment",
        "मकान मालिक", "किराया", "किरायेदार", "ज़मीन", "जमीन", "कब्ज़ा",
    ],
}


def category_scores(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {
        cat: sum(1 for w in words if re.search(rf"(?<![\wऀ-ॿ]){re.escape(w)}{_WB}", lowered))
        for cat, words in CATEGORY_SIGNALS.items()
    }


URGENT_SAFETY = re.compile(
    r"suicid|kill myself|want to die|being beaten|in danger|threatening to kill|आत्महत्या|जान से मार|"
    r"मुझे मार|खतरे में", re.I,
)
