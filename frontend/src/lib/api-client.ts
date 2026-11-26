import {
  clearAccessToken,
  getAccessToken,
  isAccessTokenExpiringSoon,
  notifySessionExpired,
  runSingleFlightRefresh,
} from "./auth-store";
import type {
  AIRecommendationResponse,
  AuditRecordItem,
  AuditTrailResponse,
  Bidder,
  BidderComplianceScore,
  ClauseCreateInput,
  ClauseUpdateInput,
  ComplianceMatrixResponse,
  DemoBiddersLoadResponse,
  EvaluationDetailResponse,
  EvaluationRunRequest,
  EvaluationRunResponse,
  NvidiaHealth,
  OfficerBidderVerificationSummary,
  OfficerOverrideRequest,
  OfficerReviewQueueResponse,
  OfficerReviewRequest,
  SourceVerificationResult,
  StatutoryAdapterInfo,
  StatutoryVerificationQuery,
  BidderStatutoryVerificationSummary,
  SystemHealth,
  Tender,
  TenderBidderRankingResponse,
  TenderClause,
  TokenResponse,
  VerificationHistoryResponse,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL !== undefined
    ? process.env.NEXT_PUBLIC_API_URL
    : process.env.NEXT_PUBLIC_API_BASE_URL !== undefined
      ? process.env.NEXT_PUBLIC_API_BASE_URL
      : "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface ApiFetchOptions extends RequestInit {
  skipAuth?: boolean;
  _retried?: boolean;
}

const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function isAuthLifecyclePath(path: string): boolean {
  return (
    path.startsWith("/api/v1/auth/login") ||
    path.startsWith("/api/v1/auth/refresh") ||
    path.startsWith("/api/v1/auth/logout")
  );
}

/**
 * Single-flight cookie-based refresh against `/api/v1/auth/refresh`.
 */
export async function performTokenRefresh(): Promise<string | null> {
  return runSingleFlightRefresh(async () => {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
    });

    if (!res.ok) {
      return null;
    }

    const data = (await res.json()) as TokenResponse;
    return {
      access_token: data.access_token,
      expires_in: data.expires_in,
    };
  });
}

async function parseErrorDetail(response: Response, fallback: string): Promise<string> {
  const err = await response.json().catch(() => null);
  if (err && typeof err.detail === "string" && err.detail.trim().length > 0) {
    return err.detail;
  }
  return fallback;
}

export async function apiFetchResponse(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const { skipAuth = false, _retried = false, headers: customHeaders, ...fetchInit } = options;
  const method = (fetchInit.method || "GET").toUpperCase();

  if (!skipAuth && !isAuthLifecyclePath(path) && getAccessToken() && isAccessTokenExpiringSoon()) {
    await performTokenRefresh();
  }

  const headers = new Headers(customHeaders);
  if (!skipAuth) {
    const token = getAccessToken();
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...fetchInit,
    method,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && !skipAuth && !_retried && !isAuthLifecyclePath(path)) {
    const refreshedToken = await performTokenRefresh();
    if (!refreshedToken) {
      clearAccessToken();
      notifySessionExpired("session_expired");
      throw new ApiError(401, "Your session has expired. Please sign in again.");
    }

    if (IDEMPOTENT_METHODS.has(method)) {
      return apiFetchResponse(path, {
        ...options,
        _retried: true,
      });
    }

    // Do not blindly re-submit non-idempotent mutations after 401
    throw new ApiError(401, "Session renewed. Please submit your request again.");
  }

  return response;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
  fallbackError?: string
): Promise<T> {
  const response = await apiFetchResponse(path, options);
  if (!response.ok) {
    const defaultMsg = fallbackError || `Request failed with status ${response.status}`;
    const detail = await parseErrorDetail(response, defaultMsg);
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  return apiFetch<SystemHealth>(
    "/api/v1/health",
    { cache: "no-store", skipAuth: true },
    "Health check failed"
  );
}

export async function fetchNvidiaHealth(): Promise<NvidiaHealth> {
  return apiFetch<NvidiaHealth>(
    "/api/v1/health/nvidia",
    { cache: "no-store", skipAuth: true },
    "NVIDIA health check failed"
  );
}

export async function uploadTenderPdf(
  file: File,
  title: string,
  gemTenderId?: string
): Promise<Tender> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  if (gemTenderId) {
    formData.append("gem_tender_id", gemTenderId);
  }

  return apiFetch<Tender>(
    "/api/v1/tenders/upload",
    { method: "POST", body: formData },
    "Upload failed"
  );
}

