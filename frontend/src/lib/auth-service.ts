import { apiFetch, ApiError, performTokenRefresh } from "./api-client";
import { clearAccessToken, notifySessionExpired, setAccessToken } from "./auth-store";
import type { InvitationAcceptRequest, TokenResponse, UserProfile } from "./types";

/**
 * Retrieve the currently authenticated user's profile and effective RBAC permissions.
 */
export async function fetchCurrentUser(): Promise<UserProfile> {
  return apiFetch<UserProfile>(
    "/api/v1/auth/me",
    { cache: "no-store" },
    "Failed to retrieve authenticated user profile"
  );
}

/**
 * Authenticate with email & password.
 * Stores the short-lived access token strictly in memory; the backend sets the HttpOnly refresh cookie.
 */
export async function loginWithCredentials(
  email: string,
  password: string
): Promise<UserProfile> {
  const tokenData = await apiFetch<TokenResponse>(
    "/api/v1/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      skipAuth: true,
    },
    "Invalid email or password."
  );

  setAccessToken(tokenData.access_token, tokenData.expires_in);

  try {
    return await fetchCurrentUser();
  } catch (err) {
    clearAccessToken();
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(500, "Failed to load user profile after authentication.");
  }
}

/**
 * Restore an existing session on app initialization using the HttpOnly refresh cookie.
 */
export async function restoreSession(): Promise<UserProfile | null> {
  const token = await performTokenRefresh();
  if (!token) {
    clearAccessToken();
    return null;
  }

  try {
    return await fetchCurrentUser();
  } catch {
    clearAccessToken();
    return null;
  }
}

/**
 * Accept a single-use organization invitation, store the resulting access token in memory,
 * and fetch the authenticated user profile.
 */
export async function acceptInvitationAndLogin(
  payload: InvitationAcceptRequest
): Promise<UserProfile> {
  const tokenData = await apiFetch<TokenResponse>(
    "/api/v1/auth/invitations/accept",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        email: payload.email.trim().toLowerCase(),
      }),
      skipAuth: true,
    },
    "Failed to accept invitation"
  );

  setAccessToken(tokenData.access_token, tokenData.expires_in);

  try {
    return await fetchCurrentUser();
  } catch (err) {
    clearAccessToken();
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(500, "Failed to load user profile after accepting invitation.");
  }
}

/**
 * Revoke the active refresh-token family on the backend and clear in-memory session state.
 */
export async function logoutSession(): Promise<void> {
  try {
    await apiFetch<{ message: string }>(
      "/api/v1/auth/logout",
      { method: "POST" },
      "Failed to revoke session"
    );
  } catch {
    // Always clear client session state even if the backend call fails
  } finally {
    clearAccessToken();
    notifySessionExpired("logged_out");
  }
}
