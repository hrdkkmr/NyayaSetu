# Case Tracking

## Status sources (always labelled)
| Source | Who creates it | Shown as |
|---|---|---|
| `internal` | NyayaSetu workflow (case status, plan steps) | Workflow status |
| `user_reported` | The citizen (filing reference, hearing dates, notices, orders) | "Reported by you" |
| `official_portal` | A legal reviewer/admin after checking the official portal, with the reference checked | "Official portal", verified |

NyayaSetu does not scrape or poll e-Jagriti case status (CAPTCHA-protected; no authorised API),
so official status is only shown after human verification.

## Case statuses
intake → research → planning → review → awaiting_approval → ready_to_file →
filed_user_reported → filed_verified; plus needs_professional_review, closed, archived.

## Timeline & history
- Incident timeline from confirmed dates; case updates feed; workflow steps with owner and status;
  activity log from `audit_logs` (actions only, no content).
- Document version history per generated document; approvals list per case.

## Deadlines
- Computed: limitation (s.69, two years from the date the problem arose) — always marked
  *estimate*, with basis and citation; becomes `missed` if passed.
- Computed: admissibility target (s.36(2), second proviso: admissibility "shall ordinarily be decided
  within twenty-one days" of filing), created when the citizen reports the submission date; marked
  *estimate* and described as the Commission's target, not a guaranteed date. Withheld if s.36 is
  not in the knowledge base.
- User-reported: hearings (from updates), responses, custom reminders, and the reply deadline the
  citizen set in their own legal notice (`legal_notice`), labelled "not a period fixed by law"; the
  Act prescribes no legal-notice period, so none is computed.
- Calendar: `GET /cases/{id}/deadlines.ics` (RFC 5545 all-day events with the basis in the
  description and a reminder alarm) and a Google Calendar link per deadline.
- Reminders: daily job creates de-duplicated notifications in the 60-day window (at the configured
  lead time, 7 days and 1 day before) and emails them when SMTP is configured.

## Archival
`POST /cases/{id}/archive` hides a case from the dashboard; restore with `archived=false`.
Account deletion removes all cases.

## Appeals
The plan's tracking step notes the 45-day appeal period (s.41); the appeal itself is out of scope
for this release.
