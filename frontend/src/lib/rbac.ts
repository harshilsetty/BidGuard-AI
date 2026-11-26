import type { UserProfile } from "./types";

export interface NavItemConfig {
  href: string;
  label: string;
  requiredPermission?: string;
  badge?: string;
}

export const PUBLIC_ROUTES = ["/login"] as const;

/**
 * Navigation items derived strictly from backend RBAC permissions.
 * Backend remains the final authority for every API request.
 */
export const NAV_ITEMS: NavItemConfig[] = [
  {
    href: "/",
    label: "Tenders",
    requiredPermission: "tender:read",
  },
  {
    href: "/tenders/new",
    label: "Upload Tender PDF",
    requiredPermission: "tender:create",
  },
  {
    href: "/mock-data",
    label: "Mock Explorer",
    badge: "5K",
  },
];

export interface RoutePolicy {
  pattern: RegExp;
  requiredPermissions: string[];
  description: string;
}

/**
 * Frontend route-protection policy mapped to backend RBAC permissions.
 * - `/` -> requires `tender:read`
 * - `/tenders/new` -> requires `tender:create`
 * - `/tenders/:id/clauses` -> requires `tender:read`
 * - `/tenders/:id/bidders` -> requires `tender:read`
 * - `/tenders/:id/compliance` -> requires `evaluation:read`
 * - `/mock-data` -> any authenticated active user
 */
export const ROUTE_POLICIES: RoutePolicy[] = [
  {
    pattern: /^\/$/,
    requiredPermissions: ["tender:read"],
    description: "Tender dashboard",
  },
  {
    pattern: /^\/tenders\/new\/?$/,
    requiredPermissions: ["tender:create"],
    description: "Tender PDF upload and extraction",
  },
  {
    pattern: /^\/tenders\/[^/]+\/clauses\/?$/,
    requiredPermissions: ["tender:read"],
    description: "Tender clause review",
  },
  {
    pattern: /^\/tenders\/[^/]+\/bidders\/?$/,
    requiredPermissions: ["tender:read"],
    description: "Tender bidders management",
  },
  {
    pattern: /^\/tenders\/[^/]+\/compliance\/?$/,
    requiredPermissions: ["evaluation:read"],
    description: "Bidder compliance matrix & officer review",
  },
  {
    pattern: /^\/mock-data\/?$/,
    requiredPermissions: [],
    description: "Mock statutory data explorer",
  },
];

export function isPublicRoute(pathname: string): boolean {
  const normalized = pathname.split("?")[0] || "/";
  return PUBLIC_ROUTES.some(
    (route) => normalized === route || normalized.startsWith(`${route}/`)
  );
}

export function hasPermission(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined,
  permission: string
): boolean {
  if (!user) return false;
  if (user.roles.includes("SUPER_ADMIN")) return true;
  return user.permissions.includes(permission);
}

export function hasRole(
  user: Pick<UserProfile, "roles"> | null | undefined,
  role: string
): boolean {
  if (!user) return false;
  return user.roles.includes(role);
}

export function getRequiredPermissionsForRoute(pathname: string): string[] | null {
  const normalized = pathname.split("?")[0] || "/";
  for (const policy of ROUTE_POLICIES) {
    if (policy.pattern.test(normalized)) {
      return policy.requiredPermissions;
    }
  }
  return null;
}

export function canAccessRoute(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined,
  pathname: string
): boolean {
  if (isPublicRoute(pathname)) return true;
  if (!user) return false;

  const required = getRequiredPermissionsForRoute(pathname);
  if (required === null) {
    // Unknown route: let Next.js 404 handle it once authenticated
    return true;
  }
  return required.every((perm) => hasPermission(user, perm));
}

export function getAuthorizedNavItems(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined
): NavItemConfig[] {
  if (!user) return [];
  return NAV_ITEMS.filter(
    (item) => !item.requiredPermission || hasPermission(user, item.requiredPermission)
  );
}

/**
 * Sanitize post-login redirect paths to prevent open redirects.
 */
export function sanitizeRedirectPath(nextPath: string | null | undefined): string {
  if (!nextPath || typeof nextPath !== "string") return "/";
  const trimmed = nextPath.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return "/";
  if (trimmed.startsWith("/login")) return "/";
  return trimmed;
}
