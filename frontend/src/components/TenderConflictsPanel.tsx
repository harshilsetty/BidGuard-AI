"use client";

import { useCallback, useEffect, useState } from "react";
import { detectTenderConflicts, fetchTenderConflicts } from "@/lib/api-client";
import { TenderRequirementConflict } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";
import { AlertTriangle, CheckCircle2, GitCompare, Loader2 } from "lucide-react";

export function TenderConflictsPanel({ tenderId }: { tenderId: string }) {
  const { hasPermission } = useAuth();
  const canDetect = hasPermission("tender:update");

  const [conflicts, setConflicts] = useState<TenderRequirementConflict[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConflicts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchTenderConflicts(tenderId, 50, 0);
      setConflicts(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err?.message || "Failed to load cross-document conflicts.");
    } finally {
      setLoading(false);
    }
  }, [tenderId]);

  useEffect(() => {
    loadConflicts();
  }, [loadConflicts]);

  const handleDetect = async () => {
    setRunning(true);
    setError(null);
    try {
      await detectTenderConflicts(tenderId);
      await loadConflicts();
    } catch (err: any) {
      setError(err?.message || "Conflict detection failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="bg-white border border-[#E9EEF5] rounded-xl shadow-xs overflow-hidden">
      <div className="px-5 py-4 bg-[#101C32] text-white flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center space-x-2">
            <GitCompare className="w-4 h-4 text-[#EAF2FA]" />
            <h2 className="text-sm font-semibold tracking-tight">
              Cross-Document Conflicts &amp; Potential Amendments ({total})
            </h2>
          </div>
          <p className="text-xs text-[#EAF2FA]/80 mt-0.5">
            Scope-aware comparison across NIT, technical specs, BoQ, annexures, and corrigenda. Human review is required before resolution.
          </p>
        </div>

        {canDetect && (
          <button
            type="button"
            onClick={handleDetect}
            disabled={running}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#145A92] disabled:opacity-50 text-white transition flex items-center space-x-1.5"
          >
            {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            <span>{running ? "Scanning..." : "Detect Conflicts"}</span>
          </button>
        )}
      </div>

      {error && (
        <div className="px-5 py-3 bg-rose-50 border-b border-rose-200 text-xs text-[#DC3545]">
          {error}
        </div>
      )}

      <div className="divide-y divide-[#E9EEF5]">
        {loading ? (
          <div className="p-6 text-center text-xs text-[#6B7C93]">
            Loading conflict checks...
          </div>
        ) : conflicts.length === 0 ? (
          <div className="p-6 text-center text-xs text-[#6B7C93] flex items-center justify-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-[#16856B]" />
            <span>No cross-document conflicts detected.</span>
          </div>
        ) : (
          conflicts.map((c) => (
            <div key={c.id} className="p-4 hover:bg-[#F8FAFC] transition space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-[#EAF2FA] text-[#101C32]">
                    {c.conflict_type}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                      c.severity === "HIGH" || c.severity === "CRITICAL"
                        ? "bg-rose-50 text-[#DC3545] border border-rose-200"
                        : "bg-amber-50 text-[#D99A35] border border-amber-200"
                    }`}
                  >
                    {c.severity}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-[#2B3A55]">
                    {c.relationship_type}
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-[#D99A35] border border-amber-200">
                  {c.status}
                </span>
              </div>
              <p className="text-xs text-[#101C32]">{c.explanation}</p>
              {c.scope_summary && (
                <p className="text-[11px] text-[#6B7C93]">Scope: {c.scope_summary}</p>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
