"""Tokenisation and bilingual query expansion for legal retrieval.

The ingested corpus is English (the authoritative text of central Acts and Rules).
Citizens often ask in Hindi or Hinglish, so queries are expanded with a reviewed
Hindi→English glossary of legal terms. This is retrieval assistance only; it is
never shown to users as a translation of law.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an the of to in for on by with and or as at be is are was were been being it its this that
    these those such any all shall may which who whom whose from into under than then there here
    has have had not no nor but if so do does did can could would should will i me my we our you
    your he she they them his her their what when where how why about after before also other
    said same section sub clause provided""".split()
)

# Reviewed glossary: Hindi (Devanagari and common romanisations) → English legal terms.
HINDI_GLOSSARY: dict[str, list[str]] = {
    "उपभोक्ता": ["consumer"],
    "upbhokta": ["consumer"],
    "शिकायत": ["complaint"],
    "shikayat": ["complaint"],
    "शिकायतकर्ता": ["complainant"],
    "विक्रेता": ["seller", "trader"],
    "दुकानदार": ["trader", "seller"],
    "dukandar": ["trader", "seller"],
    "सेवा": ["service"],
    "seva": ["service"],
    "सेवा में कमी": ["deficiency", "service"],
    "कमी": ["deficiency"],
    "दोष": ["defect"],
    "दोषपूर्ण": ["defect", "defective"],
    "खराब": ["defect", "defective"],
    "kharab": ["defect", "defective"],
    "टूटा": ["defect", "damaged"],
    "नुकसान": ["loss", "injury", "compensation"],
    "मुआवजा": ["compensation"],
    "muavza": ["compensation"],
    "मुआवज़ा": ["compensation"],
    "हर्जाना": ["compensation", "damages"],
    "रिफंड": ["refund", "return", "price"],
    "धनवापसी": ["refund", "return", "price"],
    "पैसे वापस": ["refund", "return", "price"],
    "paise wapas": ["refund", "return", "price"],
    "वापसी": ["return", "refund"],
    "बदलना": ["replace", "replacement"],
    "बदली": ["replace", "replacement"],
    "replace": ["replace", "replacement"],
    "जिला": ["district"],
    "zila": ["district"],
    "जिला आयोग": ["district", "commission"],
    "उपभोक्ता आयोग": ["consumer", "commission"],
    "आयोग": ["commission"],
    "राज्य": ["state"],
    "राष्ट्रीय": ["national"],
    "समय सीमा": ["limitation", "period", "two", "years"],
    "समयसीमा": ["limitation", "period"],
    "कितने दिन": ["limitation", "period"],
    "कब तक": ["limitation", "period"],
    "फीस": ["fee"],
    "शुल्क": ["fee"],
    "fees": ["fee"],
    "ऑनलाइन": ["online", "electronically", "electronic"],
    "online": ["online", "electronically", "electronic"],
    "ई-कॉमर्स": ["e-commerce", "electronic", "online"],
    "अनुचित व्यापार": ["unfair", "trade", "practice"],
    "धोखा": ["unfair", "trade", "practice", "misleading"],
    "धोखाधड़ी": ["unfair", "trade", "practice", "misleading"],
    "भ्रामक विज्ञापन": ["misleading", "advertisement"],
    "विज्ञापन": ["advertisement"],
    "उत्पाद": ["product", "goods"],
    "सामान": ["goods"],
    "saman": ["goods"],
    "माल": ["goods"],
    "बीमा": ["insurance", "service"],
    "बैंक": ["banking", "service"],
    "बिजली": ["electrical", "energy", "service"],
    "मकान": ["housing", "construction"],
    "बिल्डर": ["housing", "construction", "service"],
    "अपील": ["appeal"],
    "मध्यस्थता": ["mediation"],
    "क्षेत्राधिकार": ["jurisdiction"],
    "अधिकार क्षेत्र": ["jurisdiction"],
    "कहाँ": ["jurisdiction", "instituted"],
    "कहां": ["jurisdiction", "instituted"],
    "उत्पाद दायित्व": ["product", "liability"],
    "वारंटी": ["warranty"],
    "गारंटी": ["guarantee", "warranty"],
}

# Reviewed English intent expansions: everyday phrasing → statutory vocabulary.
INTENT_EXPANSIONS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"how long|time limit|deadline|last date|too late|limitation|within how many|kitne din|समय", re.I),
     ["limitation", "within", "two", "years", "cause", "action", "admit"]),
    (re.compile(r"\bfees?\b|cost to file|charges? for filing|शुल्क|फीस", re.I),
     ["fee", "payable", "amount", "table", "rupees", "upto"]),
    (re.compile(r"online|electronic|e-?filing|internet|website|ऑनलाइन", re.I),
     ["filed", "electronically", "manner", "prescribed"]),
    (re.compile(r"which (court|commission|forum)|where (can|do|should) i (file|complain)|jurisdiction|कहाँ|कहां", re.I),
     ["jurisdiction", "district", "commission", "instituted", "value", "consideration"]),
    (re.compile(r"refund|replace|money back|compensation|relief|remedy|मुआवजा|पैसे", re.I),
     ["remove", "defect", "replace", "return", "price", "compensation", "order"]),
    (re.compile(r"appeal|अपील", re.I), ["appeal", "order", "days"]),
]

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.IGNORECASE)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    return [_stem(t) for t in tokens if t not in STOPWORDS and len(t) > 1]


def _stem(token: str) -> str:
    """Very light English stemming so 'defective'/'defects' match 'defect'."""
    for suffix in ("ations", "ation", "ments", "ment", "ities", "ity", "ives", "ive", "ies",
                   "ing", "ers", "er", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def contains_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def expand_query(query: str) -> tuple[str, list[str]]:
    """Return an English retrieval query plus the glossary terms that were matched."""
    lowered = query.lower()
    matched: list[str] = []
    extra: list[str] = []
    for term in sorted(HINDI_GLOSSARY, key=len, reverse=True):
        if term in lowered:
            matched.append(term)
            extra.extend(HINDI_GLOSSARY[term])
    for pattern, terms in INTENT_EXPANSIONS:
        if pattern.search(query):
            extra.extend(terms)
    latin_part = " ".join(_TOKEN.findall(query))
    expanded = " ".join(dict.fromkeys([latin_part, *extra])).strip()
    return expanded or query, matched


def search_text(text: str) -> str:
    return " ".join(tokenize(text))
