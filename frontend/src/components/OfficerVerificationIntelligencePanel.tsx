"use client";

import { useEffect, useState } from "react";
import {
  fetchBidderVerificationSummary,
  fetchBidderVerificationHistory,
  fetchTenderReviewQueue,
} from "@/lib/api-client";
import {
  OfficerBidderVerificationSummary,
  VerificationHistoryResponse,
  OfficerReviewQueueResponse,
  ReviewQueueItem,
  SourceStatusItem,
  RiskReasonItem,
  VerificationHistoryItem,
} from "@/lib/types";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Clock,
  History,
  ExternalLink,
  ChevronRight,
  Info,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RotateCw,
  FileText,
  Building2,
  AlertOctagon,
  Scale,
  Award,
  FolderCheck,
  X,
} from "lucide-react";

interface OfficerVerificationIntelligencePanelProps {
  tenderId: string;
  bidderId?: string;
  bidderName?: string;
  onSelectBidder?: (bidderId: string) => void;
}

export default function OfficerVerificationIntelligencePanel({
  tenderId,
  bidderId,
  bidderName,
  onSelectBidder,
}: OfficerVerificationIntelligencePanelProps) {
  const [summary, setSummary] = useState<OfficerBidderVerificationSummary | null>(null);
  const [queue, setQueue] = useState<OfficerReviewQueueResponse | null>(null);
  const [history, setHistory] = useState<VerificationHistoryResponse | null>(null);
  const [selectedBidderId, setSelectedBidderId] = useState<string>(bidderId || "");
  const [loading, setLoading] = useState<boolean>(false);
  const [queueLoading, setQueueLoading] = useState<boolean>(false);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Sync prop changes
  useEffect(() => {
    if (bidderId) {
      setSelectedBidderId(bidderId);
    }
  }, [bidderId]);

  // Load Review Queue on mount or tenderId change
  useEffect(() => {
    if (!tenderId) return;
    loadReviewQueue();
  }, [tenderId]);

  // Load Bidder Verification Summary when selectedBidderId changes
  useEffect(() => {
    if (!tenderId || !selectedBidderId) return;
    loadSummary(selectedBidderId);
  }, [tenderId, selectedBidderId]);

  const loadReviewQueue = async () => {
    setQueueLoading(true);
    try {
      const q = await fetchTenderReviewQueue(tenderId);
      setQueue(q);
      // Auto-select first queued bidder if no bidder currently selected
      if (!selectedBidderId && q.items.length > 0) {
        setSelectedBidderId(q.items[0].bidder_id);
      }
    } catch (err: any) {
      console.error("Failed to load review queue:", err);
    } finally {
      setQueueLoading(false);
    }
  };

  const loadSummary = async (bId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBidderVerificationSummary(tenderId, bId);
      setSummary(data);
    } catch (err: any) {
      setError(err.message || "Failed to load verification intelligence summary");
    } finally {
      setLoading(false);
    }
  };

  const openHistory = async () => {
    if (!selectedBidderId) return;
    setHistoryOpen(true);
    setHistoryLoading(true);
    try {
      const h = await fetchBidderVerificationHistory(tenderId, selectedBidderId);
      setHistory(h);
    } catch (err: any) {
      console.error("Failed to fetch verification history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleSelectBidder = (bId: string) => {
    setSelectedBidderId(bId);
    if (onSelectBidder) {
      onSelectBidder(bId);
    }
  };

  // Helper for source status badge styles
  const getSourceStatusBadge = (item: SourceStatusItem) => {
    if (item.is_technical_failure) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300">
          <AlertTriangle className="w-3 h-3 text-amber-600" />
          {item.connection_status}
        </span>
      );
    }
    if (item.is_business_not_found) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
          <HelpCircle className="w-3 h-3 text-slate-500" />
          NOT FOUND
        </span>
      );
    }
    if (item.verification_status === "VERIFIED") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-emerald-100 text-emerald-900 border border-emerald-300">
          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
          VERIFIED
        </span>
      );
    }
    if (item.verification_status === "EXPIRED" || item.verification_status === "INACTIVE") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-orange-100 text-orange-900 border border-orange-300">
          <Clock className="w-3 h-3 text-orange-600" />
          {item.verification_status}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
        UNVERIFIED
      </span>
    );
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden mb-8">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 text-white px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold tracking-tight">
              Officer Verification Intelligence & Review Queue
            </h2>
            <span className="bg-amber-400/20 text-amber-300 text-xs px-2 py-0.5 rounded font-mono font-medium border border-amber-400/30">
              PHASE 8.4 DECISION SUPPORT
            </span>
          </div>
          <p className="text-xs text-slate-300 mt-1">
            Authoritative source facts, temporal provenance, cross-source contradictions, and debarment intelligence for procurement officer sign-off.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              loadReviewQueue();
              if (selectedBidderId) loadSummary(selectedBidderId);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs text-white font-medium transition"
          >
            <RotateCw className="w-3.5 h-3.5" />
            Refresh
          </button>
          <button
            onClick={openHistory}
            disabled={!selectedBidderId}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-xs font-bold text-white shadow-sm transition"
          >
            <History className="w-3.5 h-3.5" />
            Verification History
          </button>
        </div>
      </div>

      {/* Review Queue Bar */}
      {queue && queue.items.length > 0 && (
        <div className="bg-amber-50/70 border-b border-amber-200/80 px-6 py-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <AlertOctagon className="w-4 h-4 text-amber-700" />
              <span className="text-xs font-bold text-amber-900 uppercase tracking-wider">
                Action Required: {queue.total_queued} Bidder{queue.total_queued > 1 ? "s" : ""} in Review Queue
              </span>
            </div>
            <span className="text-xs text-amber-800">
              Human review required before qualification or award
            </span>
          </div>

          <div className="flex flex-wrap gap-2">
            {queue.items.map((item) => {
              const isSelected = item.bidder_id === selectedBidderId;
              const isHigh = item.overall_risk_state === "HIGH";
              return (
                <button
                  key={item.bidder_id}
                  onClick={() => handleSelectBidder(item.bidder_id)}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition border ${
                    isSelected
                      ? "bg-blue-900 text-white border-blue-950 shadow-xs"
                      : isHigh
                      ? "bg-red-50 text-red-900 border-red-200 hover:bg-red-100"
                      : "bg-white text-slate-800 border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <span className="font-semibold">{item.company_name}</span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                      isSelected
                        ? "bg-white/20 text-white"
                        : isHigh
                        ? "bg-red-200 text-red-900"
                        : "bg-amber-100 text-amber-900"
                    }`}
                  >
                    {item.overall_risk_state}
                  </span>
                  {item.debarred && (
                    <span className="bg-red-600 text-white px-1.5 py-0.2 rounded text-[10px] font-bold">
                      DEBARRED
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="p-6">
        {loading && (
          <div className="py-12 text-center text-slate-500">
            <RotateCw className="w-6 h-6 animate-spin mx-auto text-blue-600 mb-2" />
            <p className="text-sm font-medium">Aggregating verification intelligence & risk provenance...</p>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 text-sm flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
            <div>
              <p className="font-bold">Error Loading Intelligence View</p>
              <p className="text-xs mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {!loading && !error && summary && (
          <div className="space-y-6">
            {/* Top Stat Row: Bidder, Score, Overall Risk, Debarment State */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Card 1: Selected Enterprise */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Target Enterprise
                </p>
                <h3 className="text-sm font-bold text-slate-900 mt-1 truncate">
                  {summary.company_name}
                </h3>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  ID: {summary.bidder_id.slice(0, 8)}...
                </p>
                <div className="mt-2 text-xs text-slate-600 flex items-center gap-1">
                  <span>As of Date:</span>
                  <span className="font-mono font-medium text-slate-800">
                    {summary.as_of_date || "Not Specified (Unverified)"}
                  </span>
                </div>
              </div>

              {/* Card 2: 100-Point Score (Phase 6.4 Protected) */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Compliance Score
                </p>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-2xl font-black text-slate-900">
                    {summary.base_compliance_score.toFixed(1)}
                  </span>
                  <span className="text-xs font-semibold text-slate-500">/ 100.0</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-2 text-[10px] text-slate-600">
                  <span>Tender: {summary.score_breakdown.tender_compliance.toFixed(1)}/50</span>
                  <span>Statutory: {summary.score_breakdown.statutory_consistency.toFixed(1)}/20</span>
                  <span>Evidence: {summary.score_breakdown.evidence_completeness.toFixed(1)}/15</span>
                  <span>Contra: {summary.score_breakdown.contradiction_score.toFixed(1)}/15</span>
                </div>
              </div>

              {/* Card 3: Overall Risk State */}
              <div
                className={`rounded-lg p-4 border ${
                  summary.overall_risk_state === "HIGH"
                    ? "bg-red-50/80 border-red-200"
                    : summary.overall_risk_state === "MEDIUM"
                    ? "bg-amber-50/80 border-amber-200"
                    : "bg-emerald-50/80 border-emerald-200"
                }`}
              >
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Assessed Risk State
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={`text-2xl font-black ${
                      summary.overall_risk_state === "HIGH"
                        ? "text-red-700"
                        : summary.overall_risk_state === "MEDIUM"
                        ? "text-amber-700"
                        : "text-emerald-700"
                    }`}
                  >
                    {summary.overall_risk_state}
                  </span>
                  {summary.officer_review_required && (
                    <span className="px-2 py-0.5 bg-amber-200 text-amber-900 rounded font-bold text-[10px]">
                      REVIEW REQUIRED
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-600 mt-2">
                  {summary.overall_risk_state === "HIGH"
                    ? "Adverse findings detected. Sign-off strictly required."
                    : "Within tolerable procurement compliance threshold."}
                </p>
              </div>

              {/* Card 4: Debarment State (Orthogonal) */}
              <div
                className={`rounded-lg p-4 border ${
                  summary.debarment_state.is_debarred
                    ? "bg-red-100/90 border-red-300"
                    : "bg-emerald-50/80 border-emerald-200"
                }`}
              >
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Central Debarment Check
                </p>
                <div className="flex items-center gap-1.5 mt-1">
                  {summary.debarment_state.is_debarred ? (
                    <>
                      <XCircle className="w-5 h-5 text-red-700" />
                      <span className="text-base font-black text-red-800">
                        ACTIVE DEBARMENT
                      </span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-5 h-5 text-emerald-700" />
                      <span className="text-base font-bold text-emerald-800">
                        NOT DEBARRED
                      </span>
                    </>
                  )}
                </div>
                <p className="text-[11px] text-slate-600 mt-2 truncate">
                  {summary.debarment_state.is_debarred
                    ? `Order: ${summary.debarment_state.order_number || "Active on record"}`
                    : `Status: ${summary.debarment_state.temporal_status}`}
                </p>
              </div>
            </div>

            {/* 11 Statutory Sources Status Grid */}
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="bg-slate-100 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-slate-700" />
                  <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Statutory Source Health & Verification Provenance (All 11 Authorities)
                  </span>
                </div>
                <span className="text-[11px] text-slate-500 font-medium">
                  Technical failure != Bidder non-compliance
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 p-4 bg-slate-50/50">
                {Object.entries(summary.source_statuses).map(([authKey, item]) => (
                  <div
                    key={authKey}
                    className="bg-white border border-slate-200 rounded-lg p-3 hover:border-blue-300 transition shadow-2xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="font-bold text-xs text-slate-900 block truncate">
                          {item.source_name}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {authKey}
                        </span>
                      </div>
                      <div>{getSourceStatusBadge(item)}</div>
                    </div>

                    <div className="mt-2 pt-2 border-t border-slate-100 space-y-1 text-[11px] text-slate-600">
                      {item.query_identifier && (
                        <div className="flex justify-between">
                          <span className="text-slate-400">Query ID:</span>
                          <span className="font-mono text-slate-800 font-medium truncate max-w-[150px]">
                            {item.query_identifier}
                          </span>
                        </div>
                      )}
                      {item.validity_end && (
                        <div className="flex justify-between">
                          <span className="text-slate-400">Expiry Date:</span>
                          <span className="font-medium text-slate-700">{item.validity_end}</span>
                        </div>
                      )}
                      {item.retrieved_at && (
                        <div className="flex justify-between text-[10px] text-slate-400">
                          <span>Retrieved:</span>
                          <span>{new Date(item.retrieved_at).toLocaleString()}</span>
                        </div>
                      )}
                      {item.previous_successful_result && (
                        <div className="mt-1.5 p-1.5 rounded bg-blue-50/70 border border-blue-200 text-[10px] text-blue-900">
                          <span className="font-bold">Prior Run:</span>{" "}
                          {item.previous_successful_result.verification_status} (
                          {new Date(
                            item.previous_successful_result.retrieved_at
                          ).toLocaleDateString()}
                          )
                        </div>
                      )}
                      {item.is_technical_failure && item.error_message && (
                        <div className="mt-1 text-[10px] text-amber-800 bg-amber-50 p-1 rounded border border-amber-200">
                          {item.error_message}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Why Review? Structured Risk Reasons */}
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="bg-slate-100 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-slate-700" />
                  <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Structured Risk Reasons & Verification Discrepancies ({summary.risk_reasons.length})
                  </span>
                </div>
                <span className="text-[11px] text-slate-500">
                  Every reason is grounded in factual evidence
                </span>
              </div>

              {summary.risk_reasons.length === 0 ? (
                <div className="p-6 text-center text-slate-500 bg-white">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-1" />
                  <p className="text-sm font-bold text-slate-700">No Risk Triggers Detected</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Bidder has consistent statutory records, zero debarments, and compliant documentation.
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-200 bg-white">
                  {summary.risk_reasons.map((reason, idx) => (
                    <div
                      key={idx}
                      className={`p-4 transition ${
                        reason.severity === "HIGH"
                          ? "hover:bg-red-50/30"
                          : "hover:bg-amber-50/30"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider ${
                                reason.severity === "HIGH"
                                  ? "bg-red-100 text-red-900 border border-red-200"
                                  : "bg-amber-100 text-amber-900 border border-amber-200"
                              }`}
                            >
                              {reason.severity}
                            </span>
                            <span className="text-xs font-bold text-slate-900">
                              {reason.title}
                            </span>
                            <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                              {reason.reason_code}
                            </span>
                          </div>
                          <p className="text-xs text-slate-700 leading-relaxed">
                            {reason.explanation}
                          </p>
                        </div>

                        <div className="text-right shrink-0">
                          <span className="inline-block text-[11px] font-medium text-slate-500 bg-slate-50 px-2 py-1 rounded border border-slate-200">
                            {reason.source_type} : {reason.source_name}
                          </span>
                          {reason.clause_code && (
                            <div className="text-[10px] font-mono text-blue-700 mt-1 font-semibold">
                              Clause: {reason.clause_code}
                            </div>
                          )}
                          {reason.evidence_reference && (
                            <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                              Ref: {reason.evidence_reference}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Mandatory Disclaimer */}
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-500 text-[11px] flex items-start gap-2">
              <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
              <span>{summary.disclaimer}</span>
            </div>
          </div>
        )}
      </div>

      {/* Append-Only Verification History Drawer / Modal */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden text-slate-900">
            {/* Modal Header */}
            <div className="bg-slate-900 text-white px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="w-5 h-5 text-amber-400" />
                <div>
                  <h3 className="font-bold text-sm">
                    Append-Only Statutory Verification History
                  </h3>
                  <p className="text-xs text-slate-400">
                    Immutable execution audit trail for {summary?.company_name || selectedBidderId}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setHistoryOpen(false)}
                className="text-slate-400 hover:text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 divide-y divide-slate-100 space-y-4">
              {historyLoading && (
                <div className="py-12 text-center text-slate-500">
                  <RotateCw className="w-6 h-6 animate-spin mx-auto text-blue-600 mb-2" />
                  <p className="text-sm">Fetching historical audit records...</p>
                </div>
              )}

              {!historyLoading && (!history || history.history.length === 0) && (
                <div className="py-12 text-center text-slate-500">
                  <History className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="text-sm font-semibold">No statutory verification executions recorded yet.</p>
                </div>
              )}

              {!historyLoading &&
                history &&
                history.history.map((h, i) => (
                  <div key={h.id || i} className="pt-4 first:pt-0">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-slate-900">
                          {h.source_name}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          ({h.authority})
                        </span>
                        {h.is_latest && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-extrabold bg-blue-100 text-blue-800 border border-blue-200">
                            LATEST ATTEMPT
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-slate-500">
                          {new Date(h.retrieved_at).toLocaleString()}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-bold ${
                            h.verification_status === "VERIFIED"
                              ? "bg-emerald-100 text-emerald-800"
                              : h.connection_status !== "SUCCESS"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-slate-100 text-slate-700"
                          }`}
                        >
                          {h.connection_status === "SUCCESS"
                            ? h.verification_status
                            : h.connection_status}
                        </span>
                      </div>
                    </div>

                    <div className="mt-2 text-[11px] text-slate-600 grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50 p-2.5 rounded border border-slate-200 font-mono">
                      <div>
                        <span className="text-slate-400 block text-[10px]">Queried ID</span>
                        <span className="text-slate-800 truncate block">
                          {h.query_identifier} ({h.identifier_type})
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px]">As of Date</span>
                        <span className="text-slate-800">
                          {h.as_of_date || "Unspecified"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px]">Execution Time</span>
                        <span className="text-slate-800">
                          {h.execution_time_ms.toFixed(1)} ms
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px]">Batch UUID</span>
                        <span className="text-slate-800 truncate block">
                          {h.verification_id.slice(0, 8)}...
                        </span>
                      </div>
                    </div>

                    {h.error_message && (
                      <p className="mt-1.5 text-xs text-red-600 bg-red-50 p-2 rounded border border-red-100">
                        {h.error_message}
                      </p>
                    )}
                  </div>
                ))}
            </div>

            {/* Modal Footer */}
            <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 flex justify-between items-center text-xs text-slate-500">
              <span>{history?.history.length || 0} Total Historical Executions Recorded</span>
              <button
                onClick={() => setHistoryOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-medium transition"
              >
                Close History
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
