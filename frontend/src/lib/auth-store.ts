/**
 * In-memory access token and single-flight refresh manager.
 *
 * Security invariants:
 * - Access tokens live strictly in module memory (never localStorage or sessionStorage).
 * - Refresh tokens are managed exclusively by the backend via HttpOnly cookies.
 * - Concurrent 401/refresh calls share a single in-flight refresh Promise.
 */

export type SessionExpiredListener = (reason: "session_expired" | "logged_out") => void;

export interface RefreshTokenPayload {
  access_token: string;
  expires_in: number;
}

let inMemoryAccessToken: string | null = null;
let accessTokenExpiresAtMs: number | null = null;
let inFlightRefresh: Promise<string | null> | null = null;
const expiredListeners = new Set<SessionExpiredListener>();

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

export function getAccessTokenExpiresAt(): number | null {
  return accessTokenExpiresAtMs;
}

export function isAccessTokenExpiringSoon(bufferSeconds = 45): boolean {
  if (!inMemoryAccessToken || accessTokenExpiresAtMs === null) {
    return false;
  }
  return Date.now() + bufferSeconds * 1000 >= accessTokenExpiresAtMs;
}

export function setAccessToken(token: string, expiresInSeconds?: number): void {
  inMemoryAccessToken = token;
  if (typeof expiresInSeconds === "number" && expiresInSeconds > 0) {
    accessTokenExpiresAtMs = Date.now() + expiresInSeconds * 1000;
  } else {
    accessTokenExpiresAtMs = null;
  }
}

export function clearAccessToken(): void {
  inMemoryAccessToken = null;
  accessTokenExpiresAtMs = null;
}

export function subscribeSessionExpired(listener: SessionExpiredListener): () => void {
  expiredListeners.add(listener);
  return () => {
    expiredListeners.delete(listener);
  };
}

export function notifySessionExpired(reason: "session_expired" | "logged_out"): void {
  for (const listener of Array.from(expiredListeners)) {
    listener(reason);
  }
}

/**
 * Execute a single-flight refresh operation.
 * Concurrent callers await the same Promise until it settles.
 */
export async function runSingleFlightRefresh(
  refreshFn: () => Promise<RefreshTokenPayload | null>
): Promise<string | null> {
  if (inFlightRefresh) {
    return inFlightRefresh;
  }

  inFlightRefresh = (async () => {
    try {
      const result = await refreshFn();
      if (!result || !result.access_token) {
        clearAccessToken();
        return null;
      }
      setAccessToken(result.access_token, result.expires_in);
      return result.access_token;
    } catch {
      clearAccessToken();
      return null;
    } finally {
      inFlightRefresh = null;
    }
  })();

  return inFlightRefresh;
}

/**
 * Reset store state (primarily for unit tests).
 */
export function resetAuthStoreForTest(): void {
  clearAccessToken();
  inFlightRefresh = null;
  expiredListeners.clear();
}
