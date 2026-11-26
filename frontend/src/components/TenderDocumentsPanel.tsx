"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Upload,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import {
  ApiError,
  fetchTenderDocuments,
  fetchTenderJobStatus,
  processTenderDocument,
  retryTenderJob,
  uploadTenderDocument,
} from "@/lib/api-client";
import type {
  TenderDocument,
  TenderDocumentRole,
  TenderProcessingJob,
} from "@/lib/types";
import { EmptyState, ErrorState, LoadingState, StatusIndicator } from "./ui/WorkspacePrimitives";

const DOCUMENT_ROLE_OPTIONS: Array<{ value: TenderDocumentRole; label: string }> = [
  { value: "PRIMARY_NIT", label: "Primary NIT" },
  { value: "TECHNICAL_SPEC", label: "Technical Specification" },
  { value: "BOQ", label: "Bill of Quantities (BoQ)" },
  { value: "CORRIGENDUM", label: "Corrigendum" },
  { value: "ANNEXURE", label: "Annexure" },
  { value: "OTHER", label: "Other Supporting PDF" },
];

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING", "RETRY_WAIT"]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function getStatusVariant(status: string): "green" | "amber" | "red" | "blue" | "neutral" {
  if (status === "READY" || status === "SUCCEEDED") return "green";
  if (status === "FAILED") return "red";
  if (status === "QUEUED" || status === "PROCESSING" || status === "RUNNING" || status === "RETRY_WAIT") {
    return "amber";
  }
  return "blue";
}

