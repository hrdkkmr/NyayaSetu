"""Transactional email content (English/Hindi), as plain text plus an HTML alternative.

Email clients ignore stylesheets, so the HTML uses tables and inline styles only.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


_STRINGS = {
    "en": {
        "subject": "{code} is your NyayaSetu password reset code",
        "greeting": "Hello {name},",
        "intro": "We received a request to reset the password for your NyayaSetu account. "
                 "Enter this code on the reset page:",
        "expiry": "The code expires in {minutes} minutes and can be used once.",
        "ignore": "If you did not ask for this, you can ignore this email; your password will not change.",
        "never": "NyayaSetu will never ask you for this code by phone, SMS or chat.",
        "footer": "NyayaSetu provides legal information and workflow help. It is not a lawyer.",
    },
    "hi": {
        "subject": "{code} आपका न्यायसेतु पासवर्ड रीसेट कोड है",
        "greeting": "नमस्ते {name},",
        "intro": "हमें आपके न्यायसेतु खाते का पासवर्ड रीसेट करने का अनुरोध मिला है। "
                 "रीसेट पेज पर यह कोड डालें:",
        "expiry": "यह कोड {minutes} मिनट में समाप्त हो जाएगा और केवल एक बार इस्तेमाल हो सकता है।",
        "ignore": "अगर आपने यह अनुरोध नहीं किया, तो इस ईमेल को अनदेखा करें; आपका पासवर्ड नहीं बदलेगा।",
        "never": "न्यायसेतु कभी भी फ़ोन, SMS या चैट पर यह कोड नहीं माँगेगा।",
        "footer": "न्यायसेतु कानूनी जानकारी और प्रक्रिया में मदद देता है। यह वकील नहीं है।",
    },
}


def password_reset_code_email(name: str, code: str, minutes: int, language: str = "en") -> EmailContent:
    t = _STRINGS.get(language, _STRINGS["en"])
    lang = language if language in _STRINGS else "en"
    greeting = t["greeting"].format(name=name)
    expiry = t["expiry"].format(minutes=minutes)
    text = "\n\n".join([greeting, t["intro"], f"    {code}", expiry, t["ignore"], t["never"], "—", t["footer"]])
    spaced = " ".join(code)
    html = f"""<!doctype html>
<html lang="{lang}">
<body style="margin:0;padding:0;background:#f4f5f7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;
              font-family:Arial,'Noto Sans Devanagari',sans-serif;color:#1f2937;">
  <tr><td style="background:#1e3a5f;padding:20px 28px;color:#ffffff;font-size:20px;font-weight:bold;">
    NyayaSetu · न्यायसेतु
  </td></tr>
  <tr><td style="padding:28px;font-size:16px;line-height:1.6;">
    <p style="margin:0 0 16px;">{escape(greeting)}</p>
    <p style="margin:0 0 20px;">{escape(t["intro"])}</p>
    <div style="text-align:center;margin:0 0 20px;">
      <span style="display:inline-block;background:#eef2f7;border:1px solid #c7d2e0;border-radius:10px;
                   padding:14px 22px;font-size:32px;letter-spacing:6px;font-weight:bold;
                   font-family:'Courier New',monospace;color:#1e3a5f;"
            aria-label="{escape(code)}">{escape(spaced)}</span>
    </div>
    <p style="margin:0 0 12px;">{escape(expiry)}</p>
    <p style="margin:0 0 12px;color:#4b5563;">{escape(t["ignore"])}</p>
    <p style="margin:0;color:#4b5563;font-weight:bold;">{escape(t["never"])}</p>
  </td></tr>
  <tr><td style="padding:16px 28px;border-top:1px solid #e5e7eb;font-size:13px;color:#6b7280;">
    {escape(t["footer"])}
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""
    return EmailContent(subject=t["subject"].format(code=code), text=text, html=html)
