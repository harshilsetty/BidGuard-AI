"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Building2,
  Database,
  FileUp,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Shield,
  X,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import {
  getAuthorizedNavItems,
  isPublicRoute,
  type NavGroup,
  type NavIconKey,
} from "@/lib/rbac";
import { AuthGate } from "./AuthGate";

const ICON_MAP: Record<NavIconKey, React.ComponentType<{ className?: string }>> = {
  dashboard: LayoutDashboard,
  tenders: LayoutDashboard,
  upload: FileUp,
  organization: Building2,
  audit: ScrollText,
  mock: Database,
};

const GROUP_ORDER: NavGroup[] = [
  "Workspace",
  "Procurement",
  "Administration",
  "Diagnostics",
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, organizationName, roles, hasPermission, logout } = useAuth();
  const pathname = usePathname() || "/";
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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

  if (publicRoute) {
    return (
      <Suspense fallback={null}>
        <AuthGate>{children}</AuthGate>
      </Suspense>
    );
  }

  const renderNavGroups = (compact: boolean) =>
    GROUP_ORDER.map((group) => {
      const items = navItems.filter((item) => item.group === group);
      if (items.length === 0) return null;

      return (
        <div key={group} className="space-y-1">
          {!compact && (
            <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {group}
            </p>
          )}
          {items.map((item) => {
            const Icon = ICON_MAP[item.icon];
            const isActive =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

            return (
              <Link
                key={item.id}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                title={compact ? item.label : undefined}
                className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs transition ${
                  isActive
                    ? "bg-[#EAF2FA] text-[#1769AA] font-semibold"
                    : "text-slate-600 hover:text-[#101C32] hover:bg-slate-100/80 font-medium"
                }`}
              >
                <span className="flex items-center space-x-2.5 min-w-0">
                  <Icon className="w-4 h-4 shrink-0" />
                  {!compact && <span className="truncate">{item.label}</span>}
                </span>
                {!compact && item.badge && (
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-200">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      );
    });

  return (
    <div className="min-h-screen flex flex-col bg-[#F5F8FB]">
      {/* Government Top Strip */}
      <div className="bg-[#101C32] text-slate-200 text-[11px] px-4 py-1.5 border-b border-slate-800">
        <div className="max-w-[1600px] mx-auto flex items-center justify-between">
          <span className="font-semibold tracking-wide text-slate-100 truncate">
            GOVERNMENT OF INDIA • GeM PROCUREMENT VERIFICATION
          </span>
          <div className="hidden sm:flex items-center space-x-3 text-slate-300">
            <span>SIH26100</span>
            <span>•</span>
            <span className="text-emerald-400 font-medium flex items-center">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 inline-block" />
              Platform Online
            </span>
          </div>
        </div>
      </div>

      {/* Main Layout: Sidebar + Content */}
      <div className="flex-1 flex">
        {/* Desktop Sidebar */}
        {status === "authenticated" && (
          <aside
            aria-label="Workspace sidebar"
            className={`hidden md:flex flex-col border-r border-slate-200 bg-white shrink-0 transition-all duration-150 ${
              sidebarCollapsed ? "w-16" : "w-60"
            }`}
          >
            <div className="h-16 px-3 border-b border-slate-200 flex items-center justify-between">
              <Link href="/" className="flex items-center space-x-2.5 min-w-0">
                <div className="h-8 w-8 rounded-lg bg-[#101C32] flex items-center justify-center font-bold text-white text-xs tracking-wider shrink-0">
                  BG
                </div>
                {!sidebarCollapsed && (
                  <div className="min-w-0">
                    <div className="font-bold text-sm text-[#101C32] truncate">BidGuard AI</div>
                    <div className="text-[10px] text-slate-500 truncate">
                      Intelligence behind every bid
                    </div>
                  </div>
                )}
              </Link>
              <button
                type="button"
                onClick={() => setSidebarCollapsed((c) => !c)}
                aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                className="p-1.5 rounded text-slate-400 hover:text-[#101C32] hover:bg-slate-100"
              >
                {sidebarCollapsed ? (
                  <PanelLeftOpen className="w-4 h-4" />
                ) : (
                  <PanelLeftClose className="w-4 h-4" />
                )}
              </button>
            </div>

            <nav className="flex-1 p-3 space-y-5 overflow-y-auto">
              {renderNavGroups(sidebarCollapsed)}
            </nav>

            {!sidebarCollapsed && user && (
              <div className="p-3 border-t border-slate-200 bg-slate-50/70 space-y-1 text-xs">
                <div className="font-semibold text-[#101C32] truncate">{user.full_name}</div>
                <div className="text-[11px] text-slate-500 truncate">{user.email}</div>
                <div className="pt-1 flex items-center space-x-1 text-[10px] font-semibold text-[#1769AA] uppercase">
                  <Shield className="w-3 h-3" />
                  <span>{primaryRole}</span>
                </div>
              </div>
            )}
          </aside>
        )}

        {/* Mobile Drawer */}
        {status === "authenticated" && mobileMenuOpen && (
          <div className="fixed inset-0 z-50 md:hidden flex">
            <div
              className="fixed inset-0 bg-slate-900/40"
              onClick={() => setMobileMenuOpen(false)}
            />
            <aside className="relative w-64 max-w-full bg-white h-full border-r border-slate-200 flex flex-col z-10">
              <div className="h-16 px-4 border-b border-slate-200 flex items-center justify-between">
                <span className="font-bold text-sm text-[#101C32]">BidGuard AI</span>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close navigation menu"
                  className="p-1.5 rounded text-slate-500"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <nav className="flex-1 p-3 space-y-5 overflow-y-auto">{renderNavGroups(false)}</nav>
            </aside>
          </div>
        )}

        {/* Right Column: Top Header + Main */}
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-16 border-b border-slate-200 bg-white sticky top-0 z-30 px-4 sm:px-6 flex items-center justify-between gap-3">
            <div className="flex items-center space-x-3 min-w-0">
              {status === "authenticated" && (
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(true)}
                  aria-label="Open navigation menu"
                  className="md:hidden p-2 rounded-lg border border-slate-200 text-slate-600"
                >
                  <Menu className="w-4 h-4" />
                </button>
              )}
              <div className="md:hidden font-bold text-sm text-[#101C32]">BidGuard AI</div>
              {status === "authenticated" && organizationName && (
                <div className="hidden sm:flex items-center space-x-2 px-2.5 py-1 rounded-lg bg-[#EAF2FA] border border-blue-200/70 text-[#101C32]">
                  <Building2 className="w-3.5 h-3.5 text-[#1769AA] shrink-0" />
                  <span className="text-xs font-semibold truncate max-w-[220px]">
                    {organizationName}
                  </span>
                  <span className="text-slate-300">|</span>
                  <span className="text-[10px] font-bold uppercase tracking-wide text-[#1769AA]">
                    {primaryRole}
                  </span>
                </div>
              )}
            </div>

            {status === "authenticated" && user && (
              <div className="flex items-center space-x-2.5 shrink-0">
                {hasPermission("tender:create") && (
                  <Link
                    href="/tenders/new"
                    className="inline-flex items-center px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition shadow-xs"
                  >
                    + Create Tender
                  </Link>
                )}
                <button
                  type="button"
                  onClick={handleLogout}
                  disabled={loggingOut}
                  title={`Sign out (${user.email})`}
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[#101C32] bg-slate-50 hover:bg-slate-100 border border-slate-200 transition disabled:opacity-60"
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
          </header>

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

          <footer className="border-t border-slate-200 bg-white text-slate-500 text-xs py-4 mt-auto">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
              <div>
                <strong className="text-[#101C32] font-semibold">
                  BidGuard AI (SIH26100)
                </strong>{" "}
                — Intelligence behind every bid
              </div>
              <div className="text-[11px]">
                Source-Grounded Evidence • Deterministic Rules • RBAC &amp; Tenant Isolation
              </div>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
