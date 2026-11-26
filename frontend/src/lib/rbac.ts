import type { UserProfile, UserRole } from "./types";

export type NavGroup = "Workspace" | "Procurement" | "Administration" | "Diagnostics";

export type NavIconKey =
  | "dashboard"
  | "tenders"
  | "upload"
  | "organization"
  | "audit"
  | "mock";

export interface NavItemConfig {
  id: string;
  href: string;
  label: string;
  icon: NavIconKey;
  group: NavGroup;
  requiredPermissions?: string[];
  badge?: string;
}

export const PUBLIC_ROUTES = ["/login", "/invite/accept"] as const;

/**
 * Centralized permission-driven navigation configuration.
 * Every item maps strictly to real backend RBAC permissions.
 */
export const NAV_ITEMS: NavItemConfig[] = [
  {
    id: "workspace-home",
    href: "/",
    label: "Workspace",
    icon: "dashboard",
    group: "Workspace",
    requiredPermissions: ["tender:read"],
  },
  {
    id: "tender-upload",
    href: "/tenders/new",
    label: "Upload Tender PDF",
    icon: "upload",
    group: "Procurement",
    requiredPermissions: ["tender:create"],
  },
  {
    id: "organization-admin",
    href: "/organization",
    label: "Organization",
    icon: "organization",
    group: "Administration",
    requiredPermissions: ["organization:read"],
  },
  {
    id: "audit-trail",
    href: "/audit",
    label: "Audit Logs",
    icon: "audit",
    group: "Administration",
    requiredPermissions: ["audit:read"],
  },
  {
    id: "mock-explorer",
    href: "/mock-data",
    label: "Mock Explorer",
    icon: "mock",
    group: "Diagnostics",
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
 */
export const ROUTE_POLICIES: RoutePolicy[] = [
  {
    pattern: /^\/$/,
    requiredPermissions: ["tender:read"],
    description: "Role-aware workspace and tenders overview",
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
    pattern: /^\/organization(?:\/.*)?$/,
    requiredPermissions: ["organization:read"],
    description: "Organization overview, profile, members, and invitations",
  },
  {
    pattern: /^\/audit\/?$/,
    requiredPermissions: ["audit:read"],
    description: "Security and compliance audit trail",
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

export function hasAnyPermission(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined,
  permissions: string[]
): boolean {
  if (!user) return false;
  if (permissions.length === 0) return true;
  return permissions.some((p) => hasPermission(user, p));
}

export function hasAllPermissions(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined,
  permissions: string[]
): boolean {
  if (!user) return false;
  return permissions.every((p) => hasPermission(user, p));
}

export function canPerformAction(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined,
  required: string | string[]
): boolean {
  const list = Array.isArray(required) ? required : [required];
  return hasAllPermissions(user, list);
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
    return true;
  }
  return hasAllPermissions(user, required);
}

export function getAuthorizedNavItems(
  user: Pick<UserProfile, "roles" | "permissions"> | null | undefined
): NavItemConfig[] {
  if (!user) return [];
  return NAV_ITEMS.filter(
    (item) =>
      !item.requiredPermissions ||
      item.requiredPermissions.length === 0 ||
      hasAllPermissions(user, item.requiredPermissions)
  );
}

export interface RoleWorkspaceMetadata {
  role: UserRole;
  title: string;
  subtitle: string;
  accessSummary: string;
  futureBoundaryNote?: string;
}

export function getRoleWorkspaceMetadata(
  user: Pick<UserProfile, "roles"> | null | undefined
): RoleWorkspaceMetadata {
  const roles = user?.roles ?? [];
  if (roles.includes("SUPER_ADMIN")) {
    return {
      role: "SUPER_ADMIN",
      title: "Platform Governance Workspace",
      subtitle: "Cross-tenant oversight, organization governance, and audit inspection.",
      accessSummary: "Full platform permissions active via SUPER_ADMIN policy.",
      futureBoundaryNote:
        "Cross-tenant organization directory and billing controls are reserved for future platform-admin phases.",
    };
  }
  if (roles.includes("ORG_ADMIN")) {
    return {
      role: "ORG_ADMIN",
      title: "Organization Administration & Procurement",
      subtitle: "Manage organization identity, team memberships, invitations, and tender operations.",
      accessSummary: "Organization administration + procurement operational permissions.",
    };
  }
  if (roles.includes("PROCUREMENT_OFFICER")) {
    return {
      role: "PROCUREMENT_OFFICER",
      title: "Procurement Operations Workspace",
      subtitle: "Ingest GeM tenders, review extracted clauses, and execute compliance evaluations.",
      accessSummary: "Tender creation, evaluation execution, and officer review permissions.",
    };
  }
  if (roles.includes("AUDITOR")) {
    return {
      role: "AUDITOR",
      title: "Evidence & Oversight Workspace",
      subtitle: "Read-only inspection of compliance matrices, source provenance, and immutable audit logs.",
      accessSummary: "Strict read-only oversight (tender:read, evaluation:read, audit:read).",
    };
  }
  return {
    role: "BIDDER",
    title: "Bidder Participation Workspace",
    subtitle: "Inspect permitted tender requirements and compliance evaluation status.",
    accessSummary: "Restricted read-only access (tender:read, evaluation:read).",
    futureBoundaryNote:
      "Dedicated self-service bidder profile and bid-submission portals are reserved for upcoming phases.",
  };
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
