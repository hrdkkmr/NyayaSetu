# Legal Safety

NyayaSetu provides legal information and paperwork assistance. It is not a lawyer, law firm or
court. These rules are enforced in code and must be preserved.

## Principles
1. **Grounding.** Legal statements come from ingested official documents or deterministic rules
   that cite a provision and are verified present (`rules.ground`). No law from model memory.
2. **Honesty about uncertainty.** Retrieval confidence is computed; low confidence → no answer,
   referral to free legal aid (NALSA 15100). Dates computed from user input are labelled estimates.
3. **Separation of fact types.** User-stated, user-confirmed, document-extracted and AI-inferred
   facts are stored and displayed separately; inferences never enter documents unconfirmed.
4. **No guarantees, no impersonation.** Replies never promise outcomes or claim to be a lawyer or
   human; LLM rephrasings that do are rejected. Every analysis carries a disclaimer.
5. **Human control.** Documents need versioned approval; filing needs separate authorisation;
   NyayaSetu never submits, signs, pays, sends notices or shares data on its own.
6. **No fabricated records.** No fake acknowledgement numbers, hearing dates or case statuses;
   official status only after reviewer verification.
7. **Right route.** Non-consumer matters (criminal, cyber fraud, family, employment, property) and
   possible exclusions (commercial purpose, free service, personal-service contracts) are flagged for
   professional review with official help resources.
8. **Safety.** Danger or self-harm language triggers emergency resources (112, Tele-MANAS 14416)
   before anything else.

## Help resources shown (verified 2026-10-30)
112 Emergency · 15100 NALSA legal aid · 1915 National Consumer Helpline · 1930 / cybercrime.gov.in ·
14416 Tele-MANAS · e-jagriti.gov.in. Each is shown with its official URL.

## Draft documents
Every generated document begins with a draft notice, uses only confirmed facts, shows `[●]` for
missing details, and tells the user to confirm the current format with the Commission/portal and
whether an affidavit is required.

## Review responsibilities
Legal reviewers: verify source currency (Admin → Legal sources), verify filings against the portal,
review cases flagged `needs_professional_review`. Any new legal rule or template requires review by a
qualified person before release.
