"""Public help resources shown to users.

Each entry records where it was checked. Numbers were cross-checked on 2026-10-30;
the UI always shows the official URL so users can confirm before relying on it.
"""

from __future__ import annotations

from typing import Any

VERIFIED_ON = "2026-10-30"

RESOURCES: dict[str, dict[str, Any]] = {
    "emergency": {
        "name_en": "Emergency Response Support System",
        "name_hi": "आपातकालीन सहायता",
        "phone": "112",
        "url": "https://112.gov.in/",
        "use_en": "Immediate danger to life or safety (police, fire, ambulance).",
        "use_hi": "जान या सुरक्षा को तुरंत खतरा हो (पुलिस, अग्निशमन, एम्बुलेंस)।",
    },
    "legal_aid": {
        "name_en": "NALSA legal aid helpline",
        "name_hi": "नालसा कानूनी सहायता हेल्पलाइन",
        "phone": "15100",
        "url": "https://nalsa.gov.in/",
        "use_en": "Free legal advice and legal aid from Legal Services Authorities.",
        "use_hi": "विधिक सेवा प्राधिकरण से मुफ़्त कानूनी सलाह और सहायता।",
    },
    "consumer_helpline": {
        "name_en": "National Consumer Helpline",
        "name_hi": "राष्ट्रीय उपभोक्ता हेल्पलाइन",
        "phone": "1915",
        "url": "https://consumerhelpline.gov.in/",
        "use_en": "Pre-litigation help to resolve consumer grievances with companies.",
        "use_hi": "कंपनियों के साथ उपभोक्ता शिकायतें सुलझाने में मुकदमे से पहले मदद।",
    },
    "cyber_crime": {
        "name_en": "National Cyber Crime Reporting",
        "name_hi": "राष्ट्रीय साइबर अपराध रिपोर्टिंग",
        "phone": "1930",
        "url": "https://cybercrime.gov.in/",
        "use_en": "Report online financial fraud quickly, and other cyber crimes.",
        "use_hi": "ऑनलाइन वित्तीय धोखाधड़ी और अन्य साइबर अपराध की तुरंत रिपोर्ट करें।",
    },
    "mental_health": {
        "name_en": "Tele-MANAS mental health helpline",
        "name_hi": "टेली-मानस मानसिक स्वास्थ्य हेल्पलाइन",
        "phone": "14416",
        "url": "https://telemanas.mohfw.gov.in/",
        "use_en": "Free 24x7 mental health support.",
        "use_hi": "मुफ़्त 24x7 मानसिक स्वास्थ्य सहायता।",
    },
    "e_jagriti": {
        "name_en": "e-Jagriti (Consumer Commission e-filing)",
        "name_hi": "ई-जागृति (उपभोक्ता आयोग ई-फाइलिंग)",
        "phone": None,
        "url": "https://e-jagriti.gov.in/",
        "use_en": "Official portal to file and track consumer complaints online.",
        "use_hi": "उपभोक्ता शिकायत ऑनलाइन दर्ज करने और ट्रैक करने का आधिकारिक पोर्टल।",
    },
}


def resource(key: str, language: str) -> dict[str, Any]:
    r = RESOURCES[key]
    hi = language == "hi"
    return {
        "key": key,
        "name": r["name_hi"] if hi else r["name_en"],
        "phone": r["phone"],
        "url": r["url"],
        "use": r["use_hi"] if hi else r["use_en"],
        "verified_on": VERIFIED_ON,
    }