export async function triggerClauseExtraction(tenderId: string): Promise<{
  tender_id: string;
  extraction_status: string;
  total_pages: number;
  extracted_count: number;
  clauses: TenderClause[];
}> {
  return apiFetch(
    `/api/v1/tenders/${tenderId}/extract`,
    { method: "POST" },
    "Extraction failed"
  );
}

export async function fetchTenders(): Promise<Tender[]> {
  return apiFetch<Tender[]>(
    "/api/v1/tenders",
    { cache: "no-store" },
    "Failed to fetch tenders"
  );
}

export async function fetchTenderDetail(tenderId: string): Promise<Tender> {
  return apiFetch<Tender>(
    `/api/v1/tenders/${tenderId}`,
    { cache: "no-store" },
    "Failed to fetch tender detail"
  );
}

export async function fetchTenderClauses(tenderId: string): Promise<TenderClause[]> {
  return apiFetch<TenderClause[]>(
    `/api/v1/tenders/${tenderId}/clauses`,
    { cache: "no-store" },
    "Failed to fetch clauses"
  );
}

export async function addManualClause(
  tenderId: string,
  clause: ClauseCreateInput
): Promise<TenderClause> {
  return apiFetch<TenderClause>(
    `/api/v1/tenders/${tenderId}/clauses`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(clause),
    },
    "Failed to add clause"
  );
}

export async function updateClause(
  tenderId: string,
  clauseId: string,
  updates: ClauseUpdateInput
): Promise<TenderClause> {
  return apiFetch<TenderClause>(
    `/api/v1/tenders/${tenderId}/clauses/${clauseId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    },
    "Failed to update clause"
  );
}

export async function deleteClause(tenderId: string, clauseId: string): Promise<void> {
  const response = await apiFetchResponse(
    `/api/v1/tenders/${tenderId}/clauses/${clauseId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to delete clause: ${response.status}`
    );
    throw new ApiError(response.status, detail);
  }
}

export async function confirmTenderClauses(tenderId: string): Promise<Tender> {
  return apiFetch<Tender>(
    `/api/v1/tenders/${tenderId}/confirm`,
    { method: "POST" },
    "Failed to confirm clauses"
  );
}

export async function fetchTenderBidders(tenderId: string): Promise<Bidder[]> {
  return apiFetch<Bidder[]>(
    `/api/v1/tenders/${tenderId}/bidders`,
    { cache: "no-store" },
    "Failed to fetch bidders"
  );
}

export async function createBidder(
  tenderId: string,
  companyName: string,
  files?: File[]
): Promise<Bidder> {
  const formData = new FormData();
  formData.append("company_name", companyName);
  if (files && files.length > 0) {
    for (const f of files) {
      formData.append("files", f);
    }
  }

  return apiFetch<Bidder>(
    `/api/v1/tenders/${tenderId}/bidders`,
    { method: "POST", body: formData },
    "Failed to create bidder"
  );
}

export async function loadDemoBidders(tenderId: string): Promise<DemoBiddersLoadResponse> {
  return apiFetch<DemoBiddersLoadResponse>(
    `/api/v1/tenders/${tenderId}/bidders/demo`,
    { method: "POST" },
    "Failed to load demo bidders"
  );
}

export async function deleteBidder(tenderId: string, bidderId: string): Promise<void> {
  const response = await apiFetchResponse(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to delete bidder: ${response.status}`
    );
    throw new ApiError(response.status, detail);
  }
}

