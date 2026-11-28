"use client";

import { useCallback, useEffect, useState } from "react";
import {
  assignTenderReviewer,
  fetchOrganizationMembers,
  fetchTenderReviewHistory,
  fetchTenderLensReviewQueue,
  fetchTenderReviewWorkload,
  submitTenderReviewDecision,
} from "@/lib/api-client";
import {
  OrganizationMember,
  ReviewDecisionRecord,
  ReviewDecisionType,
  ReviewQueueItem,
  ReviewWorkloadSummary,
} from "@/lib/types";
import { useAuth } from "@/context/AuthContext";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  History,
  RefreshCw,
  UserCheck,
} from "lucide-react";

export function TenderReviewWorkspace({ tenderId }: { tenderId: string }) {
  const { hasPermission } = useAuth();
  const canDecide = hasPermission("evaluation:override");
  const canAssign = hasPermission("user:manage");

  const [workload, setWorkload] = useState<ReviewWorkloadSummary | null>(null);
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [history, setHistory] = useState<ReviewDecisionRecord[]>([]);
  const [reviewers, setReviewers] = useState<OrganizationMember[]>([]);
  const [assigneeDrafts, setAssigneeDrafts] = useState<Record<string, string>>({});
  const [objectFilter, setObjectFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [rationaleMap, setRationaleMap] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadReviewWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [wl, q, hist, membersRes] = await Promise.all([
        fetchTenderReviewWorkload(tenderId),
        fetchTenderLensReviewQueue(tenderId, {
          object_type: objectFilter !== "ALL" ? objectFilter : undefined,
          status: statusFilter !== "ALL" ? statusFilter : undefined,
          limit: 50,
          offset: 0,
        }),
        fetchTenderReviewHistory(tenderId),
        canAssign
          ? fetchOrganizationMembers({ isActive: true, limit: 100 }).catch(() => null)
          : Promise.resolve(null),
      ]);
      setWorkload(wl);
      setItems(q.items);
      setHistory(hist.items);
      if (membersRes) {
        const eligible = membersRes.items.filter(
          (m) =>
            m.is_active &&
            m.roles.some((r) => ["ORG_ADMIN", "PROCUREMENT_OFFICER", "SUPER_ADMIN"].includes(r))
        );
        setReviewers(eligible);
      }
      const nextDrafts: Record<string, string> = {};
      for (const it of q.items) {
        nextDrafts[it.object_id] = it.assigned_reviewer_id || "";
      }
      setAssigneeDrafts(nextDrafts);
    } catch (err: any) {
      setError(err?.message || "Failed to load human review workspace.");
    } finally {
      setLoading(false);
    }
  }, [tenderId, objectFilter, statusFilter, canAssign]);

  useEffect(() => {
    loadReviewWorkspace();
  }, [loadReviewWorkspace]);

  const handleDecision = async (
    item: ReviewQueueItem,
    decisionType: Exclude<ReviewDecisionType, "ASSIGN">
  ) => {
    const rationale = (rationaleMap[item.object_id] || "").trim();
    if (["REJECT", "DISMISS", "RESOLVE"].includes(decisionType)) {
      if (!confirm(`Confirm ${decisionType} decision on ${item.title}?`)) {
        return;
      }
    }
    setSubmittingId(item.object_id);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await submitTenderReviewDecision(tenderId, {
        object_type: item.object_type,
        object_id: item.object_id,
        decision_type: decisionType,
        expected_version: item.review_version,
        rationale: rationale || undefined,
      });
      setSuccessMsg(
        `Recorded ${decisionType} -> ${res.new_status} (v${res.review_version}).`
      );
      await loadReviewWorkspace();
    } catch (err: any) {
      setError(err?.message || "Failed to submit review decision.");
    } finally {
      setSubmittingId(null);
    }
  };

  const handleAssign = async (item: ReviewQueueItem) => {
    const selectedId = assigneeDrafts[item.object_id] || null;
    setSubmittingId(item.object_id);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await assignTenderReviewer(tenderId, {
        object_type: item.object_type,
        object_id: item.object_id,
        assignee_user_id: selectedId,
        expected_version: item.review_version,
      });
      setSuccessMsg(
        selectedId
          ? `Assigned reviewer for ${item.title} (v${res.review_version}).`
          : `Unassigned reviewer for ${item.title} (v${res.review_version}).`
      );
      await loadReviewWorkspace();
    } catch (err: any) {
      setError(err?.message || "Failed to assign reviewer.");
    } finally {
      setSubmittingId(null);
    }
  };

  const resolveReviewerLabel = (reviewerId?: string | null) => {
    if (!reviewerId) return "Unassigned";
    const found = reviewers.find((r) => r.id === reviewerId);
    return found ? `${found.full_name} (${found.roles.join(", ")})` : reviewerId.slice(0, 8);
  };

  return (
    <section className="bg-white border border-[#E9EEF5] rounded-xl shadow-xs overflow-hidden">
      <div className="px-5 py-4 bg-[#101C32] text-white flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center space-x-2">
            <ClipboardCheck className="w-4 h-4 text-[#EAF2FA]" />
            <h2 className="text-sm font-semibold tracking-tight">
              Human Review &amp; Decision Workspace
            </h2>
          </div>
          <p className="text-xs text-[#EAF2FA]/80 mt-0.5">
            Procurement officers own every confirmation, rejection, conflict resolution, and evidence sign-off.
          </p>
        </div>

        <button
          type="button"
          onClick={loadReviewWorkspace}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/10 hover:bg-white/20 text-white flex items-center space-x-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Queue</span>
        </button>
      </div>

      {workload && (
        <div className="px-5 py-3 bg-[#F8FAFC] border-b border-[#E9EEF5] flex flex-wrap gap-2 text-xs">
          <span className="px-2.5 py-1 rounded bg-amber-50 text-[#D99A35] border border-amber-200 font-semibold">
            Pending: {workload.pending_count}
          </span>
          <span className="px-2.5 py-1 rounded bg-emerald-50 text-[#16856B] border border-emerald-200 font-semibold">
            Confirmed: {workload.confirmed_count}
          </span>
          <span className="px-2.5 py-1 rounded bg-rose-50 text-[#DC3545] border border-rose-200 font-semibold">
            Rejected: {workload.rejected_count}
          </span>
          <span className="px-2.5 py-1 rounded bg-[#EAF2FA] text-[#1769AA] font-semibold">
            Needs Clarification: {workload.needs_clarification_count}
          </span>
          <span className="px-2.5 py-1 rounded bg-white border border-[#E9EEF5] text-[#101C32] font-medium">
            Conflicts: {workload.conflict_count} · Evidence: {workload.evidence_count} · Unassigned: {workload.unassigned_count}
          </span>
        </div>
      )}

      {successMsg && (
        <div className="px-5 py-2.5 bg-emerald-50 border-b border-emerald-200 text-xs text-[#16856B] flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="px-5 py-2.5 bg-rose-50 border-b border-rose-200 text-xs text-[#DC3545] flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="px-5 py-3 border-b border-[#E9EEF5] flex flex-wrap items-center gap-2">
        <select
          value={objectFilter}
          onChange={(e) => setObjectFilter(e.target.value)}
          className="bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
          aria-label="Filter review queue by object type"
        >
          <option value="ALL">All Review Objects</option>
          <option value="REQUIREMENT">Requirements</option>
          <option value="CONFLICT">Conflicts</option>
          <option value="EVIDENCE">Expected Evidence</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
          aria-label="Filter review queue by status"
        >
          <option value="ALL">All Statuses</option>
          <option value="DRAFT">DRAFT</option>
          <option value="NEEDS_REVIEW">NEEDS_REVIEW</option>
          <option value="DETECTED">DETECTED</option>
          <option value="SUGGESTED">SUGGESTED</option>
          <option value="CONFIRMED">CONFIRMED</option>
          <option value="REJECTED">REJECTED</option>
          <option value="NEEDS_CLARIFICATION">NEEDS_CLARIFICATION</option>
          <option value="DISMISSED">DISMISSED</option>
          <option value="RESOLVED">RESOLVED</option>
        </select>
      </div>

      <div className="divide-y divide-[#E9EEF5]">
        {loading ? (
          <div className="p-6 text-center text-xs text-[#6B7C93]">
            Loading review queue...
          </div>
        ) : items.length === 0 ? (
          <div className="p-6 text-center text-xs text-[#6B7C93]">
            No review items match the selected filters.
          </div>
        ) : (
          items.map((item) => {
            const isReviewed = ["CONFIRMED", "REJECTED", "DISMISSED", "RESOLVED"].includes(
              item.status
            );
            return (
              <div key={`${item.object_type}-${item.object_id}`} className="p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-[#101C32] text-white">
                      {item.object_type}
                    </span>
                    <span className="text-xs font-semibold text-[#1769AA]">
                      {item.title}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-[#EAF2FA] text-[#101C32]">
                      {item.status} (v{item.review_version})
                    </span>
                    {item.provenance_status && (
                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-[#2B3A55]">
                        Provenance: {item.provenance_status}
                      </span>
                    )}
                  </div>
                  {item.source_page_number && (
                    <span className="text-[11px] text-[#6B7C93]">
                      Page {item.source_page_number}
                    </span>
                  )}
                </div>

                <p className="text-xs text-[#2B3A55]">{item.summary}</p>

                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#6B7C93]">
                  <span className="inline-flex items-center space-x-1">
                    <UserCheck className="w-3.5 h-3.5 text-[#1769AA]" />
                    <span>
                      Reviewer: <strong className="text-[#101C32]">{resolveReviewerLabel(item.assigned_reviewer_id)}</strong>
                    </span>
                  </span>

                  {canAssign && (
                    <div className="flex items-center gap-1.5">
                      <select
                        value={assigneeDrafts[item.object_id] ?? ""}
                        onChange={(e) =>
                          setAssigneeDrafts((prev) => ({
                            ...prev,
                            [item.object_id]: e.target.value,
                          }))
                        }
                        aria-label={`Select reviewer for ${item.title}`}
                        disabled={submittingId === item.object_id}
                        className="bg-white border border-[#E9EEF5] rounded px-2 py-1 text-[11px] text-[#101C32]"
                      >
                        <option value="">Unassigned</option>
                        {reviewers.length === 0 ? (
                          <option value="" disabled>
                            No eligible reviewers found
                          </option>
                        ) : (
                          reviewers.map((rev) => (
                            <option key={rev.id} value={rev.id}>
                              {rev.full_name} ({rev.roles.join(", ")})
                            </option>
                          ))
                        )}
                      </select>
                      <button
                        type="button"
                        disabled={submittingId === item.object_id}
                        onClick={() => handleAssign(item)}
                        className="px-2 py-1 rounded text-[11px] font-semibold bg-[#101C32] text-white hover:opacity-90 disabled:opacity-50"
                      >
                        {item.assigned_reviewer_id ? "Reassign" : "Assign"}
                      </button>
                    </div>
                  )}
                </div>

                {canDecide && (
                  <div className="flex flex-col sm:flex-row sm:items-center gap-2 pt-1">
                    <input
                      type="text"
                      value={rationaleMap[item.object_id] || ""}
                      onChange={(e) =>
                        setRationaleMap((prev) => ({
                          ...prev,
                          [item.object_id]: e.target.value,
                        }))
                      }
                      placeholder="Decision rationale (required for Reject/Dismiss/Resolve/Clarify/Reopen)..."
                      aria-label={`Decision rationale for ${item.title}`}
                      className="flex-1 bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {!isReviewed && (
                        <button
                          type="button"
                          disabled={submittingId === item.object_id}
                          onClick={() => handleDecision(item, "CONFIRM")}
                          className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#16856B] text-white hover:opacity-90 disabled:opacity-50"
                        >
                          Confirm
                        </button>
                      )}
                      {item.object_type === "REQUIREMENT" && !isReviewed && (
                        <>
                          <button
                            type="button"
                            disabled={submittingId === item.object_id}
                            onClick={() => handleDecision(item, "REQUEST_CLARIFICATION")}
                            className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#D99A35] text-white hover:opacity-90 disabled:opacity-50"
                          >
                            Clarify
                          </button>
                          <button
                            type="button"
                            disabled={submittingId === item.object_id}
                            onClick={() => handleDecision(item, "REJECT")}
                            className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#DC3545] text-white hover:opacity-90 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {item.object_type === "CONFLICT" && item.status !== "DISMISSED" && item.status !== "RESOLVED" && (
                        <>
                          <button
                            type="button"
                            disabled={submittingId === item.object_id}
                            onClick={() => handleDecision(item, "DISMISS")}
                            className="px-2.5 py-1 rounded text-[11px] font-semibold bg-slate-600 text-white hover:opacity-90 disabled:opacity-50"
                          >
                            Dismiss
                          </button>
                          <button
                            type="button"
                            disabled={submittingId === item.object_id}
                            onClick={() => handleDecision(item, "RESOLVE")}
                            className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#1769AA] text-white hover:opacity-90 disabled:opacity-50"
                          >
                            Resolve
                          </button>
                        </>
                      )}
                      {item.object_type === "EVIDENCE" && !isReviewed && (
                        <button
                          type="button"
                          disabled={submittingId === item.object_id}
                          onClick={() => handleDecision(item, "REJECT")}
                          className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#DC3545] text-white hover:opacity-90 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      )}
                      {isReviewed && (
                        <button
                          type="button"
                          disabled={submittingId === item.object_id}
                          onClick={() => handleDecision(item, "REOPEN")}
                          className="px-2.5 py-1 rounded text-[11px] font-semibold bg-[#D99A35] text-white hover:opacity-90 disabled:opacity-50"
                        >
                          Reopen
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {history.length > 0 && (
        <div className="px-5 py-3 bg-[#F8FAFC] border-t border-[#E9EEF5]">
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-[#101C32] mb-2">
            <History className="w-3.5 h-3.5 text-[#1769AA]" />
            <span>Recent Append-Only Decision History ({history.length})</span>
          </div>
          <ul className="space-y-1 text-[11px] text-[#2B3A55]">
            {history.slice(0, 8).map((h) => (
              <li key={h.id} className="flex flex-wrap justify-between gap-2">
                <span>
                  <strong>{h.object_type}</strong> · {h.decision_type} ({h.previous_status} → {h.new_status}, v{h.object_version}): &ldquo;{h.rationale}&rdquo;
                </span>
                <span className="text-[#6B7C93]">
                  {new Date(h.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
