---
name: accessibility-i18n
description: Use when adding UI text, pages or components, changing styles, or adding a language.
---

# Accessibility & internationalisation

## Objective
A calm public-service UI usable by first-time smartphone users, screen-reader users and Hindi or
English speakers, with voice first and text always available.

## When to use
Any change under `frontend/src`, and backend reply text (`responder.py`, `slots.py`, `rules.py`).

## i18n rules
- No hardcoded UI strings. Add keys to `src/lib/i18n/en.ts` and `hi.ts` (Hindi is typed against
  English; the unit test checks key parity). Use `t("section.key", {var})`.
- Backend user-facing text has `_en`/`_hi` pairs; the assistant's Hindi first-person voice is
  consistently feminine (matching the default voices).
- Legal text stays in the authoritative language; translations/explanations are labelled as aids.
- Adding a language: new dictionary file, `Lang` union, `LANG_CODES` in `integrations/speech.py`,
  glossary entries in `legal/text.py`, slot questions, and voice BCP-47 codes.

## Accessibility rules
- Semantic landmarks (`header`, `nav`, `main#main`, skip link), headings in order.
- Every control has an accessible name; icon-only buttons need `aria-label`; decorative icons `aria-hidden`.
- Touch targets ≥ 44px (`min-h-11`); visible focus ring (global `:focus-visible`).
- Status changes use `aria-live` (chat log, voice state). Errors use `role="alert"`.
- Colour contrast AA with the tokens in `globals.css`; never convey status by colour alone (badges have text).
- Respect `text_scale`, `high_contrast`, `reduce_motion` preferences (applied on `<html>`).

## Security considerations
Never render user/LLM/document text as HTML. React escaping only; no `dangerouslySetInnerHTML`.

## Testing expectations
Vitest key-parity test; Playwright journeys on desktop and mobile; manual keyboard-only and
screen-reader pass on new pages.

## Common failure scenarios
- Text overflow in Hindi (longer strings) — use flex-wrap and avoid fixed widths.
- Fonts: Noto Sans Devanagari must stay loaded for Hindi.