export async function triggerComplianceEvaluation(
  tenderId: string,
  options?: EvaluationRunRequest
): Promise<EvaluationRunResponse> {
  return apiFetch<EvaluationRunResponse>(
    `/api/v1/tenders/${tenderId}/evaluations/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options || { use_live_llm: false }),
    },
    "Evaluation run failed"
  );
}

export async function fetchComplianceMatrix(tenderId: string): Promise<ComplianceMatrixResponse> {
  return apiFetch<ComplianceMatrixResponse>(
    `/api/v1/tenders/${tenderId}/evaluations/matrix`,
    { cache: "no-store" },
    "Failed to fetch compliance matrix"
  );
}

export async function fetchEvaluationDetail(
  tenderId: string,
  evaluationId: string
): Promise<EvaluationDetailResponse> {
  return apiFetch<EvaluationDetailResponse>(
    `/api/v1/tenders/${tenderId}/evaluations/${evaluationId}`,
    { cache: "no-store" },
    "Failed to fetch evaluation detail"
  );
}

export async function submitOfficerOverride(
  tenderId: string,
  evaluationId: string,
  req: OfficerOverrideRequest
): Promise<EvaluationDetailResponse> {
  return apiFetch<EvaluationDetailResponse>(
    `/api/v1/tenders/${tenderId}/evaluations/${evaluationId}/override`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
    "Failed to submit officer override"
  );
}

// ============================================================================
// Phase 6 Mock Verification Data Explorer
// ============================================================================

export async function fetchMockSourcesSummary(): Promise<any> {
  return apiFetch<any>(
    "/api/v1/mock-sources",
    { cache: "no-store" },
    "Failed to load mock sources summary"
  );
}

export async function fetchMockSourcesIntegrity(): Promise<any> {
  return apiFetch<any>(
    "/api/v1/mock-sources/integrity",
    { cache: "no-store" },
    "Failed to load dataset integrity"
  );
}

export async function fetchMockSourceRecords(
  source: string,
  page = 1,
  pageSize = 25,
  search?: string,
  status?: string,
  showcaseOnly = false
): Promise<any> {
  const params = new URLSearchParams();
  params.set("page", page.toString());
  params.set("page_size", pageSize.toString());
  if (search && search.trim()) params.set("search", search.trim());
  if (status && status.trim()) params.set("status", status.trim());
  if (showcaseOnly) params.set("showcase_only", "true");

  return apiFetch<any>(
    `/api/v1/mock-sources/${source}?${params.toString()}`,
    { cache: "no-store" },
    `Failed to fetch ${source} records`
  );
}

export async function fetchMockRecordDetail(source: string, verificationId: string): Promise<any> {
  return apiFetch<any>(
    `/api/v1/mock-sources/${source}/${encodeURIComponent(verificationId)}`,
    { cache: "no-store" },
    "Failed to load record detail"
  );
}

export async function fetchShowcaseBidders(bidderId?: string): Promise<any> {
  const path = bidderId
    ? `/api/v1/mock-sources/showcase?bidder_id=${encodeURIComponent(bidderId)}`
    : "/api/v1/mock-sources/showcase";
  return apiFetch<any>(path, { cache: "no-store" }, "Failed to load showcase bidders");
}

export function getMockSourceExportUrl(source: string): string {
  return `${API_BASE_URL}/api/v1/mock-sources/${source}/export/csv`;
}

export async function fetchBidderScore(
  tenderId: string,
  bidderId: string
): Promise<BidderComplianceScore> {
  return apiFetch<BidderComplianceScore>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/score`,
    { cache: "no-store" },
    "Failed to fetch bidder score"
  );
}

