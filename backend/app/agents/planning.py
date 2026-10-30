"""Workflow planning agent: turns grounded outcomes into an ordered action plan.

Tool access: writes workflow_steps and computed deadlines for the case only.
Optional steps are labelled optional; nothing is presented as legally mandatory
unless it is tied to a cited provision.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Deadline, WorkflowStep
from app.models.enums import DeadlineKind, DeadlineStatus, StepStatus


def build_plan(outcomes: dict[str, Any], slots: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    forum = (outcomes.get("pecuniary_forum") or {}).get("value")
    forum_en = {"district": "District Commission", "state": "State Commission",
                "national": "National Commission"}.get(forum or "", "the appropriate Consumer Commission")
    forum_hi = {"district": "ज़िला आयोग", "state": "राज्य आयोग", "national": "राष्ट्रीय आयोग"}.get(
        forum or "", "सही उपभोक्ता आयोग")
    limitation = (outcomes.get("limitation") or {}).get("value") or {}
    deadline = limitation.get("deadline")
    evidence = (slots.get("evidence") or {}).get("value") or ""
    have_invoice = any(w in evidence for w in ("invoice", "bill", "बिल"))

    steps: list[dict[str, Any]] = [
        {
            "step_key": "describe_problem", "owner": "user",
            "title": "Describe the problem and answer a few questions",
            "title_hi": "समस्या बताइए और कुछ सवालों के जवाब दीजिए",
            "description": "NyayaSetu needs the core facts before preparing documents.",
            "refs": [],
        },
        {
            "step_key": "collect_evidence", "owner": "user",
            "title": "Collect and upload your proof",
            "title_hi": "अपने सबूत इकट्ठा करें और अपलोड करें",
            "description": ("Upload the bill/invoice, order confirmation, photos and messages with the seller."
                            + ("" if have_invoice else " The bill or invoice is especially important.")),
            "refs": ["cpa_2019:Section 2(7)"],
        },
        {
            "step_key": "try_resolution", "owner": "user",
            "title": "Optional: try to resolve it with the seller or the National Consumer Helpline (1915)",
            "title_hi": "वैकल्पिक: विक्रेता या राष्ट्रीय उपभोक्ता हेल्पलाइन (1915) से सुलझाने की कोशिश करें",
            "description": "Not a legal requirement under the Act, but it can resolve the issue faster and "
                           "creates a written record.",
            "refs": [],
        },
        {
            "step_key": "prepare_documents", "owner": "system",
            "title": "Prepare the complaint and supporting documents",
            "title_hi": "शिकायत और सहायक दस्तावेज़ तैयार करें",
            "description": f"Draft complaint for the {forum_en}, evidence index, list of dates and memo of parties.",
            "refs": ["cpa_2019:Section 35"],
        },
        {
            "step_key": "review_approve", "owner": "user",
            "title": "Review, correct and approve the drafts",
            "title_hi": "ड्राफ़्ट जाँचें, सुधारें और स्वीकृत करें",
            "description": "Nothing is filed or shared without your explicit approval.",
            "refs": [],
        },
        {
            "step_key": "file_complaint", "owner": "user",
            "title": f"File the complaint with the {forum_en} on e-Jagriti",
            "title_hi": f"ई-जागृति पर {forum_hi} में शिकायत दर्ज करें",
            "description": ("Guided filing on the official portal. You log in yourself; NyayaSetu never "
                            "bypasses OTP or CAPTCHA."
                            + (f" File before {deadline}." if deadline else "")),
            "refs": ["cpa_2019:Section 35", "cpa_2019:Section 69"],
            "due_date": deadline,
        },
        {
            "step_key": "record_acknowledgement", "owner": "user",
            "title": "Record the filing number the portal gives you",
            "title_hi": "पोर्टल से मिला फाइलिंग नंबर दर्ज करें",
            "description": "Enter the reference/diary number and upload the acknowledgement so it can be tracked.",
            "refs": [],
        },
        {
            "step_key": "track_case", "owner": "user",
            "title": "Track hearings and respond to notices",
            "title_hi": "सुनवाई की तारीखें देखें और नोटिस का जवाब दें",
            "description": "Check the official portal for status. Appeals against a District Commission order "
                           "must be filed within 45 days.",
            "refs": ["cpa_2019:Section 41"],
        },
    ]
    order = ["describe_problem", "collect_evidence", "try_resolution", "prepare_documents",
             "review_approve", "file_complaint", "record_acknowledgement", "track_case"]
    progress = {
        "intake": 0, "analysis": 1, "drafting": 3, "review": 4, "awaiting_approval": 4,
        "filing": 5, "tracking": 7, "referred": 0,
    }.get(phase, 0)
    for index, step in enumerate(steps):
        step["order_index"] = order.index(step["step_key"])
        if index < progress:
            step["status"] = StepStatus.DONE.value
        elif index == progress:
            step["status"] = StepStatus.IN_PROGRESS.value
        else:
            step["status"] = StepStatus.PENDING.value
        if step["step_key"] == "try_resolution" and progress > index:
            step["status"] = StepStatus.SKIPPED.value if progress > 2 else step["status"]
    return steps


async def persist_plan(db: AsyncSession, workflow_id: uuid.UUID, steps: list[dict[str, Any]]) -> None:
    existing = {s.step_key: s for s in (await db.scalars(
        select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id))).all()}
    keep = set()
    for step in steps:
        row = existing.get(step["step_key"])
        if row is None:
            row = WorkflowStep(workflow_id=workflow_id, step_key=step["step_key"], order_index=step["order_index"])
            db.add(row)
        # Never move a step the user marked done back to pending.
        if not (row.status == StepStatus.DONE and step["status"] != StepStatus.DONE):
            row.status = step["status"]
        row.title = step["title"]
        row.title_hi = step.get("title_hi")
        row.description = step.get("description")
        row.owner = step["owner"]
        row.order_index = step["order_index"]
        row.source_refs = step.get("refs", [])
        row.due_date = date.fromisoformat(step["due_date"]) if step.get("due_date") else None
        keep.add(step["step_key"])
    for key, row in existing.items():
        if key not in keep:
            await db.delete(row)


async def sync_limitation_deadline(db: AsyncSession, case_id: uuid.UUID, outcomes: dict[str, Any]) -> None:
    limitation = outcomes.get("limitation")
    existing = await db.scalar(
        select(Deadline).where(Deadline.case_id == case_id, Deadline.kind == DeadlineKind.LIMITATION,
                               Deadline.source == "computed")
    )
    if not limitation or not limitation.get("grounded"):
        if existing is not None and existing.status == DeadlineStatus.OPEN:
            await db.execute(delete(Deadline).where(Deadline.id == existing.id))
        return
    value = limitation["value"]
    basis = limitation["basis"][0] if limitation.get("basis") else {}
    due = date.fromisoformat(value["deadline"])
    if existing is None:
        existing = Deadline(case_id=case_id, kind=DeadlineKind.LIMITATION, source="computed",
                            title="Estimated last date to file the consumer complaint")
        db.add(existing)
    existing.due_date = due
    existing.is_estimate = True
    existing.basis = (
        f"{basis.get('section_ref', 'Section 69')} of {basis.get('document_title') or 'the Consumer Protection Act, 2019'}: "
        "two years from the date the cause of action arose. Estimated from the date you gave."
    )
    existing.citation_chunk_id = uuid.UUID(basis["chunk_id"]) if basis.get("chunk_id") else None
    existing.reminder_days_before = 30
    if value["status"] == "expired":
        existing.status = DeadlineStatus.MISSED
