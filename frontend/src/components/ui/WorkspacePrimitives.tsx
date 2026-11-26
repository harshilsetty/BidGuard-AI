import React from "react";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";

export function PageHeader({
  title,
  subtitle,
  badge,
  actions,
}: {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="bg-[#101C32] text-white rounded-xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xs">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">{title}</h1>
          {badge}
        </div>
        {subtitle && <p className="text-xs sm:text-sm text-slate-300 max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5 shrink-0">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  subtext,
  icon,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  subtext?: string;
  icon?: React.ReactNode;
  tone?: "default" | "blue" | "green" | "amber";
}) {
  const valueTone =
    tone === "blue"
      ? "text-[#1769AA]"
      : tone === "green"
        ? "text-[#16856B]"
        : tone === "amber"
          ? "text-[#D99A35]"
          : "text-[#101C32]";

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2 shadow-xs">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>
      <div className={`text-2xl font-bold tracking-tight ${valueTone}`}>{value}</div>
      {subtext && <p className="text-xs text-slate-500">{subtext}</p>}
    </div>
  );
}

export function StatusIndicator({
  label,
  variant = "neutral",
}: {
  label: string;
  variant?: "green" | "amber" | "red" | "blue" | "neutral";
}) {
  const classes: Record<string, string> = {
    green: "bg-emerald-50 text-[#16856B] border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
    blue: "bg-[#EAF2FA] text-[#1769AA] border-blue-200",
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${classes[variant]}`}
    >
      {label}
    </span>
  );
}

export function LoadingState({ message = "Loading..." }: { message?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-white border border-slate-200 rounded-xl py-12 px-4 flex flex-col items-center justify-center space-y-3 text-center"
    >
      <Loader2 className="w-6 h-6 animate-spin text-[#1769AA]" />
      <p className="text-xs text-slate-600 font-medium">{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl py-12 px-6 flex flex-col items-center justify-center space-y-3 text-center">
      <Inbox className="w-9 h-9 text-slate-300" />
      <h3 className="text-sm font-semibold text-[#101C32]">{title}</h3>
      <p className="text-xs text-slate-500 max-w-md">{description}</p>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="bg-white border border-red-200 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-red-800"
    >
      <div className="flex items-start space-x-2.5">
        <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-3 py-1.5 rounded-lg border border-red-200 text-red-700 font-semibold hover:bg-red-50 transition self-start sm:self-auto"
        >
          Retry
        </button>
      )}
    </div>
  );
}
