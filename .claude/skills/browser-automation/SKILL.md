---
name: browser-automation
description: Use when working on e-Jagriti filing assistance, Playwright browser assist, guided filing steps, or any interaction with an official portal.
---

# Browser automation & filing

## Objective
Help citizens file on official portals without ever bypassing security controls or pretending a
filing happened.

## When to use
`integrations/ejagriti.py`, `integrations/browser_assist.py`, `api/drafts.py` (filing routes),
`components/case/filing-tab.tsx`.

## Facts about e-Jagriti (as observed 2026-10-30; re-verify before relying on them)
- SPA at https://e-jagriti.gov.in; OTP + CAPTCHA login; PDF-only uploads with a stated 25 MB limit;
  client-side ₹50 lakh check for District Commission complaints.
- No public, documented API for third-party submission was found → `api_submission=False`.

## Rules (hard)
- Never automate login, OTP or CAPTCHA. Never call private portal endpoints seen in its JS bundle.
- Never click submit / pay / e-sign. `browser_assist.plan_fills` skips such controls.
- Browser assist requires `ENABLE_BROWSER_ASSIST=true`, a visible browser on a machine the user
  controls, a valid `SUBMIT_FILING` and `SHARE_EXTERNAL` approval over current approved versions.
- Acknowledgements are `user_reported` until a reviewer verifies them on the portal
  (`/admin/filings/{id}/verify`, records the official reference).
- Guided steps describe intent, not exact button labels (portals change).

## Security considerations
Only approved data-sheet values may be typed into a portal. Log fills to the filing record and audit.

## Testing expectations
Filing flow tests: blocked before approvals, authorisation bound to version bundle hash, browser
assist returns 503 when disabled, acknowledgement recorded as user_reported, reviewer verification.

## Common failure scenarios
- Portal markup changes → label matching skips fields (acceptable; user fills them).
- Running browser assist on a server → the user cannot see the browser. Keep it local-only.
