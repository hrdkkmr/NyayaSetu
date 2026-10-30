"""e-Jagriti filing adapter.

What was established about the portal (https://e-jagriti.gov.in, inspected 30 Oct 2026):
  * It is a single-page web application operated by the Department of Consumer Affairs.
  * Users sign in with mobile/email OTP and a CAPTCHA.
  * Its document upload component accepts PDF only and states a 25 MB per-file limit.
  * Its client-side validation limits District Commission complaints to ₹50 lakh paid consideration,
    matching the 2021 Jurisdiction Rules.
  * No public, documented API for third-party complaint submission was found.

Therefore this adapter supports:
  * GUIDED filing (default): step-by-step instructions, a prepared data sheet and approved PDFs.
  * BROWSER_ASSIST (optional, local deployments only): opens the portal in a Playwright-driven
    browser for the user, who performs login, OTP, CAPTCHA and the final submit themselves.
It never automates authentication, never solves CAPTCHAs, never calls private portal APIs and
never clicks the final submit button. An acknowledgement is recorded only from what the user
reports or uploads.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

PORTAL_NAME = "e-Jagriti"
OBSERVED_ON = "2026-10-30"
UPLOAD_RULES = {"formats": ["PDF"], "max_file_mb": 25, "source": "e-Jagriti upload component text", "observed_on": OBSERVED_ON}


@dataclass
class Capabilities:
    guided: bool
    browser_assist: bool
    api_submission: bool
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def capabilities() -> Capabilities:
    s = get_settings()
    assist = s.enable_browser_assist and playwright_installed()
    notes = ["No public API for complaint submission is available; automated submission is not offered."]
    if not assist:
        notes.append("Browser assistance is disabled (set ENABLE_BROWSER_ASSIST=true and install Playwright "
                     "on a machine the user can see).")
    return Capabilities(guided=True, browser_assist=assist, api_submission=False, notes=notes)


async def check_health() -> dict[str, Any]:
    url = get_settings().ejagriti_base_url
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "NyayaSetu-healthcheck/0.1"})
        return {"reachable": resp.status_code < 500, "status_code": resp.status_code,
                "latency_ms": int((time.perf_counter() - started) * 1000)}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": type(exc).__name__}


def guided_steps(context: dict[str, Any], language: str) -> list[dict[str, Any]]:
    """Step-by-step filing guide. Portal labels can change, so steps describe intent, not exact buttons."""
    base = get_settings().ejagriti_base_url
    forum = context.get("forum_label") or "the appropriate Consumer Commission"
    fee = context.get("fee_text")
    hi = language == "hi"
    steps = [
        ("open", "Open the official e-Jagriti portal", "आधिकारिक ई-जागृति पोर्टल खोलें",
         f"Go to {base}. Check the address bar shows e-jagriti.gov.in before entering any details.",
         f"{base} पर जाएँ। कोई जानकारी डालने से पहले पता बार में e-jagriti.gov.in देखें।"),
        ("login", "Sign in or register yourself", "खुद लॉग-इन या रजिस्टर करें",
         "Use your own mobile number or email. You will receive an OTP and must solve a CAPTCHA. NyayaSetu never "
         "asks for your OTP or password.",
         "अपना मोबाइल नंबर या ईमेल इस्तेमाल करें। OTP आएगा और CAPTCHA भरना होगा। NyayaSetu कभी आपका OTP या पासवर्ड नहीं माँगता।"),
        ("start", "Start a new consumer complaint", "नई उपभोक्ता शिकायत शुरू करें",
         f"Choose the option to file a new complaint and select {forum}. Labels on the portal may change.",
         f"नई शिकायत दर्ज करने का विकल्प चुनें और {forum} चुनें। पोर्टल पर नाम बदल सकते हैं।"),
        ("details", "Enter the details from your data sheet", "डेटा शीट से जानकारी भरें",
         "Copy names, addresses, dates and amounts from the approved data sheet below so they match your documents.",
         "नीचे दी गई स्वीकृत डेटा शीट से नाम, पते, तारीखें और राशि भरें ताकि वे आपके दस्तावेज़ों से मेल खाएँ।"),
        ("upload", "Upload your approved PDFs", "स्वीकृत PDF अपलोड करें",
         f"Upload the approved complaint and annexures. The portal accepts PDF files only and states a "
         f"{UPLOAD_RULES['max_file_mb']} MB limit per file (as observed on {OBSERVED_ON}).",
         f"स्वीकृत शिकायत और संलग्नक अपलोड करें। पोर्टल केवल PDF लेता है और प्रति फ़ाइल {UPLOAD_RULES['max_file_mb']} MB की सीमा बताता है।"),
        ("fee", "Pay the fee if one applies", "अगर फीस लागू हो तो भुगतान करें",
         (fee or "Pay the fee shown by the portal, if any.") + " Payments are made by you on the portal.",
         (fee or "पोर्टल पर दिखाई गई फीस, अगर कोई हो, का भुगतान करें।") + " भुगतान आप खुद पोर्टल पर करेंगे।"),
        ("submit", "Review and submit on the portal", "पोर्टल पर जाँच कर जमा करें",
         "Check everything on the portal's preview, then press submit yourself.",
         "पोर्टल के प्रीव्यू में सब जाँचें, फिर खुद जमा करें।"),
        ("acknowledge", "Record your filing reference in NyayaSetu", "NyayaSetu में फाइलिंग नंबर दर्ज करें",
         "Note the reference/diary number the portal shows and download the acknowledgement. Enter it here so "
         "your case can be tracked.",
         "पोर्टल पर दिखा रेफ़रेंस/डायरी नंबर नोट करें और पावती डाउनलोड करें। ट्रैकिंग के लिए इसे यहाँ दर्ज करें।"),
    ]
    return [
        {"key": key, "title": t_hi if hi else t_en, "detail": d_hi if hi else d_en, "official_url": base}
        for key, t_en, t_hi, d_en, d_hi in steps
    ]


def data_sheet(slots: dict[str, Any]) -> list[dict[str, str]]:
    """Fields the user will copy into the portal - only user-provided or user-confirmed values."""
    labels = [
        ("complainant_name", "Complainant name"), ("complainant_address", "Complainant address"),
        ("complainant_location", "District / State"), ("seller_name", "Opposite party name"),
        ("seller_address", "Opposite party address"), ("product_or_service", "Goods / service"),
        ("purchase_date", "Date of purchase"), ("amount_paid", "Amount paid (₹)"),
        ("problem_date", "Date cause of action arose"), ("desired_remedy", "Relief sought"),
    ]
    sheet = []
    for key, label in labels:
        slot = slots.get(key)
        ok = slot is not None and slot.get("provenance") != "ai_inference"
        sheet.append({"key": key, "label": label, "value": slot["value"] if ok and slot else "", "missing": str(not ok).lower()})
    return sheet
