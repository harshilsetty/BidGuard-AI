"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Building2, Loader2, LogOut, Shield } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { getAuthorizedNavItems, isPublicRoute } from "@/lib/rbac";
import { AuthGate } from "./AuthGate";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, organizationName, roles, hasPermission, logout } = useAuth();
  const pathname = usePathname() || "/";
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const publicRoute = isPublicRoute(pathname);
  const navItems = getAuthorizedNavItems(user);
  const primaryRole = roles[0] || "USER";

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
      router.replace("/login");
    } finally {
      setLoggingOut(false);
    }
  };

  // Public routes (such as /login) render their own clean layout without app chrome
  if (publicRoute) {
    return (
      <Suspense fallback={null}>
        <AuthGate>{children}</AuthGate>
      </Suspense>
    );
  }

  return (
    <>
      {/* Government Top Bar */}
      <div className="bg-[#0F2D5B] text-slate-200 text-[11px] px-4 py-1.5 border-b border-[#0a2042]">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="font-semibold tracking-wide text-slate-100">
              GOVERNMENT OF INDIA • GeM PROCUREMENT VERIFICATION
            </span>
          </div>
          <div className="flex items-center space-x-4 text-slate-300">
            <span>SIH 2026 Problem ID: SIH26100</span>
            <span>•</span>
            <span className="text-emerald-400 font-medium flex items-center">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 inline-block" />
              Platform: Online
            </span>
          </div>
        </div>
      </div>

      {/* Main Navigation Header */}
      <header className="border-b border-[#E9EEF5] bg-white shadow-xs sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center space-x-6">
            <Link href="/" className="flex items-center space-x-3 group">
              <div className="h-9 w-9 rounded bg-[#0F2D5B] flex items-center justify-center font-bold text-white text-sm shadow-xs tracking-wider">
                GeM
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-sm sm:text-base text-[#0F2D5B] tracking-tight">
                    BidGuard AI
                  </span>
                  <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-blue-50 text-[#1F4E9E] border border-blue-200">
                    v1.0-RC
                  </span>
                </div>
                <p className="text-[11px] text-[#6B7C93] font-medium">
                  Integrated Bid Compliance Verification Platform
                </p>
              </div>
            </Link>

            {status === "authenticated" && (
              <nav
                aria-label="Primary navigation"
                className="hidden md:flex items-center space-x-1 pl-4 border-l border-[#E9EEF5]"
              >
                {navItems.map((item) => {
                  const isActive =
                    item.href === "/"
                      ? pathname === "/"
                      : pathname.startsWith(item.href);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`px-3 py-1.5 rounded text-xs transition flex items-center space-x-1 ${
                        isActive
                          ? "font-semibold text-[#0F2D5B] bg-[#F5F8FB]"
                          : "font-medium text-[#6B7C93] hover:text-[#0F2D5B] hover:bg-[#F5F8FB]"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.badge && (
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-50 text-amber-900 border border-amber-200">
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </nav>
            )}
          </div>

          {status === "authenticated" && user && (
            <div className="flex items-center space-x-2.5">
              {/* Organization & Role Context */}
              <div className="hidden lg:flex items-center space-x-2 px-2.5 py-1 rounded bg-[#EAF2FA] border border-blue-200/70 text-[#101C32]">
                <Building2 className="w-3.5 h-3.5 text-[#1769AA]" />
                <span className="text-xs font-semibold max-w-[160px] truncate">
                  {organizationName || "Organization"}
                </span>
                <span className="text-slate-300">|</span>
                <span className="inline-flex items-center space-x-1 text-[10px] font-semibold uppercase tracking-wide text-[#1769AA]">
                  <Shield className="w-3 h-3" />
                  <span>{primaryRole}</span>
                </span>
              </div>

              {hasPermission("tender:create") && (
                <Link
                  href="/tenders/new"
                  className="inline-flex items-center px-3.5 py-1.5 rounded text-xs font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition shadow-xs"
                >
                  + Create Tender
                </Link>
              )}

              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                title={`Sign out (${user.email})`}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded text-xs font-medium text-[#2B3A55] bg-[#F5F8FB] hover:bg-slate-200/70 border border-[#E9EEF5] transition disabled:opacity-60"
              >
                {loggingOut ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <LogOut className="w-3.5 h-3.5" />
                )}
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Application Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full">
        <Suspense
          fallback={
            <div className="min-h-[60vh] flex items-center justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-[#1769AA]" />
            </div>
          }
        >
          <AuthGate>{children}</AuthGate>
        </Suspense>
      </main>

      {/* Official Footer */}
      <footer className="border-t border-[#E9EEF5] bg-white text-[#6B7C93] text-xs py-5 mt-auto">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
          <div>
            <strong className="text-[#0F2D5B] font-semibold">
              SIH26100: Bid Compliance Verification Platform
            </strong>{" "}
            — Designed for GeM Public Procurement
          </div>
          <div className="text-[#6B7C93] text-[11px]">
            Strictly Source-Grounded Evidence • Clause-Scoped Contradiction Detection • Deterministic Verification
          </div>
        </div>
      </footer>
    </>
  );
}
