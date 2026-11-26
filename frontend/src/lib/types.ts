export interface SystemHealth {
  status: string;
  service: string;
  version: string;
  database: string;
  details?: {
    pgvector_extension?: {
      available: boolean;
      version?: string;
      note?: string;
    };
    db_error?: string;
  };
}

export interface NvidiaHealth {
  status: string;
  model: string;
  base_url: string;
  message: string;
  latency_ms?: number;
  response_sample?: string;
}

export interface TenderClause {
  id: string;
  tender_id: string;
  clause_code: string;
  category: "TECHNICAL" | "FINANCIAL" | "STATUTORY" | "EXPERIENCE" | "DELIVERY_SLA" | string;
  title: string;
  description: string;
  is_mandatory: boolean;
  rule_config?: Record<string, any> | null;
  source_text: string;
  page_number: number;
  is_confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Tender {
  id: string;
  title: string;
  gem_tender_id?: string | null;
  file_name?: string | null;
  total_pages: number;
  extraction_status: "UPLOADED" | "EXTRACTING" | "REVIEW" | "READY" | "FAILED" | string;
  created_at: string;
  updated_at: string;
  clause_count?: number;
  clauses?: TenderClause[];
}

export interface ClauseCreateInput {
  category: string;
  title: string;
  description: string;
  is_mandatory: boolean;
  rule_config?: Record<string, any> | null;
  source_text: string;
  page_number: number;
}

export interface ClauseUpdateInput {
  category?: string;
  title?: string;
  description?: string;
  is_mandatory?: boolean;
  rule_config?: Record<string, any> | null;
  source_text?: string;
  page_number?: number;
  is_confirmed?: boolean;
}

export interface BidderDocument {
  id: string;
  bidder_id: string;
  file_name: string;
  doc_type?: string | null;
  total_pages: number;
  empty_pages_count: number;
  extraction_status: string;
  created_at: string;
}

export interface Bidder {
  id: string;
  tender_id: string;
  company_name: string;
  final_status: string;
  documents_count: number;
  chunks_count: number;
  evaluations_count: number;
  documents?: BidderDocument[];
  created_at: string;
  updated_at: string;
}

export interface BidderSummary {
  id: string;
  company_name: string;
  pass_count: number;
  fail_count: number;
  review_count: number;
  final_status: string;
  officer_recommendation?: string | null;
  has_contradiction?: boolean;
  officer_override_count?: number;
}

export interface ClauseSummary {
  id: string;
  clause_code: string;
  category: string;
  title: string;
  is_mandatory: boolean;
  rule_type?: string | null;
}

export type ExtractionMethod =
  | "DIGITAL_TEXT"
  | "OCR_PROCESSED"
  | "OCR_LOW_CONFIDENCE"
  | "EMPTY_SCANNED"
  | "OCR_FAILED";

export interface EvaluationCellSummary {
  evaluation_id: string;
  bidder_id?: string;
  clause_id?: string;
  clause_code: string;
  status: "PASS" | "FAIL" | "REVIEW";
  original_status: "PASS" | "FAIL" | "REVIEW";
  confidence_score?: number | null;
  claimed_value?: string | null;
  reasoning?: string | null;
  contradiction_detected: boolean;
  evidence_page_number?: number | null;
  evidence_chunk_id?: string | null;
  document_name?: string | null;
  override_status?: "PASS" | "FAIL" | "REVIEW" | null;
  override_reason?: string | null;
  extraction_method?: ExtractionMethod | string | null;
  ocr_confidence?: number | null;
}

export interface ComplianceMatrixResponse {
  tender_id: string;
  tender_title: string;
  gem_tender_id?: string;
  evaluation_date?: string;
  bidders: BidderSummary[];
  clauses: ClauseSummary[];
  matrix: Record<string, Record<string, EvaluationCellSummary>>;
  summary: {
    total_bidders: number;
    total_clauses: number;
    total_pass: number;
    total_fail: number;
    total_review: number;
    total_officer_overrides: number;
  };
}

export interface DeterministicRuleResult {
  rule_type: string;
  parameter?: string;
  required_value?: any;
  actual_value?: any;
  unit?: string;
  passed?: boolean | null;
  margin?: number | null;
  message: string;
}

export interface EvaluationDetailResponse {
  id?: string;
  evaluation_id?: string;
  tender_id: string;
  bidder_id: string;
  bidder_name: string;
  clause_id: string;
  clause_code: string;
  clause_title: string;
  clause_category: string;
  clause_source_text: string;
  clause_page_number: number;
  is_mandatory?: boolean;
  status: "PASS" | "FAIL" | "REVIEW";
  original_status: "PASS" | "FAIL" | "REVIEW";
  confidence_score?: number | null;
  claimed_value?: string | null;
  reasoning?: string | null;
  evidence_snippet?: string | null;
  evidence_page_number?: number | null;
  evidence_chunk_id?: string | null;
  document_name?: string | null;
  rule_result?: DeterministicRuleResult | null;
  contradiction_detected: boolean;
  contradiction_details?: string | null;
  override_status?: "PASS" | "FAIL" | "REVIEW" | null;
  override_reason?: string | null;
  overridden_by?: string | null;
  overridden_at?: string | null;
  extraction_method?: ExtractionMethod | string | null;
  ocr_confidence?: number | null;
}

export interface OfficerOverrideRequest {
  override_status: "PASS" | "FAIL" | "REVIEW";
  override_reason: string;
  officer_id?: string;
}

export interface EvaluationRunRequest {
  use_live_llm?: boolean;
  bidder_ids?: string[];
}

export interface EvaluationRunResponse {
  tender_id: string;
  bidders_evaluated: number;
  total_evaluations: number;
  reports: any[];
}

export interface DemoBiddersLoadResponse {
  tender_id: string;
  message: string;
  bidders_count: number;
  bidders: Bidder[];
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface ScoreBreakdown {
  tender_compliance: number;
  statutory_consistency: number;
  evidence_completeness: number;
  contradiction_score: number;
}

export interface ScoreSummary {
  pass_count: number;
  fail_count: number;
  review_count: number;
  inconsistency_count: number;
  major_contradiction_count: number;
  minor_contradiction_count: number;
}

export interface BidderComplianceScore {
  bidder_id: string;
  tender_id?: string;
  company_name: string;
  overall_score: number;
  risk_level: RiskLevel;
  breakdown: ScoreBreakdown;
  risk_triggers: string[];
  summary: ScoreSummary;
  calculation_details?: Record<string, any>;
  disclaimer: string;
  created_at?: string;
}

export interface RankedBidderItem {
  rank: number;
  bidder_id: string;
  company_name: string;
  overall_score: number;
  risk_level: RiskLevel;
  breakdown: ScoreBreakdown;
  recommendation: string;
  warning_count: number;
  key_warnings: string[];
}

export interface TenderBidderRankingResponse {
  tender_id: string;
  tender_title: string;
  total_bidders: number;
  rankings: RankedBidderItem[];
  disclaimer: string;
  generated_at: string;
}

export type RecommendationCategory =
  | "RECOMMENDED_FOR_OFFICER_REVIEW"
  | "REQUIRES_ADDITIONAL_EVIDENCE"
  | "HIGH_RISK_OFFICER_REVIEW";

export type RecommendationSource = "AI" | "DETERMINISTIC_FALLBACK";

export type OfficerAction =
  | "ACKNOWLEDGED"
  | "NEEDS_ADDITIONAL_EVIDENCE"
  | "OVERRIDE_REVIEW"
  | "FINAL_OFFICER_DECISION";

export interface EvidenceReference {
  reference_id: string;
  clause_code?: string | null;
  source_type: string;
  source_name: string;
  page?: number | null;
  verification_id?: string | null;
  summary: string;
}

export interface AIRecommendationResponse {
  recommendation_id: string;
  tender_id: string;
  bidder_id: string;
  bidder_name: string;
  recommendation: RecommendationCategory;
  recommendation_source: RecommendationSource;
  confidence: string;
  overall_score: number;
  risk_level: string;
  executive_summary: string;
  key_reasons: string[];
  positive_findings: string[];
  risk_findings: string[];
  missing_evidence: string[];
  contradictions: string[];
  priority_actions: string[];
  supporting_references: EvidenceReference[];
  model_identifier: string;
  generated_at: string;
  disclaimer: string;
}

export interface OfficerReviewRequest {
  action: OfficerAction;
  justification: string;
  recommendation_id?: string | null;
}

export interface AuditRecordItem {
  id: string;
  tender_id: string;
  bidder_id: string;
  evaluation_id?: string | null;
  recommendation_id: string;
  event_type: string;
  recommendation_type: RecommendationCategory;
  recommendation_source: RecommendationSource;
  score_at_recommendation: number;
  risk_at_recommendation: string;
  recommendation_summary: string;
  key_reasons: string[];
  evidence_references: EvidenceReference[];
  positive_findings: string[];
  risk_findings: string[];
  priority_actions: string[];
  model_identifier: string;
  officer_action?: OfficerAction | null;
  officer_comment?: string | null;
  action_timestamp: string;
  disclaimer: string;
  created_at: string;
}

export interface AuditTrailResponse {
  tender_id: string;
  bidder_id: string;
  records: AuditRecordItem[];
}

export type StatutoryAuthority = "GSTN" | "UDYAM" | "MCA" | "INCOME_TAX" | "MII" | "DEBARMENT" | "DPIIT" | "EPFO" | "ESIC" | "NSIC" | "DIGILOCKER";
export type DebarmentTemporalStatus = "ACTIVE_ON_DATE" | "EXPIRED_BEFORE_DATE" | "STARTS_AFTER_DATE" | "UNKNOWN_PERIOD";
export type SourceMode = "MOCK" | "LIVE";
export type SourceConnectionStatus = "SUCCESS" | "TIMEOUT" | "UNAVAILABLE" | "RATE_LIMITED" | "AUTH_FAILURE" | "ERROR";
export type SourceVerificationStatus = "VERIFIED" | "NOT_FOUND" | "INACTIVE" | "EXPIRED" | "UNVERIFIED" | "DISCREPANCY" | "FAILED";

export interface SourceVerificationResult {
  verification_id: string;
  authority: StatutoryAuthority;
  source_name: string;
  query_identifier: string;
  identifier_type: string;
  mode: SourceMode;
  connection_status: SourceConnectionStatus;
  verification_status: SourceVerificationStatus;
  retrieved_at: string;
  as_of_date?: string | null;
  data_payload: Record<string, any>;
  confidence_score: number;
  provenance_note: string;
  error_message?: string | null;
  execution_time_ms: number;
}

export interface StatutoryVerificationQuery {
  bidder_id?: string | null;
  tender_id?: string | null;
  authorities?: StatutoryAuthority[] | null;
  identifiers?: Record<string, string>;
  as_of_date?: string | null;
  mode?: SourceMode;
}

export interface BidderStatutoryVerificationSummary {
  bidder_id?: string | null;
  tender_id?: string | null;
  results: SourceVerificationResult[];
  total_sources: number;
  successful_connections: number;
  failed_connections: number;
  as_of_date?: string | null;
  verified_at: string;
  disclaimer: string;
}

export interface StatutoryAdapterInfo {
  authority: StatutoryAuthority;
  source_name: string;
  supported_identifier_types: string[];
  mode: SourceMode;
  disclaimer: string;
}

// ==========================================
// Phase 8.4 Verification Intelligence Types
// ==========================================

export type RiskReasonCode =
  | "ACTIVE_DEBARMENT"
  | "MAJOR_CONTRADICTION"
  | "IDENTITY_CONFLICT"
  | "INSUFFICIENT_EVIDENCE"
  | "SOURCE_UNAVAILABLE"
  | "SOURCE_TIMEOUT"
  | "SOURCE_AUTH_FAILURE"
  | "SOURCE_FAILED"
  | "TEMPORAL_UNVERIFIED"
  | "OCR_LOW_CONFIDENCE"
  | "MANDATORY_CLAUSE_FAIL"
  | "RECOMMENDATION_REVIEW";

export type RiskReasonSeverity = "HIGH" | "REVIEW" | "INFO";

export interface RiskReasonItem {
  reason_code: RiskReasonCode;
  severity: RiskReasonSeverity;
  title: string;
  explanation: string;
  source_type: string;
  source_name: string;
  verification_id?: string | null;
  clause_code?: string | null;
  evidence_reference?: string | null;
  requires_officer_review: boolean;
  detected_at?: string;
}

export interface SourceStatusItem {
  authority: string;
  source_name: string;
  connection_status: string;
  verification_status: string;
  is_technical_failure: boolean;
  is_business_not_found: boolean;
  retrieved_at?: string | null;
  as_of_date?: string | null;
  query_identifier?: string | null;
  identifier_type?: string | null;
  validity_start?: string | null;
  validity_end?: string | null;
  provenance_note: string;
  verification_id?: string | null;
  error_message?: string | null;
  is_mock: boolean;
  previous_successful_result?: Record<string, any> | null;
}

export interface DebarmentStateSummary {
  is_debarred: boolean;
  temporal_status: string;
  order_number?: string | null;
  authority?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  as_of_date?: string | null;
  reason?: string | null;
  verification_id?: string | null;
  provenance_note: string;
}

export interface OfficerBidderVerificationSummary {
  bidder_id: string;
  tender_id: string;
  company_name: string;
  overall_risk_state: "LOW" | "MEDIUM" | "HIGH";
  base_compliance_score: number;
  score_breakdown: {
    tender_compliance: number;
    statutory_consistency: number;
    evidence_completeness: number;
    contradiction_score: number;
  };
  debarment_state: DebarmentStateSummary;
  source_statuses: Record<string, SourceStatusItem>;
  major_contradictions: string[];
  identity_conflicts: string[];
  missing_or_insufficient_evidence: string[];
  technical_source_failures: string[];
  officer_review_required: boolean;
  risk_reasons: RiskReasonItem[];
  evaluated_at: string;
  as_of_date?: string | null;
  disclaimer: string;
}

export interface VerificationHistoryItem {
  id: string;
  verification_id: string;
  authority: string;
  source_name: string;
  query_identifier: string;
  identifier_type: string;
  connection_status: string;
  verification_status: string;
  is_latest: boolean;
  retrieved_at: string;
  as_of_date?: string | null;
  data_payload: Record<string, any>;
  confidence_score: number;
  provenance_note: string;
  error_message?: string | null;
  execution_time_ms: number;
}

export interface VerificationHistoryResponse {
  bidder_id: string;
  tender_id: string;
  total_attempts: number;
  history: VerificationHistoryItem[];
  disclaimer: string;
}

export interface ReviewQueueItem {
  bidder_id: string;
  tender_id: string;
  company_name: string;
  overall_risk_state: "LOW" | "MEDIUM" | "HIGH";
  compliance_score: number;
  review_triggers: string[];
  primary_risk_reasons: RiskReasonItem[];
  debarred: boolean;
  contradiction_count: number;
  technical_failure_count: number;
  queued_at: string;
}

export interface OfficerReviewQueueResponse {
  tender_id: string;
  total_queued: number;
  items: ReviewQueueItem[];
  generated_at: string;
  disclaimer: string;
}

// ====================================================
// Phase 1.1 Enterprise Authentication & RBAC Types
// ====================================================

export type UserRole =
  | "SUPER_ADMIN"
  | "ORG_ADMIN"
  | "PROCUREMENT_OFFICER"
  | "AUDITOR"
  | "BIDDER";

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  organization_id: string;
  roles: string[];
  permissions: string[];
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  organization_name: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
  is_verified: boolean;
  last_login_at?: string | null;
  created_at: string;
}

// ====================================================
// Phase 1.2 Organization, Membership & Invitation Types
// ====================================================

export interface OrganizationProfile {
  id: string;
  name: string;
  slug: string;
  domain?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  total_members: number;
  active_members: number;
  pending_invitations: number;
}

export interface OrganizationUpdateRequest {
  name?: string;
  domain?: string | null;
}

export interface RoleSummary {
  name: string;
  description: string;
  scope: string;
  assignable_by_org_admin: boolean;
  permissions: string[];
}

export interface OrganizationMember {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  roles: string[];
  is_active: boolean;
  is_verified: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export interface OrganizationMemberListResponse {
  items: OrganizationMember[];
  total: number;
  limit: number;
  offset: number;
}

export type InvitationLifecycleStatus = "PENDING" | "ACCEPTED" | "EXPIRED" | "REVOKED";

export interface OrganizationInvitationItem {
  id: string;
  organization_id: string;
  email: string;
  role_name: string;
  status: InvitationLifecycleStatus;
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  invited_by_user_id?: string | null;
  created_at: string;
}

export interface OrganizationInvitationListResponse {
  items: OrganizationInvitationItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface InvitationCreateResponse {
  id: string;
  email: string;
  role_name: string;
  organization_id: string;
  expires_at: string;
  invitation_token: string;
  email_delivery_status: string;
}

export interface InvitationValidateResponse {
  valid: boolean;
  status: "PENDING" | "EXPIRED" | "REVOKED" | "ACCEPTED" | "INVALID";
  organization_name?: string | null;
  role_name?: string | null;
  email_masked?: string | null;
  expires_at?: string | null;
  requires_existing_login: boolean;
}

export interface InvitationAcceptRequest {
  invitation_token: string;
  email: string;
  password: string;
  full_name: string;
}

// ====================================================
// Phase 1.3 Audit Trail Types
// ====================================================

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  organization_id?: string | null;
  user_id?: string | null;
  user_email?: string | null;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  diff_json?: Record<string, any> | null;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
}

// ====================================================
// Phase 2.0A Multi-Document Tender Types
// ====================================================

export type TenderDocumentRole =
  | "PRIMARY_NIT"
  | "TECHNICAL_SPEC"
  | "BOQ"
  | "CORRIGENDUM"
  | "ANNEXURE"
  | "OTHER";

export type ProcessingJobStatus =
  | "QUEUED"
  | "RUNNING"
  | "RETRY_WAIT"
  | "SUCCEEDED"
  | "FAILED";

export interface TenderProcessingJob {
  id: string;
  tender_id: string;
  tender_document_id: string;
  job_type: string;
  status: ProcessingJobStatus;
  current_stage: string;
  progress_pct: number;
  retry_count: number;
  max_retries: number;
  extracted_count?: number;
  extraction_version?: number;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TenderDocumentPage {
  id: string;
  tender_document_id: string;
  page_number: number;
  extracted_text: string;
  word_count: number;
  extraction_method: string;
  ocr_confidence?: number | null;
  extraction_status: string;
}

export interface TenderDocumentPagesListResponse {
  tender_id: string;
  tender_document_id: string;
  total: number;
  limit: number;
  offset: number;
  items: TenderDocumentPage[];
}

export interface TenderDocument {
  id: string;
  tender_id: string;
  document_role: TenderDocumentRole;
  original_filename: string;
  file_size_bytes: number;
  sha256_hash: string;
  total_pages?: number | null;
  processing_status: string;
  created_at: string;
  updated_at: string;
  latest_job?: TenderProcessingJob | null;
}

// ====================================================
// Phase 2.0C TenderLens Requirement Intelligence Types
// ====================================================

export type RequirementCategoryCode =
  | "ELIG"
  | "TECH"
  | "FIN"
  | "STAT"
  | "EXP"
  | "DOC"
  | "DEL"
  | "SUB"
  | "DATE"
  | "PREF"
  | "UNCLASSIFIED";

export type RequirementMandatoryStatus = "MANDATORY" | "OPTIONAL" | "UNCLEAR";
export type RequirementReviewStatus =
  | "DRAFT"
  | "CONFIRMED"
  | "REJECTED"
  | "NEEDS_REVIEW"
  | "SUPERSEDED";

export interface TenderRequirement {
  id: string;
  tender_id: string;
  source_document_id: string;
  processing_job_id?: string | null;
  requirement_code: string;
  extraction_version: number;
  source_page_number: number;
  source_page_range?: string | null;
  source_section?: string | null;
  source_text: string;
  source_quote_verified: boolean;
  normalized_statement: string;
  explanatory_interpretation: string;
  primary_category: RequirementCategoryCode;
  secondary_categories: string[];
  requirement_type: string;
  mandatory_status: RequirementMandatoryStatus;
  expected_document_or_evidence?: string | null;
  expected_action_by_bidder?: string | null;
  numeric_value?: string | null;
  unit?: string | null;
  currency?: string | null;
  period_or_validity?: string | null;
  conditions_and_exceptions?: string | null;
  extraction_method: string;
  model_provider: string;
  model_version?: string | null;
  extraction_confidence: number;
  review_status: RequirementReviewStatus;
  created_at: string;
  updated_at: string;
}

export interface TenderRequirementsListResponse {
  tender_id: string;
  total: number;
  limit: number;
  offset: number;
  items: TenderRequirement[];
}

// ====================================================
// Phase 2.0D Provenance, Conflict & Evidence Types
// ====================================================

export interface TenderRequirementSource {
  id: string;
  requirement_id: string;
  source_document_id: string;
  source_role: string;
  source_page_number: number;
  source_section?: string | null;
  source_text: string;
  verification_status: string;
  source_document_sha256?: string | null;
}

export interface TenderRequirementProvenance {
  requirement_id: string;
  tender_id: string;
  source_document_id: string;
  source_document_name?: string | null;
  source_document_role?: string | null;
  source_page_number: number;
  source_page_range?: string | null;
  source_section?: string | null;
  source_text: string;
  normalized_statement: string;
  extraction_version: number;
  source_document_sha256?: string | null;
  verification_status: string;
  matched_page_number?: number | null;
  verification_detail: string;
  supporting_sources: TenderRequirementSource[];
}

export interface TenderRequirementConflict {
  id: string;
  tender_id: string;
  requirement_a_id: string;
  requirement_b_id: string;
  conflict_type: string;
  relationship_type: string;
  severity: string;
  status: string;
  scope_summary?: string | null;
  explanation: string;
  created_at: string;
  updated_at: string;
}

export interface TenderRequirementConflictsListResponse {
  tender_id: string;
  total: number;
  limit: number;
  offset: number;
  items: TenderRequirementConflict[];
}

export interface ConflictDetectionRunResponse {
  tender_id: string;
  detected_count: number;
  conflicts: TenderRequirementConflict[];
}

export interface TenderRequirementEvidence {
  id: string;
  tender_id: string;
  requirement_id: string;
  evidence_type: string;
  expected_document_name: string;
  evidence_purpose: string;
  is_mandatory: boolean;
  source_passage: string;
  mapping_method: string;
  confidence: number;
  mapping_status: string;
  created_at: string;
  updated_at: string;
}

export interface TenderRequirementEvidenceListResponse {
  tender_id: string;
  requirement_id: string;
  total: number;
  items: TenderRequirementEvidence[];
}