export async function fetchTenderRanking(
  tenderId: string
): Promise<TenderBidderRankingResponse> {
  return apiFetch<TenderBidderRankingResponse>(
    `/api/v1/tenders/${tenderId}/ranking`,
    { cache: "no-store" },
    "Failed to fetch tender ranking"
  );
}

export async function fetchBidderRecommendation(
  tenderId: string,
  bidderId: string
): Promise<AIRecommendationResponse | null> {
  const res = await apiFetchResponse(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/recommendation`,
    { cache: "no-store" }
  );
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    const detail = await parseErrorDetail(res, `Failed to fetch recommendation: ${res.status}`);
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export async function generateBidderRecommendation(
  tenderId: string,
  bidderId: string
): Promise<AIRecommendationResponse> {
  return apiFetch<AIRecommendationResponse>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/recommendation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
    "Failed to generate recommendation"
  );
}

export async function submitOfficerReview(
  tenderId: string,
  bidderId: string,
  req: OfficerReviewRequest
): Promise<AuditRecordItem> {
  return apiFetch<AuditRecordItem>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
    "Failed to submit officer review"
  );
}

export async function fetchBidderAuditTrail(
  tenderId: string,
  bidderId: string
): Promise<AuditTrailResponse> {
  return apiFetch<AuditTrailResponse>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/audit`,
    { cache: "no-store" },
    "Failed to fetch audit trail"
  );
}

// ====================================================
// Phase 8.3 Statutory Verification Client APIs
// ====================================================

export async function verifyStatutorySources(
  query: StatutoryVerificationQuery
): Promise<BidderStatutoryVerificationSummary> {
  return apiFetch<BidderStatutoryVerificationSummary>(
    "/api/v1/statutory/verify",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(query),
    },
    "Failed to verify statutory sources"
  );
}

export async function fetchStatutoryStatus(params?: {
  bidderId?: string;
  tenderId?: string;
  authority?: string;
}): Promise<SourceVerificationResult[]> {
  const queryParts: string[] = [];
  if (params?.bidderId) queryParts.push(`bidder_id=${encodeURIComponent(params.bidderId)}`);
  if (params?.tenderId) queryParts.push(`tender_id=${encodeURIComponent(params.tenderId)}`);
  if (params?.authority) queryParts.push(`authority=${encodeURIComponent(params.authority)}`);
  const qs = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";

  return apiFetch<SourceVerificationResult[]>(
    `/api/v1/statutory/status${qs}`,
    { cache: "no-store" },
    "Failed to fetch statutory status"
  );
}

export async function fetchStatutoryAdapters(): Promise<StatutoryAdapterInfo[]> {
  return apiFetch<StatutoryAdapterInfo[]>(
    "/api/v1/statutory/adapters",
    { cache: "no-store" },
    "Failed to fetch statutory adapters"
  );
}

// ====================================================
// Phase 8.4 Verification Intelligence Client APIs
// ====================================================

export async function fetchBidderVerificationSummary(
  tenderId: string,
  bidderId: string,
  asOfDate?: string
): Promise<OfficerBidderVerificationSummary> {
  const qs = asOfDate ? `?as_of_date=${encodeURIComponent(asOfDate)}` : "";
  return apiFetch<OfficerBidderVerificationSummary>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/verification-summary${qs}`,
    { cache: "no-store" },
    "Failed to fetch verification summary"
  );
}

export async function fetchBidderVerificationHistory(
  tenderId: string,
  bidderId: string
): Promise<VerificationHistoryResponse> {
  return apiFetch<VerificationHistoryResponse>(
    `/api/v1/tenders/${tenderId}/bidders/${bidderId}/verification-history`,
    { cache: "no-store" },
    "Failed to fetch verification history"
  );
}

export async function fetchTenderReviewQueue(
  tenderId: string
): Promise<OfficerReviewQueueResponse> {
  return apiFetch<OfficerReviewQueueResponse>(
    `/api/v1/tenders/${tenderId}/review-queue`,
    { cache: "no-store" },
    "Failed to fetch tender review queue"
  );
}
