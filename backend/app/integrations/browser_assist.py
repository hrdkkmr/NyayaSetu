"""Playwright browser assistance for official portals (local deployments only).

Design constraints (see docs/FILING_INTEGRATION.md):
  * Opens a *visible* browser for the user; never headless form submission.
  * Detects login/OTP/CAPTCHA screens and hands control to the user.
  * Fills only fields whose visible label clearly matches an approved data-sheet entry, and
    only after a SHARE_EXTERNAL approval exists. It reports every field it filled.
  * Never clicks submit/pay/sign controls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.integrations.ejagriti import playwright_installed

logger = logging.getLogger(__name__)

_FORBIDDEN_CONTROLS = re.compile(r"submit|pay|e-?sign|final|confirm and file|proceed to pay", re.I)
_AUTH_MARKERS = re.compile(r"captcha|otp|one time password|verify mobile|login|sign in", re.I)

LABEL_MATCHERS: dict[str, re.Pattern[str]] = {
    "complainant_name": re.compile(r"^(complainant('s)?\s+)?(full\s+)?name", re.I),
    "complainant_address": re.compile(r"complainant.*address|^address", re.I),
    "seller_name": re.compile(r"(opposite\s+party|respondent).*name", re.I),
    "seller_address": re.compile(r"(opposite\s+party|respondent).*address", re.I),
    "amount_paid": re.compile(r"(paid\s+)?consideration|amount\s+paid", re.I),
}


@dataclass
class AssistReport:
    url: str | None = None
    title: str | None = None
    state: str = "not_started"
    needs_user_action: list[str] = field(default_factory=list)
    filled: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class BrowserAssistUnavailable(RuntimeError):
    pass


async def open_portal(url: str) -> AssistReport:
    """Open the portal in a visible browser and describe what the user needs to do."""
    if not (get_settings().enable_browser_assist and playwright_installed()):
        raise BrowserAssistUnavailable("Browser assistance is not enabled on this server.")
    from playwright.async_api import async_playwright

    report = AssistReport()
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=get_settings().browser_assist_headless)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        report.url = page.url
        report.title = await page.title()
        body = (await page.inner_text("body"))[:20000]
        if _AUTH_MARKERS.search(body):
            report.state = "awaiting_user_login"
            report.needs_user_action.append("Sign in with your own OTP and CAPTCHA in the opened browser window.")
        else:
            report.state = "portal_open"
        # The browser stays open for the user; it is not closed here intentionally.
    except Exception as exc:  # noqa: BLE001
        report.state = "error"
        report.error = type(exc).__name__
        await pw.stop()
    return report


async def describe_form_fields(page: Any) -> list[dict[str, str]]:
    """Return visible input fields with their labels (used to decide what can be safely filled)."""
    return await page.evaluate(
        """() => Array.from(document.querySelectorAll('input, textarea, select'))
            .filter(el => el.offsetParent !== null && !['hidden','password','file'].includes(el.type))
            .map(el => {
              const id = el.id; let label = '';
              if (id) { const l = document.querySelector(`label[for="${id}"]`); if (l) label = l.innerText; }
              if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '';
              return {label: label.trim().slice(0, 120), name: el.name || id || ''};
            })"""
    )


def plan_fills(fields: list[dict[str, str]], approved: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    """Match visible fields to approved values. Ambiguous or unmatched fields are left for the user."""
    plan, skipped = [], []
    for item in fields:
        label = item.get("label", "")
        if _FORBIDDEN_CONTROLS.search(label) or _AUTH_MARKERS.search(label):
            skipped.append(label)
            continue
        matches = [key for key, rx in LABEL_MATCHERS.items() if rx.search(label) and approved.get(key)]
        if len(matches) == 1:
            plan.append({"label": label, "name": item.get("name", ""), "key": matches[0], "value": approved[matches[0]]})
        else:
            skipped.append(label)
    return plan, skipped
