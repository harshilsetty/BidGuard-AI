"use client";

import { useCallback, useEffect, useState } from "react";
import {
  extractDocumentRequirements,
  fetchRequirementEvidenceMappings,
  fetchRequirementJobStatus,
  fetchRequirementProvenance,
  fetchTenderDocuments,
  fetchTenderRequirements,
  generateRequirementEvidenceMappings,
} from "@/lib/api-client";
import {
  TenderDocument,
  TenderProcessingJob,
  TenderRequirement,
  TenderRequirementEvidence,
  TenderRequirementProvenance,
} from "@/lib/types";
import { useAuth } from "@/context/AuthContext";
import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  Loader2,
  Sparkles,
  BookOpen,
} from "lucide-react";

const TAXONOMY_CATEGORIES = [
  { code: "ALL", label: "All Categories" },
  { code: "ELIG", label: "ELIG · Eligibility" },
  { code: "TECH", label: "TECH · Technical" },
  { code: "FIN", label: "FIN · Financial" },
  { code: "STAT", label: "STAT · Statutory" },
  { code: "EXP", label: "EXP · Experience" },
  { code: "DOC", label: "DOC · Documentary" },
  { code: "DEL", label: "DEL · Delivery & SLA" },
  { code: "SUB", label: "SUB · Submission" },
  { code: "DATE", label: "DATE · Deadlines" },
  { code: "PREF", label: "PREF · Preferences" },
  { code: "UNCLASSIFIED", label: "Unclassified" },
];

