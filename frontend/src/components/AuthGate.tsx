"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ShieldAlert, Loader2, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { canAccessRoute, isPublicRoute, sanitizeRedirectPath } from "@/lib/rbac";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status, user, roles, organizationName, sessionNotice } = useAuth();
  const pathname = usePathname() || "/";
  const searchParams = useSearchParams();
  const router = useRouter();

  const publicRoute = isPublicRoute(pathname);
  const authorizedForRoute = canAccessRoute(user, pathname);

  useEffect(() => {
    if (status === "initializing") return;

    if (!publicRoute && status === "unauthenticated") {
      const nextTarget = sanitizeRedirectPath(pathname);
      const params = new URLSearchParams();
      if (nextTarget !== "/") {
        params.set("next", nextTarget);
      }
      if (sessionNotice === "session_expired") {
        params.set("reason", "session_expired");
      }
      const qs = params.toString();
      router.replace(qs ? `/login?${qs}` : "/login");
      return;
    }

    if (pathname.startsWith("/login") && status === "authenticated") {
      const nextParam = sanitizeRedirectPath(searchParams?.get("next"));
      router.replace(nextParam);
    }
  }, [status, publicRoute, pathname, router, searchParams, sessionNotice]);

  if (status === "initializing") {
    return (
      <div
        className="min-h-[70vh] flex flex-col items-center justify-center px-4"
        role="status"
        aria-live="polite"
      >
        <div className="bg-white border border-[#E9EEF5] rounded-xl px-8 py-7 shadow-xs flex flex-col items-center space-y-3 max-w-sm w-full text-center">
          <div className="h-10 w-10 rounded-lg bg-[#EAF2FA] text-[#1769AA] flex items-center justify-center">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
          <h2 className="text-sm font-semibold text-[#101C32]">
            Verifying enterprise session
          </h2>
          <p className="text-xs text-[#6B7C93]">
            Restoring organization context and access permissions...
          </p>
        </div>
      </div>
    );
  }

  if (!publicRoute && status === "unauthenticated") {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center px-4">
        <div className="bg-white border border-[#E9EEF5] rounded-xl px-8 py-7 shadow-xs flex flex-col items-center space-y-3 max-w-sm w-full text-center">
          <div className="h-10 w-10 rounded-lg bg-[#EAF2FA] text-[#1769AA] flex items-center justify-center">
            <Lock className="w-5 h-5" />
          </div>
          <h2 className="text-sm font-semibold text-[#101C32]">
            Authentication required
          </h2>
          <p className="text-xs text-[#6B7C93]">
            Redirecting to BidGuard AI sign-in...
          </p>
        </div>
      </div>
    );
  }

  if (pathname.startsWith("/login") && status === "authenticated") {
    return null;
  }

  if (!publicRoute && status === "authenticated" && !authorizedForRoute) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div
          className="bg-white border border-red-200 rounded-xl p-8 max-w-md w-full shadow-xs space-y-4 text-center"
          role="alert"
        >
          <div className="mx-auto h-12 w-12 rounded-full bg-red-50 text-[#DC3545] flex items-center justify-center border border-red-100">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div className="space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-[#DC3545]">
              403 • Access Restricted
            </p>
            <h1 className="text-lg font-bold text-[#101C32]">
              Insufficient Permissions
            </h1>
            <p className="text-xs text-[#6B7C93] leading-relaxed">
              Your current role ({roles.join(", ") || "Authenticated User"}) in{" "}
              <span className="font-semibold text-[#101C32]">
                {organizationName || "your organization"}
              </span>{" "}
              does not include permission to access this route.
            </p>
          </div>
          <div className="pt-2">
            <Link
              href="/"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition"
            >
              Return to Tenders
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
