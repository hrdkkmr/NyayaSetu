# Product Requirements — NyayaSetu

## Vision
*Justice should be accessible, not complicated.* A citizen opens NyayaSetu, speaks naturally in
Hindi or English about a legal problem, gets a trustworthy explanation of their options grounded
in official sources, prepares the necessary paperwork, reviews and authorises each step, and
follows their case — without needing to know which law, authority, portal or form applies.

NyayaSetu is an AI legal-information and workflow assistant. It is **not** a lawyer, law firm or
court, never guarantees outcomes, and never files, signs, pays or shares anything without explicit
user approval.

## Users
- Citizens with little legal knowledge, including rural and elderly users.
- Hindi and English speakers; people who prefer speaking to typing.
- First-time users of government portals.
- Internal: legal reviewers (verify filings and sources) and administrators (operations).

## Scope of this release
| Area | In scope |
|---|---|
| Domain | Consumer disputes end to end (Consumer Protection Act, 2019 → e-Jagriti). Other matters are recognised and referred (police/112, cyber/1930, legal aid/NALSA 15100). |
| Channels | Responsive web app; voice + text in one conversation. APIs are client-agnostic for a future Android app (bearer tokens supported). |
| Languages | Hindi and English UI, voice and replies. Architecture allows more languages. |

## Core user journey
1. Register (consent choices for transcripts, documents, external AI).
2. Describe the problem by voice or text.
3. Intake asks one question at a time; inferred facts are confirmed by the user.
4. Classification decides whether the consumer route applies (or refers elsewhere).
5. Research retrieves official provisions; deterministic rules give forum, fee, time limit,
   where to file, consumer status, possible reliefs — each with a citation.
6. Workflow plan and computed deadline (marked as an estimate).
7. Upload proof → extraction proposals → user accepts fields → evidence index.
8. Generate drafts (complaint, memo of parties, list of dates, evidence index, filing checklist),
   review, edit (new versions), approve each version.
9. Authorise filing preparation → guided e-Jagriti filing → user records acknowledgement.
10. Track user-reported and reviewer-verified updates, deadlines and reminders.

## Requirements (summary)
- **Trust:** every legal statement cites an ingested official source; uncertainty is stated;
  unknown facts are never invented; provenance is visible.
- **Safety:** approval gates for documents and filing; no fake integrations or statuses;
  uploaded documents can never instruct agents.
- **Accessibility:** WCAG-minded UI, large touch targets, keyboard and screen-reader support,
  text scaling, high contrast, reduced motion, voice-first with text fallback.
- **Privacy:** consent-gated storage and AI processing, encryption, export and deletion.
- **Operations:** admin console for integration health, sources, jobs, agent runs, audit.

## Out of scope (this release)
Native Android app; automated portal submission; payments; e-signatures; legal domains other than
consumer disputes beyond referral; lawyer marketplace.

## Success measures (to instrument)
Intake completion rate; time to first draft; share of facts confirmed vs inferred; voice turn
latency; filings recorded; referral rate; user-reported clarity.
