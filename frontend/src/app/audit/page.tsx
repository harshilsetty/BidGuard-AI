"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, ScrollText, ShieldCheck } from "lucide-react";
import { fetchAuditLogs } from "@/lib/api-client";
import type { AuditLogEntry } from "@/lib/types";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusIndicator,
} from "@/components/ui/WorkspacePrimitives";

const PAGE_SIZE = 20;

export default function AuditTrailPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [actionFilter, setActionFilter] = useState("");
  const [targetTypeFilter, setTargetTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAuditLogs({
        action: actionFilter || undefined,
        targetType: targetTypeFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setLogs(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  }, [actionFilter, targetTypeFilter, offset]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security & Compliance Audit Trail"
        subtitle="Immutable append-only activity log scoped to your organization (or platform-wide for SUPER_ADMIN)."
        badge={<StatusIndicator label="Append-Only" variant="green" />}
        actions={
          <button
            type="button"
            onClick={loadLogs}
            className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-white/10 hover:bg-white/20 border border-white/15 text-white transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        }
      />

      <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2 text-xs text-slate-600">
          <ShieldCheck className="w-4 h-4 text-[#16856B]" />
          <span>
            Showing <strong className="text-[#101C32]">{total}</strong> recorded audit events
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setOffset(0);
            }}
            placeholder="Filter action (e.g. AUTH_LOGIN_SUCCESS)"
            aria-label="Filter by action"
            className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs text-[#101C32] focus:outline-none focus:border-[#1769AA]"
          />
          <input
            type="text"
            value={targetTypeFilter}
            onChange={(e) => {
              setTargetTypeFilter(e.target.value);
              setOffset(0);
            }}
            placeholder="Filter target (e.g. User, Organization)"
            aria-label="Filter by target type"
            className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs text-[#101C32] focus:outline-none focus:border-[#1769AA]"
          />
        </div>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={loadLogs} />
      ) : loading ? (
        <LoadingState message="Loading immutable audit trail..." />
      ) : logs.length === 0 ? (
        <EmptyState
          title="No audit events match your filters"
          description="Try clearing the action or target filters to inspect all recorded events."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4 font-semibold">Timestamp</th>
                  <th className="py-3 px-4 font-semibold">Action</th>
                  <th className="py-3 px-4 font-semibold">Actor</th>
                  <th className="py-3 px-4 font-semibold">Target</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/70">
                    <td className="py-3 px-4 text-slate-600 whitespace-nowrap font-mono text-[11px]">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-[#EAF2FA] text-[#1769AA] font-mono text-[11px] font-semibold">
                        <ScrollText className="w-3 h-3" />
                        <span>{entry.action}</span>
                      </span>
                    </td>
                    <td className="py-3 px-4 text-[#101C32]">
                      {entry.user_email || entry.user_id || "System"}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
                      {entry.target_type || "—"}
                      {entry.target_id ? `: ${entry.target_id}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 text-xs text-slate-600">
              <span>
                Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <div className="space-x-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
