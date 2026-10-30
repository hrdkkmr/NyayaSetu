// Shapes returned by the NyayaSetu API (see docs/API_SPECIFICATION.md).

export type Lang = "en" | "hi";

export interface Preferences {
  language: Lang;
  text_scale: number;
  high_contrast: boolean;
  reduce_motion: boolean;
  voice_provider: "browser" | "sarvam";
  voice_speaker: string | null;
  speech_rate: number;
  autoplay_voice: boolean;
  consent_store_transcripts: boolean;
  consent_store_audio: boolean;
  consent_external_ai: boolean;
  consent_document_storage: boolean;
  consents_updated_at: string | null;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: "citizen" | "legal_reviewer" | "admin";
  created_at: string;
  deletion_requested_at: string | null;
  preferences: Preferences;
}

export interface CaseSummary {
  id: string;
  reference: string;
  title: string;
  category: string | null;
  status: string;
  language: Lang;
  incident_date: string | null;
  financial_amount: string | null;
  location_district: string | null;
  location_state: string | null;
  requires_human_review: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Fact {
  id: string;
  key: string;
  value: string;
  value_type: string;
  provenance: "user_confirmed" | "user_stated" | "document_extracted" | "ai_inference";
  status: string;
  source_type: string | null;
  source_id: string | null;
  excerpt: string | null;
  confidence: number | null;
  confirmed_at: string | null;
  created_at: string;
}

export interface Basis {
  document_key: string;
  section_ref: string;
  summary: string;
  chunk_id: string | null;
  source_url: string | null;
  document_title: string | null;
  verification_status: string | null;
}

export interface RuleOutcome {
  key: string;
  value: unknown;
  explanation_en: string;
  explanation_hi: string;
  basis: Basis[];
  grounded: boolean;
  caveats: string[];
}

export interface Step {
  key: string;
  title: string;
  title_hi: string | null;
  description: string | null;
  status: "pending" | "in_progress" | "done" | "blocked" | "skipped";
  owner: "user" | "system";
  order: number;
  due_date: string | null;
  refs: string[];
}

export interface Deadline {
  id: string;
  title: string;
  due_date: string;
  kind: string;
  status: string;
  source: string;
  basis: string | null;
  is_estimate: boolean;
  case_id?: string;
  case_title?: string;
}

export interface Card {
  type: string;
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "notice";
  content: string;
  language: Lang | null;
  modality: "text" | "voice";
  redacted: boolean;
  cards: Card[];
  created_at: string;
}

export interface TurnResult {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  phase: string;
  asked_slot: string | null;
  language: Lang;
  case: CaseSummary;
  errors: { agent: string; error: string }[];
}

export interface CaseDetail {
  case: CaseSummary;
  summary: string | null;
  facts: Fact[];
  fact_keys: { key: string; label_en: string; label_hi: string; value_type: string; required: boolean }[];
  parties: { role: string; name: string; address: string | null; provenance: string }[];
  incident_timeline: { date: string; label: string; provenance: string }[];
  missing_information: string[];
  analysis: {
    rule_outcomes?: Record<string, RuleOutcome>;
    potential_routes?: { key: string; title_en: string; title_hi: string; forum?: string; optional?: boolean }[];
  };
  workflow: {
    status: string | null;
    phase: string | null;
    category: string | null;
    category_confidence: number | null;
    routing: { reasons?: string[] } | null;
    last_error: string | null;
    steps: Step[];
  };
  deadlines: Deadline[];
  counts: { uploads: number; drafts: number; citations: number };
}

export interface Upload {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  document_class: string | null;
  page_count: number | null;
  security_flags: string[];
  error: string | null;
  created_at: string;
  extraction?: {
    method: string;
    language_hint: string | null;
    fields: Record<string, { value: string; excerpt: string | null; note?: string }>;
    injection_flags: string[];
    reviewed_at: string | null;
    text_preview: string | null;
    text_length: number;
  };
}

export interface Evidence {
  id: string;
  label: string;
  title: string;
  description: string | null;
  evidence_type: string;
  evidence_date: string | null;
  order_index: number;
  document_id: string | null;
  confirmed_by_user: boolean;
}

export interface Block {
  id: string;
  type: "notice" | "heading" | "subheading" | "parties" | "para" | "numbered" | "list" | "table" | "signature";
  text: string;
  items: string[];
  rows: string[][];
  editable: boolean;
  sources: { facts: string[]; refs: string[]; edited_by_user?: boolean };
}

export interface ValidationIssue {
  code: string;
  severity: "blocker" | "warning";
  message_en: string;
  message_hi: string;
  blocks?: string[];
}

export interface DocVersion {
  id: string;
  version_number: number;
  content_sha256: string;
  created_by: string;
  change_note: string | null;
  validation: { status?: "ok" | "needs_attention" | "blocked"; issues?: ValidationIssue[] };
  source_trace: { fact_ids?: string[]; legal_refs?: string[]; edited_from_version?: number };
  created_at: string;
  content?: { title: string; doc_type: string; blocks: Block[] };
}

export interface GeneratedDoc {
  id: string;
  doc_type: string;
  title: string;
  status: "draft" | "approved" | "superseded";
  language: string;
  template: string;
  current_version: number;
  updated_at: string;
  validation_status: "ok" | "needs_attention" | "blocked" | null;
  versions?: DocVersion[];
  approvals?: Approval[];
  approval_statement?: string;
}

export interface Approval {
  id: string;
  action: string;
  status: string;
  target_type: string;
  target_id: string;
  document_version_ids: string[];
  content_sha256: string | null;
  statement: string;
  decided_at: string | null;
  expires_at: string | null;
  consumed_at: string | null;
  created_at: string;
}

export interface FilingRecord {
  id: string;
  portal: string;
  mode: string;
  status: string;
  acknowledgement_number: string | null;
  acknowledgement_source: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  checklist_state: Record<string, boolean>;
  portal_state: Record<string, unknown>;
  notes: string | null;
  created_at: string;
}

export interface FilingOverview {
  portal: string;
  portal_url: string;
  capabilities: { guided: boolean; browser_assist: boolean; api_submission: boolean; notes: string[] };
  upload_rules: { formats: string[]; max_file_mb: number; observed_on: string };
  ready: boolean;
  blockers: string[];
  authorized: boolean;
  authorization: Approval | null;
  authorization_statement: string;
  share_statement: string;
  guided_steps: { key: string; title: string; detail: string; official_url: string }[];
  data_sheet: { key: string; label: string; value: string; missing: string }[];
  record: FilingRecord | null;
}

export interface CaseUpdate {
  id: string;
  source: "internal" | "user_reported" | "official_portal";
  update_type: string;
  title: string;
  body: string | null;
  event_date: string | null;
  verified: boolean;
  source_reference: string | null;
  created_at: string;
}

export interface Citation {
  id: string;
  topic: string;
  score: number;
  explanation: string;
  explanation_language: string;
  explanation_generated_by: string;
  section_ref: string;
  chapter: string | null;
  text: string;
  document: LegalDoc;
}

export interface LegalDoc {
  key: string;
  title: string;
  identifier: string | null;
  source_url: string;
  source_name: string | null;
  jurisdiction: string;
  publication_date: string | null;
  effective_date: string | null;
  effective_date_note: string | null;
  version_label: string | null;
  verification_status: string;
  verification_note: string | null;
  retrieved_at: string | null;
  amends?: { document: string; provisions: string[]; effect?: string; note?: string }[];
  chunk_count?: number;
  doc_type?: string;
  ingestion_status?: string;
}

export interface SearchResult {
  query: string;
  expanded_query: string;
  glossary_terms: string[];
  confidence: "high" | "medium" | "low" | "none";
  notes: string[];
  embedder: string;
  results: {
    chunk_id: string;
    document_key: string;
    document_title: string;
    section_ref: string | null;
    chapter: string | null;
    text: string;
    source_url: string;
    source_name: string;
    publication_date: string | null;
    effective_date_note: string | null;
    version_label: string | null;
    verification_status: string;
    retrieved_at: string | null;
    score: number;
    amendment_notices: string[];
    citation: string;
  }[];
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  case_id: string | null;
  read: boolean;
  created_at: string;
}

export interface Dashboard {
  cases: CaseSummary[];
  deadlines: Deadline[];
  documents_to_review: { id: string; case_id: string; title: string; case_title: string }[];
  pending_actions: (Step & { case_id: string; case_title: string })[];
  filings: (FilingRecord & { case_id: string; case_title: string })[];
  notifications: Notification[];
  unread_notifications: number;
  recent_conversations: { id: string; case_id: string; case_title: string; updated_at: string }[];
}
