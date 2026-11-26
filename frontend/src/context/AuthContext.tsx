"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { subscribeSessionExpired } from "@/lib/auth-store";
import {
  acceptInvitationAndLogin,
  loginWithCredentials,
  logoutSession,
  restoreSession,
} from "@/lib/auth-service";
import { hasPermission as checkPerm, hasRole as checkRole } from "@/lib/rbac";
import type { AuthStatus, InvitationAcceptRequest, UserProfile } from "@/lib/types";

export interface AuthContextValue {
  status: AuthStatus;
  user: UserProfile | null;
  organizationId: string | null;
  organizationName: string | null;
  roles: string[];
  permissions: string[];
  sessionNotice: "session_expired" | "logged_out" | null;
  clearSessionNotice: () => void;
  login: (email: string, password: string) => Promise<UserProfile>;
  acceptInvitation: (payload: InvitationAcceptRequest) => Promise<UserProfile>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [sessionNotice, setSessionNotice] = useState<"session_expired" | "logged_out" | null>(null);

  useEffect(() => {
    let mounted = true;

    const init = async () => {
      const restoredUser = await restoreSession();
      if (!mounted) return;

      if (restoredUser) {
        setUser(restoredUser);
        setStatus("authenticated");
      } else {
        setUser(null);
        setStatus("unauthenticated");
      }
    };

    init();

    const unsubscribe = subscribeSessionExpired((reason) => {
      if (!mounted) return;
      setUser(null);
      setStatus("unauthenticated");
      setSessionNotice(reason);
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<UserProfile> => {
    const profile = await loginWithCredentials(email, password);
    setSessionNotice(null);
    setUser(profile);
    setStatus("authenticated");
    return profile;
  }, []);

  const acceptInvitation = useCallback(
    async (payload: InvitationAcceptRequest): Promise<UserProfile> => {
      const profile = await acceptInvitationAndLogin(payload);
      setSessionNotice(null);
      setUser(profile);
      setStatus("authenticated");
      return profile;
    },
    []
  );

  const logout = useCallback(async () => {
    await logoutSession();
    setUser(null);
    setStatus("unauthenticated");
    setSessionNotice("logged_out");
  }, []);

  const clearSessionNotice = useCallback(() => {
    setSessionNotice(null);
  }, []);

  const hasPermission = useCallback(
    (permission: string) => checkPerm(user, permission),
    [user]
  );

  const hasRole = useCallback(
    (role: string) => checkRole(user, role),
    [user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      organizationId: user?.organization_id ?? null,
      organizationName: user?.organization_name ?? null,
      roles: user?.roles ?? [],
      permissions: user?.permissions ?? [],
      sessionNotice,
      clearSessionNotice,
      login,
      acceptInvitation,
      logout,
      hasPermission,
      hasRole,
    }),
    [status, user, sessionNotice, clearSessionNotice, login, acceptInvitation, logout, hasPermission, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
