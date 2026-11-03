"""Calendar export for case deadlines: an RFC 5545 iCalendar file and Google Calendar links.

Events are all-day on the deadline's date. Each description carries the deadline's basis, and
estimates and user-set dates say so, so a calendar entry never reads as more certain than it is.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from app.models import Deadline
from app.models.enums import DeadlineKind

PRODID = "-//NyayaSetu//Case deadlines//EN"


def _describe(d: Deadline) -> str:
    parts = [d.basis or ""]
    if d.kind == DeadlineKind.LEGAL_NOTICE:
        parts.append("This is the date you set in your own notice; it is not a period fixed by law.")
    elif d.is_estimate:
        parts.append("Estimate: check it against your own records and the Commission's orders.")
    parts.append("NyayaSetu gives legal information, not legal advice.")
    return " ".join(p for p in parts if p)


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets continue on the next line after a single space (RFC 5545 3.1)."""
    out: list[str] = []
    current = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode()) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0], *(" " + part for part in out[1:])]


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def build_ics(deadlines: Iterable[Deadline], case_reference: str, now: datetime) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_escape(f'NyayaSetu {case_reference}')}"]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    for d in deadlines:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{d.id}@nyayasetu",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{_ymd(d.due_date)}",
            f"DTEND;VALUE=DATE:{_ymd(d.due_date + timedelta(days=1))}",
            f"SUMMARY:{_escape(f'{d.title} ({case_reference})')}",
            f"DESCRIPTION:{_escape(_describe(d))}",
            "TRANSP:TRANSPARENT",
        ]
        if d.reminder_days_before:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(d.title)}",
                      f"TRIGGER:-P{d.reminder_days_before}D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"


def google_calendar_url(d: Deadline, case_reference: str) -> str:
    query = urlencode({
        "action": "TEMPLATE",
        "text": f"{d.title} ({case_reference})",
        "dates": f"{_ymd(d.due_date)}/{_ymd(d.due_date + timedelta(days=1))}",
        "details": _describe(d),
    })
    return f"https://calendar.google.com/calendar/render?{query}"