export function TenderDocumentsPanel({ tenderId }: { tenderId: string }) {
  const { hasPermission } = useAuth();
  const canManageDocs = hasPermission("tender:update");

  const [documents, setDocuments] = useState<TenderDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [documentRole, setDocumentRole] = useState<TenderDocumentRole>("ANNEXURE");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [busyDocId, setBusyDocId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await fetchTenderDocuments(tenderId);
      if (mountedRef.current) {
        setDocuments(list);
      }
    } catch (err) {
      if (mountedRef.current) {
        setLoadError(err instanceof Error ? err.message : "Failed to load tender documents.");
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [tenderId]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Bounded polling only for active jobs; cleans up on terminal state or unmount
  useEffect(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    const activeJobs = documents
      .map((d) => d.latest_job)
      .filter((j): j is TenderProcessingJob => Boolean(j && ACTIVE_STATUSES.has(j.status)));

    if (activeJobs.length === 0) {
      return;
    }

    pollTimerRef.current = setTimeout(async () => {
      if (!mountedRef.current) return;
      try {
        const updates = await Promise.all(
          activeJobs.map((j) => fetchTenderJobStatus(tenderId, j.id).catch(() => null))
        );
        if (!mountedRef.current) return;

        const updateMap = new Map<string, TenderProcessingJob>();
        for (const u of updates) {
          if (u) updateMap.set(u.tender_document_id, u);
        }

        let anyFinished = false;
        setDocuments((prev) =>
          prev.map((doc) => {
            const nextJob = updateMap.get(doc.id);
            if (!nextJob) return doc;
            if (!ACTIVE_STATUSES.has(nextJob.status)) {
              anyFinished = true;
            }
            return {
              ...doc,
              processing_status:
                nextJob.status === "SUCCEEDED"
                  ? "READY"
                  : nextJob.status === "FAILED"
                    ? "FAILED"
                    : nextJob.status === "QUEUED"
                      ? "QUEUED"
                      : "PROCESSING",
              latest_job: nextJob,
            };
          })
        );

        if (anyFinished) {
          await loadDocuments();
        }
      } catch {
        // Keep current state; user can manually refresh
      }
    }, 2500);

    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [documents, tenderId, loadDocuments]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError(null);
    setUploadSuccess(null);
    const f = e.target.files?.[0] || null;
    if (!f) {
      setSelectedFile(null);
      return;
    }
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF files (.pdf) are supported.");
      setSelectedFile(null);
      return;
    }
    setSelectedFile(f);
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (uploading) return;
    setUploadError(null);
    setUploadSuccess(null);

    if (!selectedFile) {
      setUploadError("Select a PDF file before uploading.");
      return;
    }

    setUploading(true);
    try {
      const created = await uploadTenderDocument(tenderId, selectedFile, documentRole);
      setUploadSuccess(
        `Uploaded "${created.original_filename}" (${created.document_role}, ${formatBytes(
          created.file_size_bytes
        )}).`
      );
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await loadDocuments();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setUploadError("Duplicate document: an identical PDF is already attached to this tender.");
        } else if (err.status === 413) {
          setUploadError("File exceeds the maximum allowed upload size (50 MB).");
        } else if (err.status === 422) {
          setUploadError(err.detail || "Invalid or unsupported PDF file.");
        } else {
          setUploadError(err.detail);
        }
      } else {
        setUploadError(err instanceof Error ? err.message : "Upload failed.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleStartProcessing = async (doc: TenderDocument) => {
    if (busyDocId) return;
    setActionError(null);
    setBusyDocId(doc.id);
    try {
      const job = await processTenderDocument(tenderId, doc.id);
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === doc.id ? { ...d, processing_status: "QUEUED", latest_job: job } : d
        )
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to start page extraction.");
    } finally {
      setBusyDocId(null);
    }
  };

  const handleRetryJob = async (doc: TenderDocument, jobId: string) => {
    if (busyDocId) return;
    setActionError(null);
    setBusyDocId(doc.id);
    try {
      const job = await retryTenderJob(tenderId, jobId);
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === doc.id ? { ...d, processing_status: "QUEUED", latest_job: job } : d
        )
      );
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to retry processing job.");
    } finally {
      setBusyDocId(null);
    }
  };

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-5 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-4">
        <div className="flex items-center space-x-2">
          <FileText className="w-5 h-5 text-[#1769AA]" />
          <div>
            <h2 className="text-sm font-bold text-[#101C32] uppercase tracking-wider">
              Tender Documents ({documents.length})
            </h2>
            <p className="text-xs text-slate-500">
              Tenant-isolated PDF attachments and asynchronous page/OCR extraction status.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={loadDocuments}
          disabled={loading}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-[#101C32] hover:bg-slate-50 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {canManageDocs && (
        <form
          onSubmit={handleUploadSubmit}
          className="bg-[#EAF2FA]/60 border border-blue-200/80 rounded-lg p-4 space-y-3"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
            <div className="space-y-1">
              <label
                htmlFor="tender-doc-file"
                className="block text-xs font-semibold text-[#101C32]"
              >
                PDF File (max 50 MB)
              </label>
              <input
                ref={fileInputRef}
                id="tender-doc-file"
                type="file"
                accept=".pdf,application/pdf"
                disabled={uploading}
                onChange={handleFileSelect}
                className="w-full text-xs text-slate-700 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-[#101C32] file:text-white hover:file:bg-slate-800"
              />
            </div>

            <div className="space-y-1">
              <label
                htmlFor="tender-doc-role"
                className="block text-xs font-semibold text-[#101C32]"
              >
                Document Role
              </label>
              <select
                id="tender-doc-role"
                value={documentRole}
                disabled={uploading}
                onChange={(e) => setDocumentRole(e.target.value as TenderDocumentRole)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-xs text-[#101C32]"
              >
                {DOCUMENT_ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={uploading || !selectedFile}
              className="inline-flex items-center justify-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Uploading &amp; Verifying...</span>
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5" />
                  <span>Attach PDF</span>
                </>
              )}
            </button>
          </div>

          {uploadError && (
            <div
              role="alert"
              className="p-2.5 rounded bg-red-50 border border-red-200 text-red-800 text-xs flex items-start space-x-2"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{uploadError}</span>
            </div>
          )}

          {uploadSuccess && (
            <div
              role="status"
              className="p-2.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-start space-x-2"
            >
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{uploadSuccess}</span>
            </div>
          )}
        </form>
      )}

      {actionError && (
        <div
          role="alert"
          className="p-2.5 rounded bg-red-50 border border-red-200 text-red-800 text-xs flex items-start space-x-2"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{actionError}</span>
        </div>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={loadDocuments} />
      ) : loading ? (
        <LoadingState message="Loading tender documents..." />
      ) : documents.length === 0 ? (
        <EmptyState
          title="No multi-document attachments yet"
          description="Legacy single-PDF tenders remain supported. Attach additional NIT, Technical Spec, BoQ, or Corrigendum PDFs above."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[11px]">
                <th className="py-2.5 pr-4 font-semibold">Filename</th>
                <th className="py-2.5 px-4 font-semibold">Role</th>
                <th className="py-2.5 px-4 font-semibold">Size</th>
                <th className="py-2.5 px-4 font-semibold">Pages</th>
                <th className="py-2.5 px-4 font-semibold">Processing</th>
                {canManageDocs && (
                  <th className="py-2.5 pl-4 font-semibold text-right">Actions</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {documents.map((doc) => {
                const job = doc.latest_job;
                const isJobActive = Boolean(job && ACTIVE_STATUSES.has(job.status));
                const canRetry = Boolean(
                  canManageDocs &&
                    job &&
                    job.status === "FAILED" &&
                    job.retry_count < job.max_retries
                );
                const isBusy = busyDocId === doc.id;

                return (
                  <tr key={doc.id} className="hover:bg-slate-50/60">
                    <td className="py-3 pr-4">
                      <div className="font-medium text-[#101C32]">{doc.original_filename}</div>
                      <div className="text-[11px] text-slate-400">
                        Uploaded {new Date(doc.created_at).toLocaleString()}
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-[#1769AA]">
                      {doc.document_role}
                    </td>
                    <td className="py-3 px-4 text-slate-600">{formatBytes(doc.file_size_bytes)}</td>
                    <td className="py-3 px-4 text-slate-600">{doc.total_pages ?? "—"}</td>
                    <td className="py-3 px-4 space-y-1">
                      <div className="flex items-center space-x-2">
                        <StatusIndicator
                          label={doc.processing_status}
                          variant={getStatusVariant(doc.processing_status)}
                        />
                        {job && isJobActive && (
                          <span className="text-[11px] font-mono text-slate-600">
                            {job.current_stage} ({job.progress_pct}%)
                          </span>
                        )}
                      </div>
                      {job && job.status === "FAILED" && job.error_message && (
                        <p className="text-[11px] text-red-700 max-w-xs">{job.error_message}</p>
                      )}
                    </td>
                    {canManageDocs && (
                      <td className="py-3 pl-4 text-right space-x-2">
                        {!isJobActive && doc.processing_status !== "FAILED" && (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleStartProcessing(doc)}
                            className="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-[#1769AA] hover:bg-[#13568c] text-white font-semibold transition disabled:opacity-50"
                          >
                            {isBusy ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Play className="w-3 h-3" />
                            )}
                            <span>
                              {doc.processing_status === "READY" ? "Reprocess" : "Extract Pages"}
                            </span>
                          </button>
                        )}
                        {canRetry && job && (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleRetryJob(doc, job.id)}
                            className="inline-flex items-center space-x-1 px-2.5 py-1 rounded border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 font-semibold transition disabled:opacity-50"
                          >
                            <RotateCcw className="w-3 h-3" />
                            <span>Retry</span>
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
