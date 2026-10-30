# Legal Knowledge & Retrieval Design

## Sources (as of 2026-10-30)
| Key | Document | Publisher / URL | Notes |
|---|---|---|---|
| `cpa_2019` | Consumer Protection Act, 2019 (Act No. 35 of 2019) | Gazette of India — egazette.gov.in/WriteReadData/2019/210422.pdf | As enacted, 9 Aug 2019. 188 chunks covering all 107 sections. Per-section commencement not ingested. |
| `cp_jurisdiction_rules_2021` | CP (Jurisdiction of the District, State and National Commission) Rules, 2021 — G.S.R. 912(E) | Copy hosted by the High Court of Tripura website | Replaces the pecuniary limits printed in ss. 34, 47, 58 (₹50 lakh / ₹2 crore). |
| `cp_cdrc_amendment_rules_2023` | CDRC (Amendment) Rules, 2023 — G.S.R. 606(E) | Gazette of India — egazette.gov.in/WriteReadData/2023/248158.pdf | Substitutes the fee table in rule 7(2). Principal 2020 Rules not yet ingested. |

The manifest (`backend/data/legal_sources/manifest.yaml`) is the single register; every value was
read from the document itself. Snapshots and their sha256 are stored in the repo.

## Pipeline (`app/legal`)
1. **Acquire:** snapshot (default) or live fetch (`LEGAL_FETCH_LIVE=true`); if live bytes differ
   from the snapshot the document is marked `stale` for review.
2. **Extract:** pypdf text. Scanned PDFs are reported as needing OCR (not silently skipped).
3. **Normalise:** remove page headers, marginal-note runs and Devanagari residue from bilingual
   Gazettes; re-join wrapped lines.
4. **Chunk:** by section/rule with chapter tracking; definitions in s.2 are chunked per term
   (`Section 2(7)`); long sections split at sub-section boundaries (≤1,800 chars).
5. **Embed:** `HashingEmbedder` (offline, deterministic lexical features, 384-d) or an
   OpenAI-compatible embeddings endpoint.
6. **Store:** `legal_documents`, `legal_chunks` (pgvector column + HNSW/GIN on Postgres).

## Retrieval (`legal/retrieval.py`)
Metadata filters (domain, jurisdiction, document) → candidates (pgvector top-60 + keyword matches on
Postgres; all filtered chunks on SQLite) → BM25 + cosine → reciprocal-rank fusion → rerank
(explicit section/rule mention, defined-term match, "what is X" focus, preamble penalty) →
amendment notices → confidence (query-term coverage + BM25 strength: high / medium / low / none).

Hindi and everyday phrasing are handled by query expansion with a reviewed glossary and intent
patterns (`legal/text.py`). The expansion is reported to the user; it is never presented as a
translation of law.

## Grounded answers
- Deterministic rules (`domains/consumer/rules.py`) encode specific provisions and are passed
  through `ground()`; if a provision is not in the DB the outcome is `grounded=false` and shown with
  a warning.
- Citations store topic, score and explanation; explanations are reviewed templates, or
  LLM-generated **only from the provision text** (labelled), or a source excerpt.
- Low-confidence retrieval → "I couldn't find reliable information… I won't guess" + legal aid.
- Every answer carries the disclaimer that it is general information, not a lawyer's advice.

## Version awareness
Each document carries publication date, effective-date note, version label, retrieved_at, sha256
and verification status (`fetched_official`, `verified_by_reviewer`, `stale`, `unverified`).
Reviewers set verification in Admin. The system never claims a document is current.

## Known gaps
No consolidated (amended) text of the Act; per-section commencement notifications, CDRC Rules
2020 (principal), Consumer Protection (E-Commerce) Rules 2020, state rules and case law are not
ingested; India Code handle pages timed out during research. Semantic quality of the default
hashing embedder is lexical — configure an embedding API for production.
