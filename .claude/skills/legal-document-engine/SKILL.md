---
name: legal-document-engine
description: Use when changing uploads, extraction, generated document templates, verification checks, versioning, PDF/DOCX rendering or approval binding.
---

# Legal document engine

## Objective
Deterministic, traceable drafts built only from confirmed facts and grounded rules; safe handling
of untrusted uploads; approvals bound to exact content.

## When to use
`app/documents/*`, `services/documents.py`, `services/document_processing.py`,
`agents/verification.py`, `api/documents.py`, `api/drafts.py`.

## Templates (`documents/templates.py`)
- Content is `{"title","doc_type","blocks":[...]}`; each block has `id`, `type`, `editable`,
  `sources: {facts:[fact ids], refs:["doc_key:Section N"]}`.
- Use `ctx.fact(key)` (ignores AI inferences). Unknown → `PLACEHOLDER` (`[●]`), which blocks approval.
- The LLM never writes clauses, headings or formats. Wording that cites law must name a provision
  that is grounded.
- Bump `TEMPLATE_VERSION` when output changes.

## Versioning & approval
- `generate_documents` creates a version only when the content hash changes.
- `edit_document` edits only `editable` blocks and creates a user version (re-verified).
- Approval requires the current `version_number` + `content_sha256`, no blockers, and acknowledged
  warnings. Editing after approval returns the doc to draft.

## Uploads
- Validate by magic bytes; reject active PDFs (`/JavaScript`, `/Launch`, embedded files), macro
  DOCX, zip bombs, undecodable images. Sanitize filenames. Encrypt before storage.
- Extraction fields are proposals; only `accept-fields` turns them into `document_extracted` facts.
- Injection phrases are flagged (`contains_ai_instructions`) and shown to the user.

## Security considerations
Never return `storage_key`. Downloads go through ownership checks, `Cache-Control: no-store`, audit.

## Testing expectations
`tests/test_documents_and_filing.py`: malicious uploads, consent gate, extraction from a generated
invoice PDF, injection flag, conflict detection blocking approval, edit → new version, stale-version
approval rejected, PDF/DOCX render.

## Common failure scenarios
- ReportLab built-in fonts lack `₹` and Indic shaping → PDF uses "Rs." and English text; Hindi
  explanations stay in the app (see KNOWN_LIMITATIONS).
- Forgetting to re-verify after an edit.
- Placeholders silently removed by an edit — the verifier must still catch missing facts.
