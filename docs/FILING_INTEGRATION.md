# Filing Integration — e-Jagriti

## What was established (inspection on 2026-10-30)
- e-Jagriti (https://e-jagriti.gov.in) is a React single-page app by the Department of Consumer
  Affairs. Public secondary reporting says it replaced e-Daakhil and related systems from 1 Jan 2025.
- Login uses mobile/email OTP and a CAPTCHA.
- Its upload component states "pdf only" and "File size should not exceed 25 MB".
- Its client-side validation limits District Commission complaints to ₹50 lakh paid consideration
  (consistent with the 2021 Jurisdiction Rules).
- No public, documented API for third-party complaint submission was found. Internal endpoints seen
  in the bundle are not an authorised integration and are **not used**.

## Supported modes (`integrations/ejagriti.py`)
| Mode | Status | What it does |
|---|---|---|
| Guided filing | Implemented and tested | Step list (open portal, sign in yourself, start complaint, copy data sheet, upload approved PDFs, pay fee yourself, submit yourself, record reference) + data sheet of confirmed facts + checklist state |
| Browser assist (Playwright) | Implemented, disabled by default, not exercised against the live portal | Opens a visible browser at the portal, detects login/OTP/CAPTCHA and hands control to the user; label-matching fill planner for approved values only; never clicks submit/pay/sign |
| API submission | Not implemented — blocked by absence of an authorised API | — |

## Approval gates
1. Each core document approved at its current version (hash-bound).
2. `POST /filing/authorize` — `SUBMIT_FILING` approval over the hash of the approved version set,
   expires in 7 days; optional `SHARE_EXTERNAL` approval for browser assist.
3. `POST /filing/start` checks both; browser assist also requires `ENABLE_BROWSER_ASSIST` and
   Playwright installed.

## Acknowledgement and status
`POST /filing/{id}/acknowledgement` records the reference the user received:
status `submitted_user_reported`, source `user_reported`, approval consumed, case status
`filed_user_reported`, and a `user_reported` case update. Only a legal reviewer/admin can mark a
filing `verified` (`POST /admin/filings/{id}/verify` with the official reference they checked);
that creates an `official_portal` update. No acknowledgement numbers are ever generated.

## Enabling browser assist (local only)
```bash
pip install -r requirements-optional.txt && python -m playwright install chromium
ENABLE_BROWSER_ASSIST=true BROWSER_ASSIST_HEADLESS=false
```
Run the backend on the user's own machine — a server-side browser is not visible to the citizen.
