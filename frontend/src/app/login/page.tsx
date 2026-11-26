"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2, Lock, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api-client";
import { sanitizeRedirectPath } from "@/lib/rbac";

function LoginFormContent() {
  const { login, status, sessionNotice, clearSessionNotice } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fieldError, setFieldError] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);

  const reasonParam = searchParams?.get("reason");
  const nextPath = sanitizeRedirectPath(searchParams?.get("next"));

  useEffect(() => {
    if (status === "authenticated") {
      router.replace(nextPath);
    }
  }, [status, router, nextPath]);

  const validateInputs = (): boolean => {
    const errors: { email?: string; password?: string } = {};
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      errors.email = "Work email is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      errors.email = "Enter a valid organization email address.";
    }

    if (!password) {
      errors.password = "Password is required.";
    }

    setFieldError(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    clearSessionNotice();

    if (!validateInputs()) {
      return;
    }

    setSubmitting(true);
    try {
      await login(email, password);
      router.replace(nextPath);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setFormError("Invalid email or password. Please verify your credentials.");
        } else if (err.status === 403) {
          setFormError(err.detail || "Your account or organization is currently inactive.");
        } else if (err.status === 429) {
          setFormError("Too many sign-in attempts. Please wait a moment and try again.");
        } else {
          setFormError(err.detail || "Authentication failed. Please try again.");
        }
      } else if (err instanceof Error) {
        setFormError(err.message || "Unable to reach authentication service.");
      } else {
        setFormError("Unable to reach authentication service.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const showExpiredBanner =
    reasonParam === "session_expired" || sessionNotice === "session_expired";
  const showLoggedOutBanner =
    !showExpiredBanner && sessionNotice === "logged_out";

  return (
    <div className="min-h-screen bg-[#EAF2FA] flex flex-col justify-center py-10 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md space-y-6">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="h-11 w-11 rounded-lg bg-[#101C32] text-white flex items-center justify-center font-bold text-sm tracking-wider shadow-xs">
            GeM
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[#101C32]">
              BidGuard AI
            </h1>
            <p className="text-xs font-medium text-[#475569] mt-0.5">
              Enterprise Procurement &amp; Bid Compliance Platform
            </p>
          </div>
        </div>

        {/* Sign-in Card */}
        <div className="bg-[#FFFFFF] border border-slate-200 rounded-xl shadow-sm p-6 sm:p-8 space-y-5">
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-[#101C32]">
              Sign in to your organization
            </h2>
            <p className="text-xs text-slate-500">
              Use your provisioned enterprise credentials to access tenders and compliance workflows.
            </p>
          </div>

          {showExpiredBanner && (
            <div
              role="status"
              className="flex items-start space-x-2.5 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs"
            >
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>Your session has expired. Please sign in again to continue.</span>
            </div>
          )}

          {showLoggedOutBanner && (
            <div
              role="status"
              className="flex items-start space-x-2.5 p-3 rounded-lg bg-[#EAF2FA] border border-blue-200 text-[#101C32] text-xs"
            >
              <CheckCircle2 className="w-4 h-4 text-[#1769AA] shrink-0 mt-0.5" />
              <span>You have been signed out securely.</span>
            </div>
          )}

          {formError && (
            <div
              role="alert"
              className="flex items-start space-x-2.5 p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs"
            >
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span>{formError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="login-email"
                className="block text-xs font-semibold text-[#101C32]"
              >
                Work Email
              </label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                autoFocus
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (fieldError.email) {
                    setFieldError((prev) => ({ ...prev, email: undefined }));
                  }
                }}
                aria-invalid={Boolean(fieldError.email)}
                aria-describedby={fieldError.email ? "login-email-error" : undefined}
                placeholder="name@organization.gov.in"
                disabled={submitting}
                className={`w-full px-3.5 py-2.5 rounded-lg border text-sm text-[#101C32] placeholder:text-slate-400 bg-white focus:outline-none focus:ring-2 transition ${
                  fieldError.email
                    ? "border-red-400 focus:ring-red-200 focus:border-red-500"
                    : "border-slate-300 focus:ring-[#1769AA]/20 focus:border-[#1769AA]"
                }`}
              />
              {fieldError.email && (
                <p id="login-email-error" className="text-xs text-red-600 font-medium">
                  {fieldError.email}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="login-password"
                className="block text-xs font-semibold text-[#101C32]"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (fieldError.password) {
                      setFieldError((prev) => ({ ...prev, password: undefined }));
                    }
                  }}
                  aria-invalid={Boolean(fieldError.password)}
                  aria-describedby={fieldError.password ? "login-password-error" : undefined}
                  placeholder="Enter your password"
                  disabled={submitting}
                  className={`w-full pl-3.5 pr-10 py-2.5 rounded-lg border text-sm text-[#101C32] placeholder:text-slate-400 bg-white focus:outline-none focus:ring-2 transition ${
                    fieldError.password
                      ? "border-red-400 focus:ring-red-200 focus:border-red-500"
                      : "border-slate-300 focus:ring-[#1769AA]/20 focus:border-[#1769AA]"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  disabled={submitting}
                  className="absolute inset-y-0 right-0 px-3 flex items-center text-slate-400 hover:text-[#101C32] focus:outline-none focus-visible:text-[#1769AA]"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {fieldError.password && (
                <p id="login-password-error" className="text-xs text-red-600 font-medium">
                  {fieldError.password}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white bg-[#1769AA] hover:bg-[#13568c] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#1769AA] disabled:opacity-60 disabled:cursor-not-allowed transition"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <Lock className="w-4 h-4" />
                  <span>Sign In</span>
                </>
              )}
            </button>
          </form>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span className="inline-flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-[#1769AA]" />
              <span>HttpOnly Session &amp; RBAC Enforced</span>
            </span>
            <span>Invite-Only Access</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#EAF2FA] flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-[#1769AA]" />
        </div>
      }
    >
      <LoginFormContent />
    </Suspense>
  );
}
