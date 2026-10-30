"""Intake slots for consumer disputes.

Slots are the facts the workflow needs. Questions are asked one at a time, in the
user's language, in priority order. `required_for_draft` slots must be known (and
user-provided or user-confirmed) before a complaint draft is generated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    key: str
    label_en: str
    label_hi: str
    question_en: str
    question_hi: str
    value_type: str = "text"
    required_for_draft: bool = False
    priority: int = 50
    explain_en: str | None = None
    explain_hi: str | None = None


SLOTS: list[Slot] = [
    Slot(
        "grievance", "What went wrong", "क्या समस्या हुई",
        "Please tell me what happened, in your own words.",
        "कृपया अपने शब्दों में बताइए कि क्या हुआ।",
        required_for_draft=True, priority=1,
    ),
    Slot(
        "product_or_service", "Product or service", "सामान या सेवा",
        "What exactly did you buy, or which service did you pay for?",
        "आपने क्या खरीदा था, या किस सेवा के लिए भुगतान किया था?",
        required_for_draft=True, priority=5,
    ),
    Slot(
        "seller_name", "Seller / service provider", "विक्रेता / सेवा प्रदाता",
        "What is the name of the seller, company or service provider?",
        "विक्रेता, कंपनी या सेवा प्रदाता का नाम क्या है?",
        required_for_draft=True, priority=10,
    ),
    Slot(
        "purchase_mode", "Bought online or in a shop", "ऑनलाइन या दुकान से",
        "Did you buy it online (website or app) or from a shop in person?",
        "आपने यह ऑनलाइन (वेबसाइट या ऐप) से खरीदा था या दुकान से?",
        value_type="choice", priority=15,
    ),
    Slot(
        "purchase_date", "Date of purchase / payment", "खरीद / भुगतान की तारीख",
        "On what date did you buy it or pay for it? An approximate date is fine if you are not sure.",
        "आपने किस तारीख को खरीदा या भुगतान किया? अगर पक्का याद न हो तो अंदाज़न तारीख बता दीजिए।",
        value_type="date", required_for_draft=True, priority=20,
    ),
    Slot(
        "amount_paid", "Amount paid", "भुगतान की गई राशि",
        "How much did you pay in total, in rupees?",
        "आपने कुल कितने रुपये का भुगतान किया?",
        value_type="money", required_for_draft=True, priority=25,
        explain_en="The amount paid decides which Consumer Commission hears the complaint and the filing fee.",
        explain_hi="भुगतान की गई राशि से तय होता है कि कौन सा उपभोक्ता आयोग सुनवाई करेगा और कितनी फीस लगेगी।",
    ),
    Slot(
        "problem_date", "When the problem happened", "समस्या कब हुई",
        "When did the problem happen or when did you first notice it?",
        "समस्या कब हुई या आपको पहली बार कब पता चला?",
        value_type="date", required_for_draft=True, priority=30,
        explain_en="A consumer complaint generally has to be filed within two years of when the problem arose.",
        explain_hi="उपभोक्ता शिकायत आम तौर पर समस्या होने के दो साल के अंदर दर्ज करनी होती है।",
    ),
    Slot(
        "contacted_seller", "Complaint made to the seller", "विक्रेता से की गई शिकायत",
        "Have you already complained to the seller — and if so, when, and what did they say?",
        "क्या आपने विक्रेता से पहले शिकायत की थी — और अगर की थी, तो कब और उन्होंने क्या जवाब दिया?",
        priority=35,
    ),
    Slot(
        "desired_remedy", "What you want", "आप क्या चाहते हैं",
        "What would you like to happen now — a replacement, a refund, repair, or compensation?",
        "अब आप क्या चाहते हैं — सामान बदलना, पैसे वापस, मरम्मत, या मुआवज़ा?",
        value_type="choice", required_for_draft=True, priority=40,
    ),
    Slot(
        "evidence", "Proof you have", "आपके पास सबूत",
        "What proof do you have? For example: bill or invoice, order confirmation, photos, emails or chats.",
        "आपके पास क्या सबूत है? जैसे: बिल, ऑर्डर की पुष्टि, फोटो, ईमेल या चैट।",
        priority=45,
    ),
    Slot(
        "complainant_location", "Your district and state", "आपका ज़िला और राज्य",
        "Which district and state do you live or work in?",
        "आप किस ज़िले और राज्य में रहते या काम करते हैं?",
        required_for_draft=True, priority=50,
        explain_en="You can usually file in the District Commission where you live or work.",
        explain_hi="आप आम तौर पर उस ज़िला आयोग में शिकायत कर सकते हैं जहाँ आप रहते या काम करते हैं।",
    ),
    Slot(
        "commercial_purpose", "Bought for business use?", "व्यापार के लिए खरीदा?",
        "Did you buy this for your own or family use, or for a business or for resale?",
        "क्या आपने यह अपने या परिवार के उपयोग के लिए खरीदा था, या किसी व्यापार या दोबारा बेचने के लिए?",
        value_type="choice", required_for_draft=True, priority=55,
        explain_en="The law does not treat purchases made for resale or commercial purposes as consumer purchases, except for earning a livelihood through self-employment.",
        explain_hi="दोबारा बेचने या व्यापारिक उद्देश्य से की गई खरीद को कानून उपभोक्ता खरीद नहीं मानता, सिवाय स्व-रोज़गार से आजीविका कमाने के।",
    ),
    Slot(
        "seller_address", "Seller's address", "विक्रेता का पता",
        "Do you know the seller's address or registered office? It will be needed in the complaint.",
        "क्या आपको विक्रेता का पता या रजिस्टर्ड ऑफ़िस मालूम है? शिकायत में इसकी ज़रूरत होगी।",
        priority=60,
    ),
    Slot(
        "complainant_name", "Your full name", "आपका पूरा नाम",
        "What is your full name as it should appear on the complaint?",
        "शिकायत में आपका पूरा नाम क्या लिखा जाए?",
        required_for_draft=True, priority=65,
    ),
    Slot(
        "complainant_address", "Your address", "आपका पता",
        "What is your full postal address?",
        "आपका पूरा डाक पता क्या है?",
        required_for_draft=True, priority=70,
    ),
]

SLOT_BY_KEY: dict[str, Slot] = {s.key: s for s in SLOTS}
REQUIRED_FOR_DRAFT = [s.key for s in SLOTS if s.required_for_draft]
