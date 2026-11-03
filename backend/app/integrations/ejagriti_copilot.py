"""e-Jagriti filing co-pilot: a bundle the citizen runs on their own computer.

The bundle (ZIP) holds the locked, approved PDFs, a JSON packet of user-provided / user-confirmed
details, and a Playwright script. The script opens a visible browser, waits while the citizen logs
in (mobile number, OTP, CAPTCHA), fills only fields whose label clearly matches a packet entry,
attaches PDFs where an upload field's label names the document, then stops at
HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT. It never clicks anything: reviewing and the final submit are
the citizen's. It runs locally because a hosted server has no screen for the citizen to use.

The portal's form has not been mapped against the live site; matching is by visible label, and any
field it is unsure about is left for the citizen and listed in its report.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

HITL_STATE = "HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT"


@dataclass
class PacketDocument:
    doc_type: str
    title: str
    filename: str
    pdf: bytes
    version_number: int
    content_sha256: str


def build_packet(*, case_reference: str, portal_url: str, data_sheet: list[dict[str, str]],
                 forum: str | None, documents: list[PacketDocument], generated_at: datetime) -> dict[str, Any]:
    return {
        "case_reference": case_reference,
        "portal_url": portal_url,
        "generated_at": generated_at.isoformat(),
        "hitl_state": HITL_STATE,
        "forum": forum,
        "fields": {row["key"]: row["value"] for row in data_sheet if row["value"]},
        "missing": [row["label"] for row in data_sheet if not row["value"]],
        "documents": [{
            "doc_type": d.doc_type, "title": d.title, "file": d.filename, "version": d.version_number,
            "approved_content_sha256": d.content_sha256, "pdf_sha256": hashlib.sha256(d.pdf).hexdigest(),
        } for d in documents],
    }


def build_bundle(packet: dict[str, Any], documents: list[PacketDocument]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("case_packet.json", json.dumps(packet, ensure_ascii=False, indent=2))
        z.writestr("nyayasetu_copilot.py", SCRIPT)
        z.writestr("README.txt", README)
        for d in documents:
            z.writestr(f"documents/{d.filename}", d.pdf)
    return buffer.getvalue()


README = """NyayaSetu e-Jagriti co-pilot
============================

This helps you fill the e-Jagriti consumer complaint form with the details and documents you
approved in NyayaSetu. It runs on YOUR computer, in a browser window you can see. It never logs
in for you, never enters an OTP, and never clicks submit, pay or sign.

1. Install once:   pip install playwright   then   python -m playwright install chromium
2. Unzip this folder and run:   python nyayasetu_copilot.py
3. In the browser that opens, log in yourself (mobile number, OTP, CAPTCHA) and open the
   new-complaint form. Then press Enter in the terminal.
4. The co-pilot fills the fields it is sure about and lists what it left for you.
5. It stops at HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT. Check every field and attachment on the
   portal, then submit yourself if everything is right.
6. Enter the acknowledgement number the portal gives you back into NyayaSetu.

The co-pilot has not been tested against the live portal form. Anything it is unsure about is
left empty for you. NyayaSetu gives legal information, not legal advice.
"""


SCRIPT = r'''#!/usr/bin/env python3
"""NyayaSetu e-Jagriti co-pilot. Runs on your computer; see README.txt.

Fills only fields whose visible label clearly matches your approved details, attaches your
approved PDFs, then pauses at HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT. It never clicks anything.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HITL_STATE = "HITL_AWAITING_CITIZEN_OTP_AND_SUBMIT"
NEVER_TOUCH = re.compile(r"submit|pay|e-?sign|final|confirm and file|proceed|otp|captcha|password|mobile|login", re.I)
MATCHERS = {
    "complainant_name": re.compile(r"^(complainant('s)?\s+)?(full\s+)?name", re.I),
    "complainant_address": re.compile(r"complainant.*address|^address", re.I),
    "seller_name": re.compile(r"(opposite\s+party|respondent).*name", re.I),
    "seller_address": re.compile(r"(opposite\s+party|respondent).*address", re.I),
    "amount_paid": re.compile(r"(paid\s+)?consideration|amount\s+paid", re.I),
    "product_or_service": re.compile(r"(goods|product|service).*(description|name)", re.I),
}
UPLOAD_HINTS = {
    "consumer_complaint": re.compile(r"complaint", re.I),
    "list_of_dates": re.compile(r"list of dates|synopsis|chronolog", re.I),
    "evidence_index": re.compile(r"index|annexure|evidence", re.I),
    "memo_of_parties": re.compile(r"memo of parties|parties", re.I),
}
LABEL_JS = """el => {
  let label = '';
  if (el.id) { const l = document.querySelector(`label[for="${el.id}"]`); if (l) label = l.innerText; }
  if (!label) { const l = el.closest('label'); if (l) label = l.innerText; }
  if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
  return label.trim().slice(0, 160);
}"""


def load_packet(here):
    packet = json.loads((here / "case_packet.json").read_text(encoding="utf-8"))
    for doc in packet["documents"]:
        data = (here / "documents" / doc["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != doc["pdf_sha256"]:
            sys.exit(f"{doc['file']} has changed since you approved it. Download a fresh bundle from NyayaSetu.")
    return packet


def fill(page, packet, here):
    filled, left = [], []
    for el in page.locator("input:visible, textarea:visible, select:visible").all():
        kind = (el.get_attribute("type") or "").lower()
        label = el.evaluate(LABEL_JS)
        if kind in ("hidden", "password", "submit", "button", "checkbox", "radio") or NEVER_TOUCH.search(label):
            continue
        if kind == "file":
            matches = [d for d in packet["documents"] if UPLOAD_HINTS.get(d["doc_type"], re.compile("$^")).search(label)]
            if len(matches) == 1:
                el.set_input_files(str(here / "documents" / matches[0]["file"]))
                filled.append(f"{label} <- {matches[0]['file']}")
            else:
                left.append(f"{label} (upload)")
            continue
        keys = [k for k, rx in MATCHERS.items() if rx.search(label) and packet["fields"].get(k)]
        if len(keys) != 1 or (el.input_value() or "").strip():
            if label:
                left.append(label)
            continue
        value = packet["fields"][keys[0]]
        if el.evaluate("e => e.tagName") == "SELECT":
            continue  # choose drop-downs (state, district, commission) yourself
        el.fill(value)
        filled.append(f"{label} <- {value}")
    return filled, left


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
    here = Path(__file__).resolve().parent
    packet = load_packet(here)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(packet["portal_url"])
        print("\n1) In the browser, log in yourself (mobile number, OTP, CAPTCHA).")
        print("2) Open the form to file a new consumer complaint.")
        input("3) Then press Enter here... ")
        filled, left = fill(page, packet, here)
        print("\nFilled from your approved details:")
        for line in filled or ["(nothing matched clearly)"]:
            print("  +", line)
        print("\nLeft for you to fill or choose:")
        for line in left + [f"{m} (not in your case yet)" for m in packet["missing"]] or ["(none)"]:
            print("  -", line)
        if packet.get("forum"):
            print(f"\nForum worked out by NyayaSetu: {packet['forum']} Commission (choose it in the form yourself).")
        print(f"\n{HITL_STATE}")
        print("Check every field and attachment on the portal. If everything is right, submit it yourself.")
        input("Press Enter here to close the browser when you are done... ")
        browser.close()


if __name__ == "__main__":
    main()
'''
