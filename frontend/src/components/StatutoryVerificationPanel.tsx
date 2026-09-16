"use client";

import React, { useState, useEffect } from "react";
import {
  StatutoryAuthority,
  SourceVerificationResult,
  BidderStatutoryVerificationSummary,
  Bidder,
} from "@/lib/types";
import { verifyStatutorySources } from "@/lib/api-client";
import {
  ShieldCheck,
  Building2,
  FileCheck,
  Landmark,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ExternalLink,
  Calendar,
} from "lucide-react";

interface StatutoryVerificationPanelProps {
  tenderId: string;
  bidders: Bidder[];
}

export default function StatutoryVerificationPanel({
  tenderId,
  bidders,
}: StatutoryVerificationPanelProps) {
  const [selectedBidderId, setSelectedBidderId] = useState<string>(
    bidders.length > 0 ? bidders[0].id : ""
  );
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [summary, setSummary] = useState<BidderStatutoryVerificationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (bidders.length > 0 && (!selectedBidderId || !bidders.some((b) => b.id === selectedBidderId))) {
      setSelectedBidderId(bidders[0].id);
    }
  }, [bidders, selectedBidderId]);

  const handleVerify = async () => {
    const activeBidderId = selectedBidderId || (bidders.length > 0 ? bidders[0].id : "");
    if (!activeBidderId) return;
    setLoading(true);
    setError(null);

    const selectedBidder = bidders.find((b) => b.id === activeBidderId) || bidders[0];
    const cleanCompanyName = selectedBidder
      ? selectedBidder.company_name.replace(/\s*\([^)]*\)/g, "").trim()
      : "";

    try {
      const res = await verifyStatutorySources({
        tender_id: tenderId,
        bidder_id: selectedBidderId,
        as_of_date: asOfDate ? asOfDate : null,
        identifiers: cleanCompanyName
          ? { company_name: cleanCompanyName }
          : {},
      });
      setSummary(res);
    } catch (err: any) {
      setError(err?.message || "Failed to execute statutory verification.");
    } finally {
      setLoading(false);
    }
  };

  const getConnectionBadge = (status: string) => {
    switch (status) {
      case "SUCCESS":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            CONN: SUCCESS
          </span>
        );
      case "TIMEOUT":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3 mr-1" />
            CONN: TIMEOUT
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3 mr-1" />
            CONN: {status}
          </span>
        );
    }
  };

  const getVerificationBadge = (status: string) => {
    switch (status) {
      case "VERIFIED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            VERIFIED
          </span>
        );
      case "NOT_FOUND":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            NOT FOUND
          </span>
        );
      case "INACTIVE":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            INACTIVE
          </span>
        );
      case "DISCREPANCY":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            DISCREPANCY
          </span>
        );
      case "EXPIRED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            EXPIRED
          </span>
        );
      case "UNVERIFIED":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            UNVERIFIED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const getAuthorityIcon = (auth: StatutoryAuthority) => {
    switch (auth) {
      case "GSTN":
        return <Landmark className="w-4 h-4 text-blue-600" />;
      case "UDYAM":
        return <Building2 className="w-4 h-4 text-emerald-600" />;
      case "MCA":
        return <ShieldCheck className="w-4 h-4 text-purple-600" />;
      case "INCOME_TAX":
        return <FileCheck className="w-4 h-4 text-orange-600" />;
      case "MII":
        return <CheckCircle2 className="w-4 h-4 text-indigo-600" />;
      case "DEBARMENT":
        return <AlertTriangle className="w-4 h-4 text-rose-600" />;
      case "DPIIT":
        return <CheckCircle2 className="w-4 h-4 text-cyan-600" />;
      case "EPFO":
        return <Building2 className="w-4 h-4 text-teal-600" />;
      case "ESIC":
        return <ShieldCheck className="w-4 h-4 text-blue-700" />;
      case "NSIC":
        return <Building2 className="w-4 h-4 text-emerald-700" />;
      case "DIGILOCKER":
        return <FileCheck className="w-4 h-4 text-indigo-700" />;
      default:
        return <Landmark className="w-4 h-4 text-slate-600" />;
    }
  };

  const renderPayloadSummary = (result: SourceVerificationResult) => {
    const p = result.data_payload || {};
    if (!p || Object.keys(p).length === 0) {
      return (
        <span className="text-[11px] text-slate-400 italic">
          No factual payload recorded
        </span>
      );
    }

    switch (result.authority) {
      case "GSTN":
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">GSTIN:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.gstin || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Turnover:</span>
              <span className="font-bold text-slate-900 text-right">
                {p.verified_turnover ? `₹${p.verified_turnover.toFixed(2)} Cr` : "N/A"}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Filing Status:</span>
              <span className="font-semibold text-emerald-700 text-right">{p.filing_status || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">State:</span>
              <span className="text-slate-700 text-right">{p.state || "N/A"}</span>
            </div>
          </div>
        );

      case "UDYAM":
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Registration:</span>
              <span className="font-mono font-bold text-slate-900 text-[11px] text-right truncate" title={p.udyam_registration_number}>
                {p.udyam_registration_number || "N/A"}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Enterprise:</span>
              <span className="font-bold text-emerald-700 text-right">{p.enterprise_type || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Activity:</span>
              <span className="text-slate-700 text-right truncate max-w-[150px]">{p.major_activity || "N/A"}</span>
            </div>
          </div>
        );

      case "MCA":
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">CIN:</span>
              <span className="font-mono font-bold text-slate-900 text-[10.5px] text-right truncate" title={p.cin}>
                {p.cin || "N/A"}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Status:</span>
              <span className="font-semibold text-purple-700 text-right">{p.company_status || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Auth Capital:</span>
              <span className="text-slate-700 text-right">
                {p.authorized_capital_cr ? `₹${p.authorized_capital_cr} Cr` : "N/A"}
              </span>
            </div>
          </div>
        );

      case "INCOME_TAX":
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">PAN:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.pan || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">PAN Status:</span>
              <span className="font-semibold text-emerald-700 text-right">{p.pan_status || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Last ITR FY:</span>
              <span className="text-slate-700 font-mono text-right">{p.last_itr_filed_fy || "N/A"}</span>
            </div>
          </div>
        );

      case "MII":
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Local Content:</span>
              <span className="font-bold text-indigo-700 text-right">
                {p.verified_local_content !== undefined ? `${p.verified_local_content}%` : "N/A"}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Certificate Ref:</span>
              <span className="font-mono text-slate-700 text-right truncate max-w-[150px]">{p.certificate_reference || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Authority:</span>
              <span className="text-slate-600 truncate max-w-[150px] text-right">{p.certifying_authority || "N/A"}</span>
            </div>
          </div>
        );

      case "DEBARMENT":
        if (p.is_debarred_on_date) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-2 rounded bg-rose-50 border border-rose-200 text-rose-900 space-y-1">
                <div className="flex items-center text-[10px] font-bold text-rose-700 tracking-wide uppercase">
                  <AlertTriangle className="w-3 h-3 mr-1 text-rose-600 shrink-0" />
                  <span>HIGH RISK — OFFICER REVIEW REQUIRED</span>
                </div>
                <p className="text-[10px] text-rose-800 leading-tight font-medium">
                  Debarment active on bid date. Automatic disqualification disabled.
                </p>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Order No:</span>
                <span className="font-mono font-bold text-slate-800 truncate max-w-[110px]">{p.order_number || "N/A"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Authority:</span>
                <span className="text-slate-700 truncate max-w-[110px]">{p.authority_name || "N/A"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Period:</span>
                <span className="text-slate-700 font-mono text-[10px]">
                  {p.start_date || "?"} → {p.end_date || "INDEFINITE"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Status:</span>
                <span className="font-bold text-rose-700">{p.temporal_status || "ACTIVE_ON_DATE"}</span>
              </div>
            </div>
          );
        } else if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-2 rounded bg-amber-50 border border-amber-200 text-amber-900 space-y-1">
                <div className="flex items-center text-[10px] font-bold text-amber-800 uppercase">
                  <AlertTriangle className="w-3 h-3 mr-1 text-amber-600 shrink-0" />
                  <span>AMBIGUOUS NAME MATCH</span>
                </div>
                <p className="text-[10px] text-amber-800 leading-tight">
                  Officer review required. Debarment NOT confirmed.
                </p>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Candidate:</span>
                <span className="text-slate-800 font-medium truncate max-w-[110px]">{p.candidate_firm_name || "N/A"}</span>
              </div>
            </div>
          );
        } else if (p.temporal_status === "EXPIRED_BEFORE_DATE") {
          return (
            <div className="space-y-1 text-[11px] text-slate-600">
              <div className="p-1.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10px] font-medium">
                Debarment concluded prior to evaluation date
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Concluded:</span>
                <span className="font-mono text-slate-700">{p.end_date || "N/A"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Past Order:</span>
                <span className="font-mono text-slate-700 truncate max-w-[110px]">{p.order_number || "N/A"}</span>
              </div>
            </div>
          );
        } else if (p.temporal_status === "STARTS_AFTER_DATE") {
          return (
            <div className="space-y-1 text-[11px] text-slate-600">
              <div className="p-1.5 rounded bg-blue-50 border border-blue-200 text-blue-800 text-[10px] font-medium">
                Future order (not effective on evaluation date)
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Commences:</span>
                <span className="font-mono text-slate-700">{p.start_date || "N/A"}</span>
              </div>
            </div>
          );
        } else {
          return (
            <div className="space-y-1 text-[11px] text-slate-600">
              <div className="p-1.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10px] font-semibold flex items-center">
                <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
                No Active Debarment Record
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Registry Status:</span>
                <span className="font-medium text-emerald-700">CLEAR</span>
              </div>
            </div>
          );
        }

      case "DPIIT":
        if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-medium">
                Ambiguous firm name match — Officer review required
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Candidate Cert:</span>
                <span className="font-mono text-slate-700">{p.candidate_certificate_number || "N/A"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Candidate Name:</span>
                <span className="text-slate-800 truncate max-w-[120px]">{p.candidate_entity_name || "N/A"}</span>
              </div>
            </div>
          );
        }
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Certificate:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.certificate_number || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Status:</span>
              <span className={`font-semibold text-right ${p.is_recognized ? "text-cyan-700" : "text-amber-700"}`}>
                {p.recognition_status || (p.is_recognized ? "RECOGNIZED" : "NOT_RECOGNIZED")}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Entity:</span>
              <span className="text-slate-700 truncate max-w-[150px] text-right">{p.entity_name || "N/A"}</span>
            </div>
            {p.valid_until && (
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Valid Until:</span>
                <span className="font-mono text-slate-700 text-right">{p.valid_until}</span>
              </div>
            )}
          </div>
        );

      case "EPFO":
        if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-medium">
                Ambiguous name match — Authoritative code required
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Candidate Est:</span>
                <span className="font-mono text-slate-700 text-right">{p.candidate_establishment_code || "N/A"}</span>
              </div>
            </div>
          );
        }
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Est. Code:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.establishment_code || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Coverage:</span>
              <span className={`font-semibold text-right ${p.is_covered ? "text-teal-700" : "text-slate-600"}`}>
                {p.status || (p.is_covered ? "COVERED" : "INACTIVE")}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Office:</span>
              <span className="text-slate-700 truncate max-w-[150px] text-right">{p.office_name || "N/A"}</span>
            </div>
          </div>
        );

      case "ESIC":
        if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-medium">
                Ambiguous name match — Authoritative code required
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Candidate ESIC:</span>
                <span className="font-mono text-slate-700 text-right">{p.candidate_esic_code || "N/A"}</span>
              </div>
            </div>
          );
        }
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">ESIC Code:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.esic_code || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Status:</span>
              <span className={`font-semibold text-right ${p.is_covered ? "text-blue-700" : "text-slate-600"}`}>
                {p.status || (p.is_covered ? "ACTIVE" : "INACTIVE")}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Region:</span>
              <span className="text-slate-700 text-right">{p.region || "N/A"}</span>
            </div>
          </div>
        );

      case "NSIC":
        if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-medium">
                {p.conflict_detected ? "Identity conflict detected — Officer review required" : "Ambiguous firm name match — Registration code required"}
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Candidate Reg:</span>
                <span className="font-mono text-slate-700 text-right">{p.candidate_registration_number || p.queried_registration_number || "N/A"}</span>
              </div>
            </div>
          );
        }
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">SPRS Reg:</span>
              <span className="font-mono font-bold text-slate-900 text-right">{p.registration_number || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Status:</span>
              <span className={`font-semibold text-right ${p.is_registered ? "text-emerald-700" : "text-amber-700"}`}>
                {p.status || (p.is_registered ? "ACTIVE" : "INACTIVE")}
              </span>
            </div>
            {p.monetary_limit && (
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Monetary Limit:</span>
                <span className="font-semibold text-slate-800 text-right">₹{p.monetary_limit} Lakhs</span>
              </div>
            )}
            {p.expiry_date && (
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Valid Until:</span>
                <span className="font-mono text-slate-700 text-right">{p.expiry_date}</span>
              </div>
            )}
          </div>
        );

      case "DIGILOCKER":
        if (p.is_ambiguous_match) {
          return (
            <div className="space-y-1.5 text-[11px]">
              <div className="p-1.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-medium">
                {p.conflict_detected ? "Subject identity conflict — Officer review required" : "Specific document reference or subject identifier required"}
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-500 shrink-0 font-medium">Document Ref:</span>
                <span className="font-mono text-slate-700 text-right">{p.queried_document_reference || "N/A"}</span>
              </div>
            </div>
          );
        }
        return (
          <div className="space-y-1.5 text-[11px] text-slate-600">
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Doc Type:</span>
              <span className="font-medium text-slate-800 truncate max-w-[150px] text-right">{p.document_type || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Issuer:</span>
              <span className="text-slate-700 truncate max-w-[150px] text-right">{p.issuer || "N/A"}</span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Signature:</span>
              <span className={`font-semibold text-right ${p.signature_status === "VALID" ? "text-emerald-700" : "text-rose-700"}`}>
                {p.signature_status || "N/A"}
              </span>
            </div>
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500 shrink-0 font-medium">Doc Ref:</span>
              <span className="font-mono text-slate-700 truncate max-w-[150px] text-right">{p.document_reference || "N/A"}</span>
            </div>
          </div>
        );

      default:
        return (
          <div className="text-[10px] text-slate-500 truncate">
            {JSON.stringify(p)}
          </div>
        );
    }
  };

  return (
    <div className="bg-white border border-[#E9EEF5] rounded-xl p-6 shadow-xs space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#E9EEF5] pb-5">
        <div className="flex items-center space-x-3.5">
          <div className="w-11 h-11 rounded-xl bg-blue-50 border border-blue-200/80 flex items-center justify-center text-blue-900 shadow-2xs">
            <Landmark className="w-5 h-5 text-[#0F2D5B]" />
          </div>
          <div>
            <h3 className="text-base font-bold text-[#0F2D5B] tracking-tight">
              Statutory Verification Orchestrator
            </h3>
            <p className="text-xs text-[#6B7C93] mt-0.5">
              Authoritative multi-source register checks (GSTN, Udyam, MCA, Income Tax, MII, Debarment, DPIIT, EPFO, ESIC, NSIC, DigiLocker)
            </p>
          </div>
        </div>

        <span className="inline-flex items-center px-3 py-1 rounded-md text-[11px] font-bold bg-amber-50 text-amber-900 border border-amber-200/80 shadow-2xs">
          MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION
        </span>
      </div>

      {/* Query Control Bar */}
      <div className="bg-[#F8FAFC] border border-[#E9EEF5] rounded-xl p-4 sm:p-5 flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center space-x-2">
          <label className="font-semibold text-slate-700">Target Bidder:</label>
          <select
            value={selectedBidderId}
            onChange={(e) => setSelectedBidderId(e.target.value)}
            className="bg-white border border-slate-300 rounded-lg px-3.5 py-2 text-slate-900 font-semibold focus:outline-none focus:ring-2 focus:ring-blue-900/20 shadow-2xs"
          >
            {bidders.map((b) => (
              <option key={b.id} value={b.id}>
                {b.company_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <label className="font-semibold text-slate-700 flex items-center">
            <Calendar className="w-3.5 h-3.5 mr-1 text-slate-500" />
            As-of Date (Cutoff):
          </label>
          <input
            type="date"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-slate-900 font-medium focus:outline-none focus:ring-2 focus:ring-blue-900/20 shadow-2xs"
          />
        </div>

        <button
          onClick={handleVerify}
          disabled={loading || !selectedBidderId}
          className="ml-auto inline-flex items-center space-x-2 px-5 py-2.5 bg-[#0F2D5B] hover:bg-[#1A427D] disabled:bg-slate-300 text-white font-bold rounded-lg transition shadow-xs text-xs tracking-wide"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>{loading ? "Verifying Registers..." : "Run Statutory Verification"}</span>
        </button>
      </div>

      {error && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Verification Results Cards */}
      {summary ? (
        <div className="space-y-3.5">
          <div className="flex items-center justify-between text-xs text-[#6B7C93] px-1 font-medium">
            <span>
              Verified {summary.total_sources} Authorities • {summary.successful_connections} Successful Connections
            </span>
            <span className="font-mono text-[11px]">
              Retrieved at: {new Date(summary.verified_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {summary.results.map((r) => (
              <div
                key={r.verification_id}
                className="bg-white border border-slate-200/90 rounded-xl p-4 flex flex-col justify-between shadow-2xs hover:border-slate-300 hover:shadow-xs transition space-y-3"
              >
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <div className="w-7 h-7 rounded-lg bg-slate-50 border border-slate-200/70 flex items-center justify-center shrink-0">
                        {getAuthorityIcon(r.authority)}
                      </div>
                      <span className="font-bold text-[#0F2D5B] text-xs tracking-tight">{r.authority}</span>
                    </div>
                    {getConnectionBadge(r.connection_status)}
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] text-slate-500 font-medium truncate max-w-[170px]" title={r.source_name}>
                      {r.source_name}
                    </span>
                    {getVerificationBadge(r.verification_status)}
                  </div>
                </div>

                <div className="pt-2.5 pb-1 border-t border-slate-100 flex-1 flex flex-col justify-center min-h-[80px]">
                  {renderPayloadSummary(r)}
                </div>

                <div className="pt-2.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>Latency: {r.execution_time_ms}ms</span>
                  <span>Conf: {r.confidence_score.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* Static / Baseline Preview before trigger */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[
            { name: "GSTN", label: "Goods & Services Tax", key: "GSTIN", desc: "Turnover, filing status & active registration" },
            { name: "Udyam / MSME", label: "Ministry of MSME", key: "Udyam No.", desc: "Enterprise scale (Micro/Small/Medium)" },
            { name: "MCA", label: "Corporate Affairs", key: "CIN", desc: "Active company status & authorized capital" },
            { name: "Income Tax", label: "CBDT PAN Register", key: "PAN", desc: "PAN validity & tax filing compliance" },
            { name: "Make in India", label: "DPIIT Local Content", key: "Audit Ref", desc: "Statutory verified domestic content %" },
            { name: "Debarment", label: "Central Blacklist", key: "PAN / CIN", desc: "Time-aware debarment & sanction orders" },
            { name: "DPIIT / Startup India", label: "Startup Recognition", key: "DPIIT Cert", desc: "Startup recognition status & certificate validity" },
            { name: "EPFO", label: "Provident Fund", key: "Est. Code", desc: "Establishment-level registration & operational status" },
            { name: "ESIC", label: "State Insurance", key: "ESIC Code", desc: "Employer-level registration & regional compliance" },
            { name: "NSIC", label: "National Small Industries", key: "SPRS Reg", desc: "Single Point Registration Scheme & monetary limit" },
            { name: "DigiLocker", label: "Document Provenance", key: "Doc URI", desc: "Cryptographic verification & digital signature audit" },
          ].map((item, idx) => (
            <div key={idx} className="bg-slate-50/70 border border-slate-200/90 rounded-xl p-4 space-y-3 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-bold text-[#0F2D5B] text-xs">{item.name}</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100/70 text-amber-900 border border-amber-200">
                    MOCK
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 line-clamp-2 leading-snug">{item.desc}</p>
              </div>
              <div className="pt-2.5 border-t border-slate-200/80 text-[11px] space-y-1 text-slate-600">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Primary Key:</span>
                  <span className="font-mono font-medium text-slate-800">{item.key}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Status:</span>
                  <span className="font-semibold text-emerald-700">Ready to Query</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
