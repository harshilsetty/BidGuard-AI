import test from "node:test";
import assert from "node:assert/strict";

import {
  clearAccessToken,
  getAccessToken,
  resetAuthStoreForTest,
  setAccessToken,
  subscribeSessionExpired,
} from "../src/lib/auth-store";
import {
  apiFetch,
  ApiError,
  fetchTenderDocumentPages,
  fetchTenderDocuments,
  fetchTenderJobStatus,
  fetchTenders,
  performTokenRefresh,
  processTenderDocument,
  retryTenderJob,
  triggerClauseExtraction,
  uploadTenderDocument,
} from "../src/lib/api-client";
import {
  loginWithCredentials,
  logoutSession,
  restoreSession,
} from "../src/lib/auth-service";
import {
  canAccessRoute,
  canPerformAction,
  getAuthorizedNavItems,
  getRoleWorkspaceMetadata,
  hasAllPermissions,
  hasAnyPermission,
  hasPermission,
  isPublicRoute,
  sanitizeRedirectPath,
} from "../src/lib/rbac";
import type { UserProfile } from "../src/lib/types";

function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    email: "officer@org.gov.in",
    full_name: "Test Officer",
    organization_id: "22222222-2222-2222-2222-222222222222",
    organization_name: "Ministry of Procurement",
    roles: ["PROCUREMENT_OFFICER"],
    permissions: [
      "organization:read",
      "tender:create",
      "tender:read",
      "tender:update",
      "document:upload",
      "document:download",
      "evaluation:run",
      "evaluation:read",
      "evaluation:override",
      "audit:read",
    ],
    is_active: true,
    is_verified: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function createStorageSpy() {
  const store = new Map<string, string>();
  const writes: Array<{ key: string; value: string }> = [];
  return {
    writes,
    api: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        writes.push({ key: k, value: v });
        store.set(k, v);
      },
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    },
  };
}