export function TenderRequirementsPanel({ tenderId }: { tenderId: string }) {
  const { hasPermission } = useAuth();
  const canExtract = hasPermission("tender:update");

  const [documents, setDocuments] = useState<TenderDocument[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [requirements, setRequirements] = useState<TenderRequirement[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeJob, setActiveJob] = useState<TenderProcessingJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [mandatoryFilter, setMandatoryFilter] = useState("ALL");
  const [reviewFilter, setReviewFilter] = useState("ALL");
  const [selectedReq, setSelectedReq] = useState<TenderRequirement | null>(null);
  const [provenance, setProvenance] = useState<TenderRequirementProvenance | null>(null);
  const [evidenceList, setEvidenceList] = useState<TenderRequirementEvidence[]>([]);
  const [inspectLoading, setInspectLoading] = useState(false);

  const handleInspect = async (req: TenderRequirement) => {
    if (selectedReq?.id === req.id) {
      setSelectedReq(null);
      setProvenance(null);
      setEvidenceList([]);
      return;
    }
    setSelectedReq(req);
    setInspectLoading(true);
    try {
      const [prov, ev] = await Promise.all([
        fetchRequirementProvenance(tenderId, req.id),
        fetchRequirementEvidenceMappings(tenderId, req.id),
      ]);
      setProvenance(prov);
      setEvidenceList(ev.items);
    } catch {
      setProvenance(null);
      setEvidenceList([]);
    } finally {
      setInspectLoading(false);
    }
  };

  const handleGenerateEvidence = async (reqId: string) => {
    setInspectLoading(true);
    try {
      const ev = await generateRequirementEvidenceMappings(tenderId, reqId);
      setEvidenceList(ev.items);
    } finally {
      setInspectLoading(false);
    }
  };

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docs, reqsRes] = await Promise.all([
        fetchTenderDocuments(tenderId),
        fetchTenderRequirements(tenderId, {
          primary_category: categoryFilter !== "ALL" ? categoryFilter : undefined,
          mandatory_status: mandatoryFilter !== "ALL" ? mandatoryFilter : undefined,
          review_status: reviewFilter !== "ALL" ? reviewFilter : undefined,
          limit: 100,
          offset: 0,
        }),
      ]);
      setDocuments(docs);
      const readyDoc = docs.find((d) => d.processing_status === "READY");
      if (!selectedDocId && readyDoc) {
        setSelectedDocId(readyDoc.id);
      }
      setRequirements(reqsRes.items);
      setTotal(reqsRes.total);
    } catch (err: any) {
      setError(err?.message || "Failed to load TenderLens requirements.");
    } finally {
      setLoading(false);
    }
  }, [tenderId, categoryFilter, mandatoryFilter, reviewFilter, selectedDocId]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  // Bounded polling while a requirement extraction job is active
  useEffect(() => {
    if (
      !activeJob ||
      !["QUEUED", "RUNNING", "RETRY_WAIT"].includes(activeJob.status)
    ) {
      return;
    }

    let cancelled = false;
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      if (attempts > 45 || cancelled) {
        clearInterval(timer);
        return;
      }
      try {
        const latest = await fetchRequirementJobStatus(tenderId, activeJob.id);
        if (cancelled) return;
        setActiveJob(latest);
        if (["SUCCEEDED", "FAILED"].includes(latest.status)) {
          clearInterval(timer);
          await loadWorkspace();
        }
      } catch {
        clearInterval(timer);
      }
    }, 2000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeJob, tenderId, loadWorkspace]);

  const handleStartExtraction = async () => {
    if (!selectedDocId) return;
    setError(null);
    try {
      const job = await extractDocumentRequirements(tenderId, selectedDocId);
      setActiveJob(job);
    } catch (err: any) {
      setError(err?.message || "Failed to enqueue requirement extraction.");
    }
  };

  const docNameMap = new Map(documents.map((d) => [d.id, d.original_filename]));
  const readyDocuments = documents.filter((d) => d.processing_status === "READY");
  const draftCount = requirements.filter((r) => r.review_status === "DRAFT").length;
  const needsReviewCount = requirements.filter(
    (r) => r.review_status === "NEEDS_REVIEW"
  ).length;

  return (
    <section className="bg-white border border-[#E9EEF5] rounded-xl shadow-xs overflow-hidden">
      <div className="px-5 py-4 bg-[#101C32] text-white flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-[#EAF2FA]" />
            <h2 className="text-sm font-semibold tracking-tight">
              TenderLens Requirement Intelligence (Drafts)
            </h2>
          </div>
          <p className="text-xs text-[#EAF2FA]/80 mt-0.5">
            AI proposes source-grounded draft requirements across 10 procurement
            categories. Human review is required before confirmation.
          </p>
        </div>

        {canExtract && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="bg-white/10 border border-white/20 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none"
              aria-label="Select processed document for requirement extraction"
            >
              {readyDocuments.length === 0 ? (
                <option value="" className="text-[#101C32]">
                  No READY documents
                </option>
              ) : (
                readyDocuments.map((d) => (
                  <option key={d.id} value={d.id} className="text-[#101C32]">
                    {d.original_filename} ({d.total_pages ?? 0}p)
                  </option>
                ))
              )}
            </select>
            <button
              type="button"
              onClick={handleStartExtraction}
              disabled={!selectedDocId || (activeJob !== null && ["QUEUED", "RUNNING", "RETRY_WAIT"].includes(activeJob.status))}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#145A92] disabled:opacity-50 text-white transition flex items-center space-x-1.5"
            >
              <FileSearch className="w-3.5 h-3.5" />
              <span>Extract Requirements</span>
            </button>
          </div>
        )}
      </div>

      {/* Job Status Banner */}
      {activeJob && (
        <div className="px-5 py-3 bg-[#EAF2FA] border-b border-[#E9EEF5] flex flex-wrap items-center justify-between gap-2 text-xs text-[#101C32]">
          <div className="flex items-center space-x-2">
            {["QUEUED", "RUNNING", "RETRY_WAIT"].includes(activeJob.status) ? (
              <Loader2 className="w-4 h-4 animate-spin text-[#1769AA]" />
            ) : activeJob.status === "SUCCEEDED" ? (
              <CheckCircle2 className="w-4 h-4 text-[#16856B]" />
            ) : (
              <AlertCircle className="w-4 h-4 text-[#DC3545]" />
            )}
            <span className="font-semibold">
              Job {activeJob.status} ({activeJob.current_stage} · {activeJob.progress_pct}%)
            </span>
            {activeJob.status === "SUCCEEDED" && (
              <span className="text-[#16856B] font-medium">
                · {activeJob.extracted_count ?? 0} draft requirement(s) extracted (v
                {activeJob.extraction_version ?? 1})
              </span>
            )}
            {activeJob.status === "FAILED" && activeJob.error_message && (
              <span className="text-[#DC3545]">{activeJob.error_message}</span>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="px-5 py-3 bg-rose-50 border-b border-rose-200 text-xs text-[#DC3545] flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Summary & Filters */}
      <div className="px-5 py-3 border-b border-[#E9EEF5] bg-[#F8FAFC] flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="px-2.5 py-1 rounded-md bg-white border border-[#E9EEF5] font-semibold text-[#101C32]">
            Total: {total}
          </span>
          <span className="px-2.5 py-1 rounded-md bg-[#EAF2FA] text-[#1769AA] font-semibold">
            Drafts: {draftCount}
          </span>
          <span className="px-2.5 py-1 rounded-md bg-amber-50 text-[#D99A35] border border-amber-200 font-semibold">
            Needs Review: {needsReviewCount}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
            aria-label="Filter requirements by category"
          >
            {TAXONOMY_CATEGORIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>

          <select
            value={mandatoryFilter}
            onChange={(e) => setMandatoryFilter(e.target.value)}
            className="bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
            aria-label="Filter requirements by obligation status"
          >
            <option value="ALL">All Obligations</option>
            <option value="MANDATORY">MANDATORY</option>
            <option value="OPTIONAL">OPTIONAL</option>
            <option value="UNCLEAR">UNCLEAR</option>
          </select>

          <select
            value={reviewFilter}
            onChange={(e) => setReviewFilter(e.target.value)}
            className="bg-white border border-[#E9EEF5] rounded-lg px-2.5 py-1.5 text-xs text-[#101C32]"
            aria-label="Filter requirements by review status"
          >
            <option value="ALL">All Review States</option>
            <option value="DRAFT">DRAFT</option>
            <option value="NEEDS_REVIEW">NEEDS_REVIEW</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="REJECTED">REJECTED</option>
          </select>
        </div>
      </div>

      {/* Requirements List */}
      <div className="divide-y divide-[#E9EEF5]">
        {loading ? (
          <div className="p-8 text-center text-xs text-[#6B7C93]">
            Loading extracted requirements...
          </div>
        ) : requirements.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#6B7C93]">
            No extracted requirements yet. Process a PDF to READY status and click
            &ldquo;Extract Requirements&rdquo;.
          </div>
        ) : (
          requirements.map((req) => (
            <div
              key={req.id}
              className="p-4 hover:bg-[#F8FAFC] transition flex flex-col gap-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-bold text-[#1769AA]">
                    {req.requirement_code}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-[#EAF2FA] text-[#101C32]">
                    {req.primary_category}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                      req.mandatory_status === "MANDATORY"
                        ? "bg-rose-50 text-[#DC3545] border border-rose-200"
                        : req.mandatory_status === "OPTIONAL"
                        ? "bg-emerald-50 text-[#16856B] border border-emerald-200"
                        : "bg-amber-50 text-[#D99A35] border border-amber-200"
                    }`}
                  >
                    {req.mandatory_status}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                      req.review_status === "NEEDS_REVIEW"
                        ? "bg-amber-50 text-[#D99A35] border border-amber-200"
                        : req.review_status === "CONFIRMED"
                        ? "bg-emerald-50 text-[#16856B] border border-emerald-200"
                        : "bg-slate-100 text-[#2B3A55]"
                    }`}
                  >
                    {req.review_status}
                  </span>
                </div>

                <div className="flex items-center space-x-3 text-[11px] text-[#6B7C93]">
                  <span>
                    {docNameMap.get(req.source_document_id) ?? "Source Doc"} · Page{" "}
                    {req.source_page_number}
                  </span>
                  <span>
                    Conf: {Math.round(req.extraction_confidence * 100)}%
                  </span>
                  <button
                    type="button"
                    onClick={() => handleInspect(req)}
                    className="text-[#1769AA] hover:underline font-semibold flex items-center space-x-1"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    <span>{selectedReq?.id === req.id ? "Hide Source" : "Inspect"}</span>
                  </button>
                </div>
              </div>

              <p className="text-xs font-semibold text-[#101C32]">
                {req.normalized_statement}
              </p>
              <p className="text-xs text-[#2B3A55]">
                {req.explanatory_interpretation}
              </p>

              {selectedReq?.id === req.id && (
                <div className="mt-2 p-3 rounded-lg bg-[#EAF2FA]/60 border border-[#E9EEF5] text-xs space-y-2">
                  <div>
                    <span className="font-semibold text-[#101C32]">
                      Source Quotation ({provenance ? provenance.verification_status : req.source_quote_verified ? "VERIFIED" : "UNVERIFIED"}):{" "}
                    </span>
                    <span className="italic text-[#2B3A55]">
                      &ldquo;{req.source_text}&rdquo;
                    </span>
                    {provenance?.verification_detail && (
                      <p className="text-[11px] text-[#6B7C93] mt-0.5">{provenance.verification_detail}</p>
                    )}
                  </div>
                  {(req.numeric_value || req.unit || req.currency || req.period_or_validity) && (
                    <div className="text-[#2B3A55]">
                      <span className="font-semibold text-[#101C32]">Threshold / Period: </span>
                      {[req.numeric_value, req.unit, req.currency, req.period_or_validity]
                        .filter(Boolean)
                        .join(" ")}
                    </div>
                  )}
                  <div className="pt-1 border-t border-[#E9EEF5] flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-[#101C32]">
                      Expected Bidder Evidence ({evidenceList.length})
                    </span>
                    {canExtract && (
                      <button
                        type="button"
                        onClick={() => handleGenerateEvidence(req.id)}
                        disabled={inspectLoading}
                        className="px-2.5 py-1 rounded bg-[#1769AA] text-white text-[11px] font-semibold hover:bg-[#145A92] disabled:opacity-50"
                      >
                        {inspectLoading ? "Checking..." : "Map Expected Evidence"}
                      </button>
                    )}
                  </div>
                  {evidenceList.length > 0 && (
                    <ul className="space-y-1">
                      {evidenceList.map((ev) => (
                        <li key={ev.id} className="bg-white px-2.5 py-1.5 rounded border border-[#E9EEF5] flex flex-wrap justify-between gap-2">
                          <span>
                            <strong>{ev.expected_document_name}</strong> ({ev.evidence_type}) — {ev.evidence_purpose}
                          </span>
                          <span className="text-[11px] font-semibold text-[#D99A35]">
                            {ev.mapping_status} · {Math.round(ev.confidence * 100)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
