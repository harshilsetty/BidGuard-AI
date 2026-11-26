"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getRoleWorkspaceMetadata } from "@/lib/rbac";
import { fetchSystemHealth, fetchNvidiaHealth, fetchTenders } from "@/lib/api-client";
import { SystemHealth, NvidiaHealth, Tender } from "@/lib/types";
import {
  Activity,
  Database,
  Cpu,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FileText,
  Plus,
  ArrowRight,
  SlidersHorizontal,
  Clock,
} from "lucide-react";

export default function HomePage() {
  const { user, organizationName, hasPermission } = useAuth();
  const workspaceMeta = getRoleWorkspaceMetadata(user);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [nvidiaHealth, setNvidiaHealth] = useState<NvidiaHealth | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const checkHealth = async () => {
    setLoading(true);
    try {
      const [sys, nvd, tnd] = await Promise.allSettled([
        fetchSystemHealth(),
        fetchNvidiaHealth(),
        fetchTenders(),
      ]);

      if (sys.status === "fulfilled") {
        setSystemHealth(sys.value);
      } else {
        setSystemHealth({
          status: "OFFLINE",
          service: "GeM Platform Backend",
          version: "0.1.0",
          database: "DISCONNECTED",
        });
      }

      if (nvd.status === "fulfilled") {
        setNvidiaHealth(nvd.value);
      } else {
        setNvidiaHealth({
          status: "OFFLINE",
          model: "openai/gpt-oss-20b",
          base_url: "https://integrate.api.nvidia.com/v1",
          message: "Could not reach NVIDIA health endpoint",
        });
      }

      if (tnd.status === "fulfilled") {
        setTenders(tnd.value);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div className="space-y-8">
      {/* Role-Aware Workspace Header - Official Midnight Navy Surface */}
      <div className="bg-[#101C32] border border-[#101C32] rounded-xl p-6 sm:p-8 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6 text-white">
        <div className="space-y-3 max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white/10 text-white border border-white/20">
              {workspaceMeta.role} • {organizationName || "Organization"}
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#1769AA]/60 text-blue-100 border border-blue-400/30">
              {workspaceMeta.accessSummary}
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            {workspaceMeta.title}
          </h1>
          <p className="text-sm sm:text-base text-blue-100 leading-relaxed font-normal">
            {workspaceMeta.subtitle}
          </p>
          {workspaceMeta.futureBoundaryNote && (
            <p className="text-xs text-amber-200/90 font-medium">
              Module Boundary: {workspaceMeta.futureBoundaryNote}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          {hasPermission("organization:read") && (
            <Link
              href="/organization"
              className="inline-flex items-center space-x-1.5 px-3.5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-semibold transition border border-white/20"
            >
              <span>Organization</span>
            </Link>
          )}
          {hasPermission("audit:read") && (
            <Link
              href="/audit"
              className="inline-flex items-center space-x-1.5 px-3.5 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-semibold transition border border-white/20"
            >
              <span>Audit Logs</span>
            </Link>
          )}
          <button
            onClick={checkHealth}
            disabled={loading}
            className="p-2.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs transition border border-white/20 flex items-center space-x-1.5 cursor-pointer"
            title="Refresh Platform Status"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            <span className="text-xs font-medium">Refresh</span>
          </button>
          {hasPermission("tender:create") && (
            <Link
              href="/tenders/new"
              className="inline-flex items-center space-x-2 px-4 py-2.5 bg-[#1769AA] hover:bg-[#13568c] text-white rounded-lg text-sm font-semibold transition shadow-sm border border-blue-400/30"
            >
              <Plus className="w-4 h-4" />
              <span>Upload Tender</span>
            </Link>
          )}
        </div>
      </div>

      {/* Platform Status Cards (Evaluator View) - Clean White Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Verification Engine */}
        <div className="bg-white border border-[#E9EEF5] rounded-xl p-5 space-y-3 shadow-xs hover:border-[#1F4E9E]/40 transition">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-[#0F2D5B]">
              <Activity className="w-4 h-4 text-[#1F4E9E]" />
              <span className="font-bold text-xs uppercase tracking-wider text-[#0F2D5B]">Verification Engine</span>
            </div>
            {systemHealth?.status === "OFFLINE" ? (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-red-50 text-[#DC3545] border border-red-200">
                <AlertCircle className="w-3 h-3 mr-1" /> Offline
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-[#28A745] border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Operational
              </span>
            )}
          </div>
          <p className="text-xs text-[#6B7C93] leading-relaxed font-normal">
            Requirement extraction and compliance verification
          </p>
          <div className="pt-2 border-t border-[#E9EEF5] text-[11px] text-[#6B7C93] flex items-center justify-between font-mono">
            <span>Rules: Deterministic</span>
            <span className="text-[#2B3A55] font-semibold">v{systemHealth?.version || "0.1.0"}</span>
          </div>
        </div>

        {/* Evidence Retrieval */}
        <div className="bg-white border border-[#E9EEF5] rounded-xl p-5 space-y-3 shadow-xs hover:border-[#1F4E9E]/40 transition">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-[#0F2D5B]">
              <FileText className="w-4 h-4 text-[#17A2B8]" />
              <span className="font-bold text-xs uppercase tracking-wider text-[#0F2D5B]">Evidence Retrieval</span>
            </div>
            {systemHealth?.status === "OFFLINE" ? (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-red-50 text-[#DC3545] border border-red-200">
                <AlertCircle className="w-3 h-3 mr-1" /> Offline
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-[#28A745] border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Ready
              </span>
            )}
          </div>
          <p className="text-xs text-[#6B7C93] leading-relaxed font-normal">
            Source-grounded bidder evidence
          </p>
          <div className="pt-2 border-t border-[#E9EEF5] text-[11px] text-[#6B7C93] flex items-center justify-between font-mono">
            <span>Model: Nemotron</span>
            <span className="text-[#2B3A55] font-semibold">2048-dim</span>
          </div>
        </div>

        {/* AI Engine */}
        <div className="bg-white border border-[#E9EEF5] rounded-xl p-5 space-y-3 shadow-xs hover:border-[#1F4E9E]/40 transition">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-[#0F2D5B]">
              <Cpu className="w-4 h-4 text-[#1F4E9E]" />
              <span className="font-bold text-xs uppercase tracking-wider text-[#0F2D5B]">AI Engine</span>
            </div>
            {nvidiaHealth?.status === "OFFLINE" ? (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-[#FFC107] border border-amber-300">
                <AlertCircle className="w-3 h-3 mr-1" /> Offline
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-[#28A745] border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Ready
              </span>
            )}
          </div>
          <p className="text-xs text-[#6B7C93] leading-relaxed font-normal">
            Document understanding and semantic analysis
          </p>
          <div className="pt-2 border-t border-[#E9EEF5] text-[11px] text-[#6B7C93] flex items-center justify-between font-mono">
            <span>Model:</span>
            <span className="text-[#2B3A55] font-semibold truncate ml-1">{nvidiaHealth?.model || "openai/gpt-oss-20b"}</span>
          </div>
        </div>

        {/* Data Storage */}
        <div className="bg-white border border-[#E9EEF5] rounded-xl p-5 space-y-3 shadow-xs hover:border-[#1F4E9E]/40 transition">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-[#0F2D5B]">
              <Database className="w-4 h-4 text-[#1F4E9E]" />
              <span className="font-bold text-xs uppercase tracking-wider text-[#0F2D5B]">Data Storage</span>
            </div>
            {systemHealth?.database?.toLowerCase() === "disconnected" ? (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-red-50 text-[#DC3545] border border-red-200">
                <AlertCircle className="w-3 h-3 mr-1" /> Disconnected
              </span>
            ) : (
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-[#28A745] border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 mr-1" /> Operational
              </span>
            )}
          </div>
          <p className="text-xs text-[#6B7C93] leading-relaxed font-normal">
            Persistent demonstration data
          </p>
          <div className="pt-2 border-t border-[#E9EEF5] text-[11px] text-[#6B7C93] flex items-center justify-between font-mono">
            <span>Storage:</span>
            <span className="text-[#2B3A55] font-semibold truncate ml-1">
              {systemHealth?.database === "postgresql" ? "PostgreSQL" : "Persistent local storage"}
            </span>
          </div>
        </div>
      </div>

      {/* Active Tenders List */}
      <div className="bg-white border border-[#E9EEF5] rounded-xl overflow-hidden shadow-xs">
        <div className="px-6 py-4 border-b border-[#E9EEF5] flex items-center justify-between bg-[#F5F8FB]">
          <div className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-[#1F4E9E]" />
            <h2 className="font-bold text-sm text-[#0F2D5B] uppercase tracking-wider">
              Active Tender Documents
            </h2>
          </div>
          {hasPermission("tender:create") && (
            <Link
              href="/tenders/new"
              className="text-xs text-[#1769AA] hover:text-[#13568c] transition font-semibold"
            >
              + Upload New
            </Link>
          )}
        </div>

        {tenders.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <FileText className="w-10 h-10 text-slate-300 mx-auto" />
            <p className="text-sm text-[#2B3A55] font-medium">No tenders ingested yet.</p>
            <p className="text-xs text-[#6B7C93]">
              {hasPermission("tender:create")
                ? "Upload a GeM Tender Notice / NIT document to trigger AI requirement extraction."
                : "No tenders are currently available for your organization."}
            </p>
            {hasPermission("tender:create") && (
              <div className="pt-2">
                <Link
                  href="/tenders/new"
                  className="inline-flex items-center space-x-1.5 px-4 py-2 bg-[#1769AA] hover:bg-[#13568c] text-white rounded-lg text-xs font-semibold transition shadow-xs"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Upload First Tender</span>
                </Link>
              </div>
            )}
          </div>
        ) : (
          <div className="divide-y divide-[#E9EEF5]">
            {[...tenders]
              .sort((a, b) => {
                if (a.gem_tender_id === "GEM/2026/B/8912450") return -1;
                if (b.gem_tender_id === "GEM/2026/B/8912450") return 1;
                return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
              })
              .map((tender) => {
                const isGolden = tender.gem_tender_id === "GEM/2026/B/8912450";
                const biddersLabel = isGolden
                  ? "3 Sample Bidders (A, B, C)"
                  : tender.gem_tender_id === "GEM/2026/B/8912453"
                  ? "3 Bidders"
                  : "2 Bidders";

                return (
                  <div
                    key={tender.id}
                    className={`p-6 flex flex-col lg:flex-row lg:items-center justify-between gap-5 transition bg-white ${
                      isGolden
                        ? "border-l-4 border-l-[#FFC107] hover:bg-[#F5F8FB]"
                        : "hover:bg-[#F5F8FB]"
                    }`}
                  >
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <h3 className="font-bold text-base sm:text-lg text-[#0F2D5B]">
                          {tender.title}
                        </h3>
                        {isGolden && (
                          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-300">
                            ★ SIH Golden Demo
                          </span>
                        )}
                        {tender.extraction_status === "READY" ? (
                          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-[#28A745] border border-emerald-200">
                            READY
                          </span>
                        ) : tender.extraction_status === "REVIEW" ? (
                          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300">
                            REVIEW MODE
                          </span>
                        ) : (
                          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-[#1F4E9E] border border-blue-200">
                            {tender.extraction_status}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-[#6B7C93]">
                        {tender.gem_tender_id && (
                          <span>
                            <strong className="text-[#6B7C93] font-normal">GeM ID:</strong>{" "}
                            <span className="font-semibold text-[#2B3A55]">{tender.gem_tender_id}</span>
                          </span>
                        )}
                        <span>
                          <strong className="text-[#6B7C93] font-normal">Pages:</strong>{" "}
                          <span className="font-semibold text-[#2B3A55]">{tender.total_pages}</span>
                        </span>
                        <span>
                          <strong className="text-[#6B7C93] font-normal">Extracted Clauses:</strong>{" "}
                          <span className="font-semibold text-[#2B3A55]">{tender.clause_count || 0}</span>
                        </span>
                        <span>
                          <strong className="text-[#6B7C93] font-normal">
                            {isGolden ? "Evaluation Benchmark:" : "Bidders:"}
                          </strong>{" "}
                          <span className={`font-semibold ${isGolden ? "text-emerald-700" : "text-[#2B3A55]"}`}>
                            {biddersLabel}
                          </span>
                        </span>
                        <span>
                          <strong className="text-[#6B7C93] font-normal">Uploaded:</strong>{" "}
                          <span className="text-[#6B7C93]">{new Date(tender.created_at).toLocaleDateString()}</span>
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0 pt-2 lg:pt-0">
                      <Link
                        href={`/tenders/${tender.id}/compliance`}
                        className="inline-flex items-center space-x-1.5 px-4 py-2.5 bg-white hover:bg-[#F5F8FB] text-[#1F4E9E] rounded-lg text-xs sm:text-sm font-semibold transition border border-[#E9EEF5] hover:border-[#1F4E9E]/30"
                      >
                        <span>Compliance Matrix</span>
                      </Link>
                      <Link
                        href={`/tenders/${tender.id}/clauses`}
                        className="inline-flex items-center space-x-2 px-5 py-2.5 bg-[#1F4E9E] hover:bg-[#2E73D6] text-white rounded-lg text-xs sm:text-sm font-semibold transition shadow-xs"
                      >
                        <span>Review Requirements</span>
                        <ArrowRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
}