test("Authentication: valid login stores access token in memory only and loads user profile", async () => {
  resetAuthStoreForTest();
  const lsSpy = createStorageSpy();
  const ssSpy = createStorageSpy();
  (globalThis as any).localStorage = lsSpy.api;
  (globalThis as any).sessionStorage = ssSpy.api;

  const calls: Array<{ url: string; init: RequestInit }> = [];
  const profile = makeProfile();

  (globalThis as any).fetch = async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    if (url.endsWith("/api/v1/auth/login")) {
      return new Response(
        JSON.stringify({
          access_token: "access-token-123",
          token_type: "bearer",
          expires_in: 900,
          user_id: profile.id,
          organization_id: profile.organization_id,
          roles: profile.roles,
          permissions: profile.permissions,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return new Response(JSON.stringify(profile), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const result = await loginWithCredentials("Officer@Org.Gov.In", "SecretPass123!");
  assert.equal(result.email, profile.email);
  assert.equal(result.organization_name, "Ministry of Procurement");
  assert.equal(getAccessToken(), "access-token-123");
  assert.equal(lsSpy.writes.length, 0);
  assert.equal(ssSpy.writes.length, 0);
  assert.equal(calls[0].init.credentials, "include");
  assert.equal(calls[1].init.credentials, "include");
  assert.equal(new Headers(calls[1].init.headers).get("Authorization"), "Bearer access-token-123");
});

test("Authentication: invalid credentials returns 401 ApiError and leaves token empty", async () => {
  resetAuthStoreForTest();
  (globalThis as any).fetch = async () =>
    new Response(JSON.stringify({ detail: "Invalid email or password." }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

  await assert.rejects(
    () => loginWithCredentials("bad@org.gov.in", "wrong"),
    (err: unknown) => err instanceof ApiError && err.status === 401
  );
  assert.equal(getAccessToken(), null);
});

test("Session restoration: succeeds via HttpOnly refresh cookie + /auth/me, returns null when unauthenticated", async () => {
  resetAuthStoreForTest();
  const profile = makeProfile();

  (globalThis as any).fetch = async (url: string) => {
    if (url.endsWith("/api/v1/auth/refresh")) {
      return new Response(
        JSON.stringify({
          access_token: "restored-token",
          token_type: "bearer",
          expires_in: 900,
          user_id: profile.id,
          organization_id: profile.organization_id,
          roles: profile.roles,
          permissions: profile.permissions,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return new Response(JSON.stringify(profile), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const restored = await restoreSession();
  assert.equal(restored?.id, profile.id);
  assert.equal(getAccessToken(), "restored-token");

  resetAuthStoreForTest();
  (globalThis as any).fetch = async () =>
    new Response(JSON.stringify({ detail: "Refresh token not found" }), { status: 401 });

  const anon = await restoreSession();
  assert.equal(anon, null);
  assert.equal(getAccessToken(), null);
});

test("Logout: revokes backend session, clears memory token, and notifies listeners", async () => {
  resetAuthStoreForTest();
  setAccessToken("active-token", 900);
  const events: string[] = [];
  subscribeSessionExpired((reason) => events.push(reason));

  let logoutCalled = false;
  (globalThis as any).fetch = async (url: string, init: RequestInit = {}) => {
    if (url.endsWith("/api/v1/auth/logout")) {
      logoutCalled = true;
      assert.equal(init.method, "POST");
      assert.equal(init.credentials, "include");
      return new Response(JSON.stringify({ message: "Logged out successfully." }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  await logoutSession();
  assert.equal(logoutCalled, true);
  assert.equal(getAccessToken(), null);
  assert.deepEqual(events, ["logged_out"]);
});

test("Refresh & Concurrency: 5 concurrent 401 GET requests trigger exactly 1 refresh and retry safely", async () => {
  resetAuthStoreForTest();
  setAccessToken("expired-token", 900);

  let refreshCount = 0;
  let tendersCalls = 0;

  (globalThis as any).fetch = async (url: string, init: RequestInit = {}) => {
    if (url.endsWith("/api/v1/auth/refresh")) {
      refreshCount += 1;
      await new Promise((r) => setTimeout(r, 15));
      return new Response(
        JSON.stringify({
          access_token: "fresh-rotated-token",
          token_type: "bearer",
          expires_in: 900,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    if (url.endsWith("/api/v1/tenders")) {
      tendersCalls += 1;
      const authHeader = new Headers(init.headers).get("Authorization");
      if (authHeader === "Bearer expired-token") {
        return new Response(JSON.stringify({ detail: "Token expired" }), { status: 401 });
      }
      if (authHeader === "Bearer fresh-rotated-token") {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    throw new Error(`Unexpected request: ${url}`);
  };

  const results = await Promise.all([
    fetchTenders(),
    fetchTenders(),
    fetchTenders(),
    fetchTenders(),
    fetchTenders(),
  ]);

  assert.equal(results.length, 5);
  assert.equal(refreshCount, 1);
  assert.equal(tendersCalls, 10);
  assert.equal(getAccessToken(), "fresh-rotated-token");
});

test("Security: non-idempotent POST is not blindly re-submitted after 401 refresh", async () => {
  resetAuthStoreForTest();
  setAccessToken("stale-token", 900);

  let postCalls = 0;
  let refreshCalls = 0;

  (globalThis as any).fetch = async (url: string) => {
    if (url.endsWith("/api/v1/auth/refresh")) {
      refreshCalls += 1;
      return new Response(
        JSON.stringify({ access_token: "new-token", expires_in: 900 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.includes("/extract")) {
      postCalls += 1;
      return new Response(JSON.stringify({ detail: "Expired" }), { status: 401 });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  await assert.rejects(
    () => triggerClauseExtraction("tender-1"),
    (err: unknown) => err instanceof ApiError && err.status === 401
  );
  assert.equal(postCalls, 1);
  assert.equal(refreshCalls, 1);
  assert.equal(getAccessToken(), "new-token");
});

test("Security: failed refresh / revoked session does not infinite-loop and emits session_expired", async () => {
  resetAuthStoreForTest();
  setAccessToken("revoked-token", 900);
  const events: string[] = [];
  subscribeSessionExpired((reason) => events.push(reason));

  let refreshCalls = 0;
  let apiCalls = 0;

  (globalThis as any).fetch = async (url: string) => {
    if (url.endsWith("/api/v1/auth/refresh")) {
      refreshCalls += 1;
      return new Response(JSON.stringify({ detail: "Reuse detected" }), { status: 401 });
    }
    apiCalls += 1;
    return new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 });
  };

  await assert.rejects(
    () => apiFetch("/api/v1/tenders"),
    (err: unknown) => err instanceof ApiError && err.status === 401
  );
  assert.equal(refreshCalls, 1);
  assert.equal(apiCalls, 1);
  assert.equal(getAccessToken(), null);
  assert.deepEqual(events, ["session_expired"]);
});

test("Security: backend 403 does not trigger refresh and preserves 403 status", async () => {
  resetAuthStoreForTest();
  setAccessToken("bidder-token", 900);

  let refreshCalls = 0;
  (globalThis as any).fetch = async (url: string) => {
    if (url.endsWith("/api/v1/auth/refresh")) {
      refreshCalls += 1;
    }
    return new Response(JSON.stringify({ detail: "Missing permission tender:create" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });
  };

  await assert.rejects(
    () => apiFetch("/api/v1/tenders/upload", { method: "POST" }),
    (err: unknown) =>
      err instanceof ApiError &&
      err.status === 403 &&
      err.detail.includes("tender:create")
  );
  assert.equal(refreshCalls, 0);
});

test("RBAC & Route Protection: enforces public, authenticated, and role-restricted routes", () => {
  assert.equal(isPublicRoute("/login"), true);
  assert.equal(isPublicRoute("/tenders/new"), false);

  // Anonymous user
  assert.equal(canAccessRoute(null, "/login"), true);
  assert.equal(canAccessRoute(null, "/"), false);
  assert.equal(canAccessRoute(null, "/tenders/new"), false);

  // BIDDER role: tender:read + evaluation:read only (no organization:read, no audit:read)
  const bidder = makeProfile({
    roles: ["BIDDER"],
    permissions: ["tender:read", "evaluation:read"],
  });
  assert.equal(canAccessRoute(bidder, "/"), true);
  assert.equal(canAccessRoute(bidder, "/tenders/abc/compliance"), true);
  assert.equal(canAccessRoute(bidder, "/tenders/new"), false);
  assert.equal(canAccessRoute(bidder, "/organization"), false);
  assert.equal(canAccessRoute(bidder, "/audit"), false);
  assert.equal(isPublicRoute("/invite/accept"), true);
  assert.equal(canAccessRoute(null, "/invite/accept"), true);
  assert.deepEqual(
    getAuthorizedNavItems(bidder).map((n) => n.href),
    ["/", "/mock-data"]
  );
  assert.equal(getRoleWorkspaceMetadata(bidder).role, "BIDDER");

  // AUDITOR role: read-only, has organization:read + audit:read, no tender:create
  const auditor = makeProfile({
    roles: ["AUDITOR"],
    permissions: [
      "organization:read",
      "tender:read",
      "document:download",
      "evaluation:read",
      "audit:read",
      "audit:export",
    ],
  });
  assert.equal(canAccessRoute(auditor, "/tenders/new"), false);
  assert.equal(canAccessRoute(auditor, "/organization"), true);
  assert.equal(canAccessRoute(auditor, "/audit"), true);
  assert.equal(canPerformAction(auditor, "evaluation:override"), false);
  assert.deepEqual(
    getAuthorizedNavItems(auditor).map((n) => n.href),
    ["/", "/organization", "/audit", "/mock-data"]
  );
  assert.equal(getRoleWorkspaceMetadata(auditor).role, "AUDITOR");

  // PROCUREMENT_OFFICER role: has tender:create, organization:read, audit:read
  const officer = makeProfile();
  assert.equal(canAccessRoute(officer, "/tenders/new"), true);
  assert.equal(canAccessRoute(officer, "/organization"), true);
  assert.equal(canAccessRoute(officer, "/audit"), true);
  assert.equal(canPerformAction(officer, ["tender:create", "evaluation:run"]), true);
  assert.equal(hasAnyPermission(officer, ["user:manage", "tender:create"]), true);
  assert.equal(hasAllPermissions(officer, ["user:manage", "tender:create"]), false);
  assert.deepEqual(
    getAuthorizedNavItems(officer).map((n) => n.href),
    ["/", "/tenders/new", "/organization", "/audit", "/mock-data"]
  );
  assert.equal(getRoleWorkspaceMetadata(officer).role, "PROCUREMENT_OFFICER");

  // ORG_ADMIN role: org admin + procurement
  const orgAdmin = makeProfile({
    roles: ["ORG_ADMIN"],
    permissions: ["organization:read", "organization:update", "user:invite", "user:manage", "tender:create", "tender:read", "evaluation:read", "audit:read"],
  });
  assert.equal(canAccessRoute(orgAdmin, "/organization"), true);
  assert.equal(canAccessRoute(orgAdmin, "/audit"), true);
  assert.equal(getRoleWorkspaceMetadata(orgAdmin).role, "ORG_ADMIN");

  // SUPER_ADMIN role: platform governance
  const superAdmin = makeProfile({ roles: ["SUPER_ADMIN"], permissions: [] });
  assert.equal(hasPermission(superAdmin, "tender:delete"), true);
  assert.equal(canAccessRoute(superAdmin, "/organization"), true);
  assert.equal(canAccessRoute(superAdmin, "/audit"), true);
  assert.equal(getRoleWorkspaceMetadata(superAdmin).role, "SUPER_ADMIN");

  // Redirect sanitization prevents open redirects
  assert.equal(sanitizeRedirectPath("https://evil.example"), "/");
  assert.equal(sanitizeRedirectPath("//evil.example"), "/");
  assert.equal(sanitizeRedirectPath("/login"), "/");
  assert.equal(sanitizeRedirectPath("/tenders/123/compliance"), "/tenders/123/compliance");
});

test("Single-flight refresh: direct concurrent performTokenRefresh calls coalesce to 1 fetch", async () => {
  resetAuthStoreForTest();
  let calls = 0;
  (globalThis as any).fetch = async () => {
    calls += 1;
    await new Promise((r) => setTimeout(r, 10));
    return new Response(
      JSON.stringify({ access_token: "coalesced-token", expires_in: 900 }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const tokens = await Promise.all([
    performTokenRefresh(),
    performTokenRefresh(),
    performTokenRefresh(),
  ]);

  assert.equal(calls, 1);
  assert.deepEqual(tokens, ["coalesced-token", "coalesced-token", "coalesced-token"]);
  clearAccessToken();
});

test("Error handling: network failure, 429 rate limit, 500, and malformed JSON return clean ApiError", async () => {
  resetAuthStoreForTest();
  setAccessToken("valid-token", 900);

  // Network failure -> ApiError(0, ...)
  (globalThis as any).fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(
    () => apiFetch("/api/v1/tenders"),
    (err: unknown) => err instanceof ApiError && err.status === 0
  );

  // 429 rate limit
  (globalThis as any).fetch = async () =>
    new Response(JSON.stringify({ detail: "Too many requests" }), {
      status: 429,
      headers: { "Content-Type": "application/json" },
    });
  await assert.rejects(
    () => apiFetch("/api/v1/tenders"),
    (err: unknown) => err instanceof ApiError && err.status === 429
  );

  // 500 with malformed non-JSON body
  (globalThis as any).fetch = async () =>
    new Response("Internal Server Error", { status: 500 });
  await assert.rejects(
    () => apiFetch("/api/v1/tenders", {}, "Server error fallback"),
    (err: unknown) =>
      err instanceof ApiError && err.status === 500 && err.detail === "Server error fallback"
  );
  clearAccessToken();
});

test("Phase 2.0A: tender multi-document upload, listing, duplicate 409, and permission gating", async () => {
  resetAuthStoreForTest();
  setAccessToken("officer-token", 900);

  const mockDoc = {
    id: "doc-1",
    tender_id: "tender-1",
    document_role: "CORRIGENDUM",
    original_filename: "corrigendum_1.pdf",
    file_size_bytes: 1024,
    sha256_hash: "a".repeat(64),
    total_pages: 2,
    processing_status: "UPLOADED",
    created_at: "2026-11-26T00:00:00Z",
    updated_at: "2026-11-26T00:00:00Z",
  };

  (globalThis as any).fetch = async (url: string, init: RequestInit = {}) => {
    if (url.endsWith("/api/v1/tenders/tender-1/documents") && init.method === "POST") {
      return new Response(JSON.stringify(mockDoc), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith("/api/v1/tenders/tender-1/documents") && (!init.method || init.method === "GET")) {
      return new Response(JSON.stringify([mockDoc]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d])], "corrigendum_1.pdf", {
    type: "application/pdf",
  });
  const uploaded = await uploadTenderDocument("tender-1", file, "CORRIGENDUM");
  assert.equal(uploaded.id, "doc-1");
  assert.equal(uploaded.document_role, "CORRIGENDUM");

  const list = await fetchTenderDocuments("tender-1");
  assert.equal(list.length, 1);

  // Duplicate 409 handling
  (globalThis as any).fetch = async () =>
    new Response(JSON.stringify({ detail: "Duplicate document" }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    });
  await assert.rejects(
    () => uploadTenderDocument("tender-1", file, "CORRIGENDUM"),
    (err: unknown) => err instanceof ApiError && err.status === 409
  );

  // Permission gating for upload UI
  const officer = makeProfile();
  const auditor = makeProfile({ roles: ["AUDITOR"], permissions: ["tender:read"] });
  assert.equal(hasPermission(officer, "tender:update"), true);
  assert.equal(hasPermission(auditor, "tender:update"), false);
  clearAccessToken();
});

test("Phase 2.0B: async document processing enqueue (202), job polling, retry, and page retrieval", async () => {
  resetAuthStoreForTest();
  setAccessToken("officer-token", 900);

  const mockJob = {
    id: "job-1",
    tender_id: "tender-1",
    tender_document_id: "doc-1",
    job_type: "PAGE_EXTRACTION",
    status: "QUEUED",
    current_stage: "QUEUED",
    progress_pct: 0,
    retry_count: 0,
    max_retries: 3,
    created_at: "2026-11-26T00:00:00Z",
    updated_at: "2026-11-26T00:00:00Z",
  };

  (globalThis as any).fetch = async (url: string, init: RequestInit = {}) => {
    if (url.endsWith("/documents/doc-1/process") && init.method === "POST") {
      return new Response(JSON.stringify(mockJob), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith("/jobs/job-1") && (!init.method || init.method === "GET")) {
      return new Response(
        JSON.stringify({ ...mockJob, status: "SUCCEEDED", current_stage: "FINALIZING", progress_pct: 100 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.endsWith("/jobs/job-1/retry") && init.method === "POST") {
      return new Response(JSON.stringify({ ...mockJob, retry_count: 1 }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("/documents/doc-1/pages")) {
      return new Response(
        JSON.stringify({ tender_id: "tender-1", tender_document_id: "doc-1", total: 1, limit: 20, offset: 0, items: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const enqueued = await processTenderDocument("tender-1", "doc-1");
  assert.equal(enqueued.status, "QUEUED");

  const polled = await fetchTenderJobStatus("tender-1", "job-1");
  assert.equal(polled.status, "SUCCEEDED");
  assert.equal(polled.progress_pct, 100);

  const retried = await retryTenderJob("tender-1", "job-1");
  assert.equal(retried.retry_count, 1);

  const pages = await fetchTenderDocumentPages("tender-1", "doc-1");
  assert.equal(pages.total, 1);
  clearAccessToken();
});
