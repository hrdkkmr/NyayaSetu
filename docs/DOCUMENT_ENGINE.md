# Document Engine

## Uploads (`services/document_processing.py`, `api/documents.py`)
1. **Consent gate:** `consent_document_storage` must be on.
2. **Validation:** type by magic bytes (PDF, DOCX, JPEG, PNG), ≤ `MAX_UPLOAD_MB`, ≤ 50 per case;
   filename sanitised.
3. **Security checks:** reject PDFs with `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile`,
   `/RichMedia`; DOCX with macros (`vbaProject`, `.bin`) or zip-bomb characteristics; images that
   fail decoding (Pillow pixel limit). Encrypted PDFs flagged. (No antivirus engine — see limitations.)
4. **Storage:** AES-256-GCM encrypted, random key path, local or S3 (SSE also requested).
5. **Processing job:** text extraction (pypdf, python-docx, Tesseract OCR if installed; otherwise
   `needs_ocr`), classification (invoice, order confirmation, warranty, communication, payment
   proof, other), field extraction (amount, date, order id, invoice no., GSTIN, seller, emails),
   prompt-injection flags. With `consent_external_ai`, `agents/evidence.py` also asks the LLM for
   seller, brand, product, invoice date/number, amount, GSTIN and a defect summary over the
   wrapped (untrusted) text; a field is kept only if its quote appears in the document and its
   value passes format checks. Pattern matches take precedence; AI fields are tagged `method: ai`
   and shown "read by AI — check it".
6. **Human review:** the user accepts fields (`accept-fields`) → `document_extracted` facts; adds
   documents to the evidence list (auto `Annexure A-n`).

## Generated documents (`documents/templates.py`, template v1.0)
| doc_type | Contents |
|---|---|
| `consumer_complaint` | Forum heading (from grounded pecuniary rule), parties, s.35 title, numbered facts (user's own words + confirmed facts), defect/deficiency paragraph for the user to complete, jurisdiction (2021 Rules + s.34(2)), limitation (s.69; condonation wording if expired), fee (2023 table), prayer mapped to s.39(1) reliefs, signature, verification, affidavit note |
| `memo_of_parties` | Complainant / opposite party table |
| `list_of_dates` | Chronology from confirmed dates and dated evidence |
| `evidence_index` | Annexure list |
| `filing_checklist` | Forum, fee, time limit, approvals, portal upload rules, OTP note, signature/affidavit, acknowledgement |

Rules: only user-stated/confirmed facts are used; unknowns render as `[●]`; every block records
`sources.facts` and `sources.refs`; each document starts with a draft notice. The LLM is not used
to write documents. Formatting requirements of a particular Commission are not asserted — the draft
notice tells the user to confirm the current format on the portal.

## Versioning
A new version is created only when content changes (sha256). Users edit `editable` blocks only
(`PUT /drafts/{id}`), creating `created_by=user` versions with `edited_by_user` markers.

## Verification (`agents/verification.py`)
Blockers: placeholders, conflicting values across sources (amount, purchase date, seller), future
purchase date, problem date before purchase, non-positive amount, possible non-consumer, amount
mismatch. Warnings: unconfirmed inferences, limitation expired, ungrounded rules, no evidence,
paragraph needing the user's description.

## Approval
`POST /approve` requires the current version number and its sha256, an accepted statement, no
blockers, and acknowledged warnings. Approval rows store the hash; editing returns the document to
draft. Filing authorisation is bound to the hash of the set of approved version ids.

## Export
PDF (ReportLab, Times/Helvetica; "Rs." instead of ₹; footer with version and DRAFT marker) and DOCX
(python-docx). Rendered on demand (deterministic), not stored.
