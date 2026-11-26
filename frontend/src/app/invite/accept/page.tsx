"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ApiError, validateInvitationToken } from "@/lib/api-client";
import type { InvitationValidateResponse } from "@/lib/types";

function AcceptInvitationContent() {
  const { acceptInvitation } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams?.get("token")?.trim() || "";

  const [validating, setValidating] = useState(true);
  const [validation, setValidation] = useState<InvitationValidateResponse | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const runValidation = async () => {
      if (!token) {
        if (mounted) {
          setValidation({ valid: false, status: "INVALID", requires_existing_login: false });
          setValidating(false);
        }
        return;
      }

      try {
        const res = await validateInvitationToken(token);
        if (mounted) {
          setValidation(res);
        }
      } catch (err) {
        if (mounted) {
          setValidateError(
            err instanceof Error ? err.message : "Unable to validate invitation token."
          );
        }
      } finally {
        if (mounted) {
          setValidating(false);
        }
      }
    };

    runValidation();
    return () => {
      mounted = false;
    };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const cleanedEmail = email.trim().toLowerCase();
    if (!cleanedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanedEmail)) {
      setSubmitError("Enter the invited work email address.");
      return;
    }
    if (fullName.trim().length < 2) {
      setSubmitError("Full name must be at least 2 characters.");
      return;
    }
    if (password.length < 8) {
      setSubmitError("Password must be at least 8 characters with uppercase, lowercase, and a number.");
      return;
    }

    setSubmitting(true);
    try {
      await acceptInvitation({
        invitation_token: token,
        email: cleanedEmail,
        full_name: fullName.trim(),
        password,
      });
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.detail);
      } else if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Failed to accept invitation.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const statusMessages: Record<string, string> = {
    EXPIRED: "This invitation has expired. Ask your organization administrator to resend it.",
    REVOKED: "This invitation has been revoked by an organization administrator.",
    ACCEPTED: "This invitation has already been used. Please sign in with your account.",
    INVALID: "This invitation link is invalid or incomplete.",
  };

  return (
    <div className="min-h-screen bg-[#EAF2FA] flex flex-col justify-center py-10 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md space-y-6">
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="h-11 w-11 rounded-lg bg-[#101C32] text-white flex items-center justify-center font-bold text-sm tracking-wider">
            GeM
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#101C32]">
            BidGuard AI Invitation
          </h1>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 sm:p-8 space-y-5">
          {validating ? (
            <div className="py-8 flex flex-col items-center space-y-3 text-center">
              <Loader2 className="w-6 h-6 animate-spin text-[#1769AA]" />
              <p className="text-xs text-slate-600">Validating invitation token...</p>
            </div>
          ) : validateError ? (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{validateError}</span>
              </div>
              <Link
                href="/login"
                className="block text-center w-full py-2 rounded-lg text-xs font-semibold bg-[#1769AA] text-white"
              >
                Go to Sign In
              </Link>
            </div>
          ) : !validation?.valid ? (
            <div className="space-y-4 text-center">
              <div className="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start space-x-2 text-left">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
                <span>
                  {statusMessages[validation?.status || "INVALID"] || statusMessages.INVALID}
                </span>
              </div>
              <Link
                href="/login"
                className="inline-flex justify-center w-full py-2.5 rounded-lg text-xs font-semibold bg-[#1769AA] text-white hover:bg-[#13568c]"
              >
                Return to Sign In
              </Link>
            </div>
          ) : validation.requires_existing_login ? (
            <div className="space-y-4">
              <div className="p-3.5 rounded-lg bg-[#EAF2FA] border border-blue-200 text-[#101C32] text-xs space-y-1">
                <p className="font-semibold">Account already registered</p>
                <p>
                  An account for <span className="font-mono">{validation.email_masked}</span>{" "}
                  already exists. Sign in with your existing credentials.
                </p>
              </div>
              <Link
                href="/login"
                className="inline-flex justify-center w-full py-2.5 rounded-lg text-xs font-semibold bg-[#1769AA] text-white hover:bg-[#13568c]"
              >
                Sign In to Continue
              </Link>
            </div>
          ) : (
            <>
              <div className="p-3.5 rounded-lg bg-[#EAF2FA] border border-blue-200 space-y-1.5 text-xs text-[#101C32]">
                <div className="flex items-center space-x-2 font-semibold">
                  <Building2 className="w-4 h-4 text-[#1769AA]" />
                  <span>{validation.organization_name}</span>
                </div>
                <p className="text-slate-600">
                  Assigned role (fixed):{" "}
                  <span className="font-mono font-semibold text-[#1769AA]">
                    {validation.role_name}
                  </span>
                </p>
                {validation.email_masked && (
                  <p className="text-slate-600">
                    Invited email: <span className="font-mono">{validation.email_masked}</span>
                  </p>
                )}
              </div>

              {submitError && (
                <div
                  role="alert"
                  className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-start space-x-2"
                >
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{submitError}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                <div className="space-y-1">
                  <label htmlFor="invite-email" className="block text-xs font-semibold text-[#101C32]">
                    Confirm Work Email
                  </label>
                  <input
                    id="invite-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@organization.gov.in"
                    disabled={submitting}
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] focus:outline-none focus:border-[#1769AA]"
                  />
                </div>

                <div className="space-y-1">
                  <label htmlFor="invite-name" className="block text-xs font-semibold text-[#101C32]">
                    Full Name
                  </label>
                  <input
                    id="invite-name"
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Your full name"
                    disabled={submitting}
                    className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] focus:outline-none focus:border-[#1769AA]"
                  />
                </div>

                <div className="space-y-1">
                  <label htmlFor="invite-password" className="block text-xs font-semibold text-[#101C32]">
                    Set Password
                  </label>
                  <div className="relative">
                    <input
                      id="invite-password"
                      type={showPassword ? "text" : "password"}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Minimum 8 chars, mixed case & number"
                      disabled={submitting}
                      className="w-full pl-3.5 pr-10 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] focus:outline-none focus:border-[#1769AA]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((p) => !p)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute inset-y-0 right-0 px-3 flex items-center text-slate-400 hover:text-[#101C32]"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition disabled:opacity-60"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Activating Account...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Accept Invitation &amp; Join</span>
                    </>
                  )}
                </button>
              </form>
            </>
          )}

          <div className="pt-3 border-t border-slate-100 flex items-center justify-center space-x-1.5 text-[11px] text-slate-500">
            <ShieldCheck className="w-3.5 h-3.5 text-[#1769AA]" />
            <span>Single-Use • Organization &amp; Role Bound</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AcceptInvitationPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#EAF2FA] flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-[#1769AA]" />
        </div>
      }
    >
      <AcceptInvitationContent />
    </Suspense>
  );
}
