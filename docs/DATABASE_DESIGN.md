# Database Design

PostgreSQL 16 + pgvector in production; SQLite for local development and tests. Models:
`backend/app/models/*.py`. Migration: `backend/alembic/versions/0001_initial_schema.py`.

Portable types (`app/db/types.py`): `GUID` (UUID / CHAR36), `JSONType` (JSONB / JSON),
`EmbeddingVector(n)` (`vector(n)` / JSON text). All timestamps are timezone-aware UTC.
Enumerations are stored as strings (`app/models/enums.py`) to keep migrations simple.

## Tables (30)
| Group | Table | Purpose / key fields |
|---|---|---|
| Identity | `users` | email (unique), full_name, phone, password_hash (argon2), role, deletion_requested_at |
| | `user_preferences` | language, text_scale, contrast/motion, voice settings, **consent flags** + consents_updated_at |
| | `auth_sessions` | refresh_token_hash (unique, HMAC), ip_hash, expires/revoked |
| | `password_reset_tokens` | token_hash, expires_at, used_at |
| Cases | `cases` | user_id, reference (unique), category, status, incident fields, `analysis` JSON (rule outcomes, routes, missing info), archived_at |
| | `case_parties` | role, name, address, provenance (reserved for multi-party cases; current parties derive from facts) |
| | `case_facts` | key, value, **provenance** (user_stated / user_confirmed / document_extracted / ai_inference), status (active/superseded/rejected), source_type/id, excerpt, confidence |
| | `case_updates` | **source** (internal / user_reported / official_portal), verified, source_reference |
| | `deadlines` | due_date, kind, status, source, basis, citation_chunk_id, is_estimate |
| Conversation | `conversations` | case_id, store_transcript |
| | `conversation_messages` | role, content (placeholder if not consented), modality, redacted, meta (cards) |
| | `voice_sessions` | providers, status, resume_token_hash, stats (latencies, interruptions), audio_stored |
| Documents | `uploaded_documents` | storage_key (never exposed), sha256, status, document_class, security_flags |
| | `document_extractions` | method, text, fields (proposals), injection_flags, reviewed_at |
| | `evidence_items` | label (Annexure A-n), title, date, document_id |
| | `generated_documents` | doc_type (unique per case), status, template id/version, current_version |
| | `document_versions` | content JSON, content_sha256, created_by, source_trace, validation |
| Legal | `legal_sources` | publisher (Gazette, court site) |
| | `legal_documents` | key, title, source_url, publication/effective dates + note, identifier, version_label, amends, sha256, retrieved_at, verification_status |
| | `legal_chunks` | section_ref, chapter, text, search_text, embedding (vector 384), embedding_model |
| | `legal_citations` | case_id, chunk_id, topic, score, explanation + method |
| Workflow | `workflow_instances` | case_id (unique), status, current_node, state JSON (durable keys), **revision** (optimistic lock), last_error |
| | `workflow_steps` | step_key, titles (en/hi), status, owner, due_date, source_refs |
| | `agent_executions` | agent, status, provider, model, attempt, latency, summary, error |
| | `approvals` | action, status, target, document_version_ids, **content_sha256**, statement, expires_at, consumed_at, ip_hash |
| | `filing_records` | portal, mode, status, approval_id, acknowledgement_number + source, verified_at, checklist_state, portal_state |
| | `background_jobs` | kind, status, payload, attempts, result, error |
| System | `notifications` | user_id, kind, title, read_at, dedupe_key (unique) |
| | `audit_logs` | actor, action, resource, case_id, outcome, scrubbed meta |
| | `integration_configs` | non-secret settings + last health status |

## Indexes and constraints
Foreign keys with `ON DELETE CASCADE` from user → cases → dependent rows (account deletion
removes all case data). Composite indexes: cases(user_id,status), case_facts(case_id,key),
messages(conversation_id,created_at), deadlines(due_date,status), notifications(user_id,read_at),
legal_chunks(document_id,ordinal). Postgres-only: HNSW `vector_cosine_ops` on
`legal_chunks.embedding`, GIN full-text on `legal_chunks.text`.

## Tenant isolation
Application layer: every case-scoped query is filtered by the owning user
(`core/deps.get_owned_case`); non-owners get 404. Admin endpoints expose operational metadata, not
transcripts or document text. (Postgres row-level security is a planned hardening step.)

## Sensitive data
Uploaded file bytes are stored encrypted in object storage, not in the DB. Extracted text is
stored in `document_extractions.text` for the owner's review; it is never logged or placed in
audit metadata.
