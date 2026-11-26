"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Building2,
  Check,
  CheckCircle2,
  Copy,
  KeyRound,
  Loader2,
  MailPlus,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserMinus,
  Users,
  XCircle,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import {
  ApiError,
  createOrganizationInvitation,
  fetchMyOrganization,
  fetchOrganizationInvitations,
  fetchOrganizationMembers,
  fetchOrganizationRoles,
  removeOrganizationMember,
  resendOrganizationInvitation,
  revokeOrganizationInvitation,
  updateMemberRole,
  updateMemberStatus,
  updateMyOrganization,
} from "@/lib/api-client";
import type {
  InvitationCreateResponse,
  OrganizationInvitationItem,
  OrganizationMember,
  OrganizationProfile,
  RoleSummary,
} from "@/lib/types";

type OrgTab = "overview" | "profile" | "members" | "invitations" | "roles";

const PAGE_SIZE = 10;

export default function OrganizationPage() {
  const { user, hasPermission } = useAuth();
  const canEditOrg = hasPermission("organization:update");
  const canManageMembers = hasPermission("user:manage");
  const canInvite = hasPermission("user:invite");

  const [activeTab, setActiveTab] = useState<OrgTab>("overview");
  const [org, setOrg] = useState<OrganizationProfile | null>(null);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [loadingOrg, setLoadingOrg] = useState(true);
  const [orgError, setOrgError] = useState<string | null>(null);

  // Profile edit state
  const [profileName, setProfileName] = useState("");
  const [profileDomain, setProfileDomain] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Members state
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersOffset, setMembersOffset] = useState(0);
  const [memberSearch, setMemberSearch] = useState("");
  const [memberRoleFilter, setMemberRoleFilter] = useState("");
  const [memberStatusFilter, setMemberStatusFilter] = useState<string>("all");
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [memberActionMessage, setMemberActionMessage] = useState<string | null>(null);
  const [busyMemberId, setBusyMemberId] = useState<string | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  // Invitations state
  const [invitations, setInvitations] = useState<OrganizationInvitationItem[]>([]);
  const [invitationsTotal, setInvitationsTotal] = useState(0);
  const [invitationsOffset, setInvitationsOffset] = useState(0);
  const [invitationStatusFilter, setInvitationStatusFilter] = useState<string>("");
  const [loadingInvitations, setLoadingInvitations] = useState(false);
  const [invitationsError, setInvitationsError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("PROCUREMENT_OFFICER");
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [inviteFormError, setInviteFormError] = useState<string | null>(null);
  const [issuedInvite, setIssuedInvite] = useState<InvitationCreateResponse | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [busyInviteId, setBusyInviteId] = useState<string | null>(null);

  const loadOrganizationSummary = useCallback(async () => {
    setLoadingOrg(true);
    setOrgError(null);
    try {
      const [orgData, roleList] = await Promise.all([
        fetchMyOrganization(),
        fetchOrganizationRoles(),
      ]);
      setOrg(orgData);
      setProfileName(orgData.name);
      setProfileDomain(orgData.domain || "");
      setRoles(roleList);
    } catch (err) {
      setOrgError(err instanceof Error ? err.message : "Failed to load organization.");
    } finally {
      setLoadingOrg(false);
    }
  }, []);

  const loadMembers = useCallback(async () => {
    setLoadingMembers(true);
    setMembersError(null);
    try {
      const isActiveParam =
        memberStatusFilter === "active"
          ? true
          : memberStatusFilter === "inactive"
            ? false
            : null;
      const res = await fetchOrganizationMembers({
        q: memberSearch,
        role: memberRoleFilter,
        isActive: isActiveParam,
        limit: PAGE_SIZE,
        offset: membersOffset,
      });
      setMembers(res.items);
      setMembersTotal(res.total);
    } catch (err) {
      setMembersError(err instanceof Error ? err.message : "Failed to load members.");
    } finally {
      setLoadingMembers(false);
    }
  }, [memberSearch, memberRoleFilter, memberStatusFilter, membersOffset]);

  const loadInvitations = useCallback(async () => {
    if (!canInvite) return;
    setLoadingInvitations(true);
    setInvitationsError(null);
    try {
      const res = await fetchOrganizationInvitations({
        status: invitationStatusFilter || undefined,
        limit: PAGE_SIZE,
        offset: invitationsOffset,
      });
      setInvitations(res.items);
      setInvitationsTotal(res.total);
    } catch (err) {
      setInvitationsError(err instanceof Error ? err.message : "Failed to load invitations.");
    } finally {
      setLoadingInvitations(false);
    }
  }, [canInvite, invitationStatusFilter, invitationsOffset]);

  useEffect(() => {
    loadOrganizationSummary();
  }, [loadOrganizationSummary]);

  useEffect(() => {
    if (activeTab === "members") {
      loadMembers();
    }
  }, [activeTab, loadMembers]);

  useEffect(() => {
    if (activeTab === "invitations" && canInvite) {
      loadInvitations();
    }
  }, [activeTab, canInvite, loadInvitations]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMessage(null);
    setProfileError(null);
    if (!profileName.trim() || profileName.trim().length < 2) {
      setProfileError("Organization name must be at least 2 characters.");
      return;
    }

    setSavingProfile(true);
    try {
      const updated = await updateMyOrganization({
        name: profileName.trim(),
        domain: profileDomain.trim() || null,
      });
      setOrg(updated);
      setProfileName(updated.name);
      setProfileDomain(updated.domain || "");
      setProfileMessage("Organization profile updated.");
    } catch (err) {
      setProfileError(
        err instanceof ApiError ? err.detail : "Failed to update organization profile."
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const handleRoleChange = async (memberId: string, newRole: string) => {
    setMemberActionMessage(null);
    setMembersError(null);
    setBusyMemberId(memberId);
    try {
      await updateMemberRole(memberId, newRole);
      setMemberActionMessage("Member role updated.");
      await Promise.all([loadMembers(), loadOrganizationSummary()]);
    } catch (err) {
      setMembersError(err instanceof ApiError ? err.detail : "Failed to update member role.");
    } finally {
      setBusyMemberId(null);
    }
  };

  const handleStatusToggle = async (member: OrganizationMember) => {
    setMemberActionMessage(null);
    setMembersError(null);
    setBusyMemberId(member.id);
    try {
      await updateMemberStatus(member.id, !member.is_active);
      setMemberActionMessage(
        !member.is_active ? "Member reactivated." : "Member deactivated and sessions revoked."
      );
      await Promise.all([loadMembers(), loadOrganizationSummary()]);
    } catch (err) {
      setMembersError(err instanceof ApiError ? err.detail : "Failed to update member status.");
    } finally {
      setBusyMemberId(null);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    setMemberActionMessage(null);
    setMembersError(null);
    setBusyMemberId(memberId);
    try {
      await removeOrganizationMember(memberId);
      setConfirmRemoveId(null);
      setMemberActionMessage("Member removed from organization.");
      await Promise.all([loadMembers(), loadOrganizationSummary()]);
    } catch (err) {
      setMembersError(err instanceof ApiError ? err.detail : "Failed to remove member.");
    } finally {
      setBusyMemberId(null);
    }
  };

  const handleCreateInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteFormError(null);
    setIssuedInvite(null);
    setCopiedLink(false);

    const cleanedEmail = inviteEmail.trim().toLowerCase();
    if (!cleanedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanedEmail)) {
      setInviteFormError("Enter a valid work email address.");
      return;
    }

    setCreatingInvite(true);
    try {
      const created = await createOrganizationInvitation(cleanedEmail, inviteRole);
      setIssuedInvite(created);
      setInviteEmail("");
      await Promise.all([loadInvitations(), loadOrganizationSummary()]);
    } catch (err) {
      setInviteFormError(
        err instanceof ApiError ? err.detail : "Failed to create invitation."
      );
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleRevokeInvitation = async (invitationId: string) => {
    setInvitationsError(null);
    setBusyInviteId(invitationId);
    try {
      await revokeOrganizationInvitation(invitationId);
      await Promise.all([loadInvitations(), loadOrganizationSummary()]);
    } catch (err) {
      setInvitationsError(
        err instanceof ApiError ? err.detail : "Failed to revoke invitation."
      );
    } finally {
      setBusyInviteId(null);
    }
  };

  const handleResendInvitation = async (invitationId: string) => {
    setInvitationsError(null);
    setIssuedInvite(null);
    setCopiedLink(false);
    setBusyInviteId(invitationId);
    try {
      const resent = await resendOrganizationInvitation(invitationId);
      setIssuedInvite(resent);
      await Promise.all([loadInvitations(), loadOrganizationSummary()]);
    } catch (err) {
      setInvitationsError(
        err instanceof ApiError ? err.detail : "Failed to resend invitation."
      );
    } finally {
      setBusyInviteId(null);
    }
  };

  const buildAcceptanceLink = (token: string) => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    return `${origin}/invite/accept?token=${encodeURIComponent(token)}`;
  };

  const handleCopyInviteLink = async (token: string) => {
    try {
      await navigator.clipboard.writeText(buildAcceptanceLink(token));
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    } catch {
      setInviteFormError("Clipboard write failed. Copy the link manually from the field below.");
    }
  };

  const assignableRoles = roles.filter((r) => r.assignable_by_org_admin);

  const tabs: Array<{ id: OrgTab; label: string; visible: boolean }> = [
    { id: "overview", label: "Organization Overview", visible: true },
    { id: "profile", label: "Organization Profile", visible: true },
    { id: "members", label: "Team Members", visible: true },
    { id: "invitations", label: "Invitations", visible: canInvite },
    { id: "roles", label: "Role Management", visible: true },
  ];

  if (loadingOrg) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-[#1769AA]" />
      </div>
    );
  }

  if (orgError && !org) {
    return (
      <div className="bg-white border border-red-200 rounded-xl p-6 text-sm text-red-700 flex items-center space-x-2">
        <AlertCircle className="w-5 h-5 shrink-0" />
        <span>{orgError}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-[#101C32] text-white rounded-xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <Building2 className="w-5 h-5 text-[#EAF2FA]" />
            <h1 className="text-xl font-bold tracking-tight">{org?.name}</h1>
            <span
              className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                org?.is_active
                  ? "bg-[#16856B]/20 text-emerald-200 border border-emerald-400/30"
                  : "bg-red-500/20 text-red-200 border border-red-400/30"
              }`}
            >
              {org?.is_active ? "Active Organization" : "Inactive"}
            </span>
          </div>
          <p className="text-xs text-slate-300 font-mono">
            Slug: {org?.slug} • Domain: {org?.domain || "Not set"}
          </p>
        </div>
        <button
          type="button"
          onClick={loadOrganizationSummary}
          className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-white/10 hover:bg-white/20 border border-white/15 transition self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Sub-navigation tabs */}
      <div className="border-b border-slate-200 flex flex-wrap gap-1">
        {tabs
          .filter((t) => t.visible)
          .map((tab) => {
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition ${
                  active
                    ? "border-[#1769AA] text-[#1769AA] bg-[#EAF2FA]/50"
                    : "border-transparent text-slate-600 hover:text-[#101C32] hover:bg-slate-50"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
      </div>

      {/* 1. OVERVIEW TAB */}
      {activeTab === "overview" && org && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Active Members
              </p>
              <p className="text-2xl font-bold text-[#101C32]">
                {org.active_members}
                <span className="text-xs font-normal text-slate-500 ml-1.5">
                  / {org.total_members} total
                </span>
              </p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Pending Invitations
              </p>
              <p className="text-2xl font-bold text-[#1769AA]">{org.pending_invitations}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Created On
              </p>
              <p className="text-sm font-semibold text-[#101C32] pt-1">
                {new Date(org.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <h2 className="text-sm font-bold text-[#101C32]">Administrative Actions</h2>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => setActiveTab("members")}
                className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#EAF2FA] text-[#1769AA] hover:bg-blue-100 transition"
              >
                <Users className="w-4 h-4" />
                <span>View Team Members</span>
              </button>
              {canInvite && (
                <button
                  type="button"
                  onClick={() => setActiveTab("invitations")}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#1769AA] text-white hover:bg-[#13568c] transition"
                >
                  <MailPlus className="w-4 h-4" />
                  <span>Invite Team Member</span>
                </button>
              )}
              {canEditOrg && (
                <button
                  type="button"
                  onClick={() => setActiveTab("profile")}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold border border-slate-300 text-[#101C32] hover:bg-slate-50 transition"
                >
                  <Building2 className="w-4 h-4" />
                  <span>Edit Organization Profile</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 2. PROFILE TAB */}
      {activeTab === "profile" && org && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 max-w-2xl space-y-5">
          <div>
            <h2 className="text-base font-bold text-[#101C32]">Organization Profile</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Editable fields require <span className="font-mono">organization:update</span>{" "}
              permission. System-managed fields are read-only.
            </p>
          </div>

          {profileMessage && (
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{profileMessage}</span>
            </div>
          )}
          {profileError && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{profileError}</span>
            </div>
          )}

          <form onSubmit={handleSaveProfile} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="org-name" className="block text-xs font-semibold text-[#101C32]">
                Organization Name
              </label>
              <input
                id="org-name"
                type="text"
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                disabled={!canEditOrg || savingProfile}
                className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] disabled:bg-slate-50 disabled:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#1769AA]/20 focus:border-[#1769AA]"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="org-domain" className="block text-xs font-semibold text-[#101C32]">
                Verified Domain (optional)
              </label>
              <input
                id="org-domain"
                type="text"
                value={profileDomain}
                onChange={(e) => setProfileDomain(e.target.value)}
                placeholder="procurement.gov.in"
                disabled={!canEditOrg || savingProfile}
                className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] disabled:bg-slate-50 disabled:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#1769AA]/20 focus:border-[#1769AA]"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-100 text-xs">
              <div>
                <span className="text-slate-500 block">Organization ID (System)</span>
                <span className="font-mono text-[#101C32] break-all">{org.id}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Slug (System)</span>
                <span className="font-mono text-[#101C32]">{org.slug}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Status (System)</span>
                <span className="font-semibold text-[#16856B]">
                  {org.is_active ? "Active" : "Inactive"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Created At (System)</span>
                <span className="text-[#101C32]">{new Date(org.created_at).toLocaleString()}</span>
              </div>
            </div>

            {canEditOrg && (
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={savingProfile}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition disabled:opacity-60"
                >
                  {savingProfile && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Save Changes</span>
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* 3. TEAM MEMBERS TAB */}
      {activeTab === "members" && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-[#101C32]">Team Members ({membersTotal})</h2>
              <p className="text-xs text-slate-500">
                Server-filtered membership directory scoped to your authenticated organization.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="search"
                  value={memberSearch}
                  onChange={(e) => {
                    setMemberSearch(e.target.value);
                    setMembersOffset(0);
                  }}
                  placeholder="Search name or email..."
                  aria-label="Search members"
                  className="pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 text-xs text-[#101C32] focus:outline-none focus:border-[#1769AA]"
                />
              </div>

              <select
                value={memberRoleFilter}
                onChange={(e) => {
                  setMemberRoleFilter(e.target.value);
                  setMembersOffset(0);
                }}
                aria-label="Filter by role"
                className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs text-[#101C32] bg-white"
              >
                <option value="">All Roles</option>
                {roles.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>

              <select
                value={memberStatusFilter}
                onChange={(e) => {
                  setMemberStatusFilter(e.target.value);
                  setMembersOffset(0);
                }}
                aria-label="Filter by status"
                className="px-2.5 py-1.5 rounded-lg border border-slate-300 text-xs text-[#101C32] bg-white"
              >
                <option value="all">All Statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>

          {memberActionMessage && (
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{memberActionMessage}</span>
            </div>
          )}
          {membersError && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{membersError}</span>
            </div>
          )}

          {loadingMembers ? (
            <div className="py-10 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-[#1769AA]" />
            </div>
          ) : members.length === 0 ? (
            <div className="py-10 text-center text-xs text-slate-500">
              No members match your current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[11px]">
                    <th className="py-2.5 pr-4 font-semibold">Member</th>
                    <th className="py-2.5 px-4 font-semibold">Role</th>
                    <th className="py-2.5 px-4 font-semibold">Status</th>
                    <th className="py-2.5 px-4 font-semibold">Joined</th>
                    {canManageMembers && (
                      <th className="py-2.5 pl-4 font-semibold text-right">Actions</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {members.map((m) => {
                    const currentRole = m.roles[0] || "BIDDER";
                    const isSelf = user?.id === m.id;
                    const isSuper = m.roles.includes("SUPER_ADMIN");
                    const isBusy = busyMemberId === m.id;

                    return (
                      <tr key={m.id} className="hover:bg-slate-50/70">
                        <td className="py-3 pr-4">
                          <div className="font-semibold text-[#101C32]">
                            {m.full_name}
                            {isSelf && (
                              <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-[#EAF2FA] text-[#1769AA]">
                                You
                              </span>
                            )}
                          </div>
                          <div className="text-slate-500">{m.email}</div>
                        </td>
                        <td className="py-3 px-4">
                          {canManageMembers && !isSelf && !isSuper ? (
                            <select
                              aria-label={`Role for ${m.email}`}
                              value={currentRole}
                              disabled={isBusy}
                              onChange={(e) => handleRoleChange(m.id, e.target.value)}
                              className="px-2 py-1 rounded border border-slate-300 text-xs bg-white text-[#101C32]"
                            >
                              {assignableRoles.map((r) => (
                                <option key={r.name} value={r.name}>
                                  {r.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-100 text-[#101C32] font-medium">
                              {m.roles.join(", ") || "UNASSIGNED"}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full font-semibold text-[11px] ${
                              m.is_active
                                ? "bg-emerald-50 text-[#16856B] border border-emerald-200"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}
                          >
                            {m.is_active ? "Active" : "Deactivated"}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-600">
                          {new Date(m.created_at).toLocaleDateString()}
                        </td>
                        {canManageMembers && (
                          <td className="py-3 pl-4 text-right space-x-2">
                            {!isSelf && !isSuper && (
                              <>
                                <button
                                  type="button"
                                  disabled={isBusy}
                                  onClick={() => handleStatusToggle(m)}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-100 transition disabled:opacity-50"
                                >
                                  {m.is_active ? (
                                    <>
                                      <UserMinus className="w-3 h-3" />
                                      <span>Deactivate</span>
                                    </>
                                  ) : (
                                    <>
                                      <UserCheck className="w-3 h-3" />
                                      <span>Reactivate</span>
                                    </>
                                  )}
                                </button>

                                {confirmRemoveId === m.id ? (
                                  <span className="inline-flex items-center space-x-1">
                                    <button
                                      type="button"
                                      disabled={isBusy}
                                      onClick={() => handleRemoveMember(m.id)}
                                      className="px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700"
                                    >
                                      Confirm Remove
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setConfirmRemoveId(null)}
                                      className="px-2 py-1 rounded border border-slate-300 text-slate-600"
                                    >
                                      Cancel
                                    </button>
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    disabled={isBusy}
                                    onClick={() => setConfirmRemoveId(m.id)}
                                    className="inline-flex items-center space-x-1 px-2.5 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50 transition disabled:opacity-50"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                    <span>Remove</span>
                                  </button>
                                )}
                              </>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {membersTotal > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-3 border-t border-slate-100 text-xs text-slate-600">
              <span>
                Showing {membersOffset + 1}–{Math.min(membersOffset + PAGE_SIZE, membersTotal)} of{" "}
                {membersTotal}
              </span>
              <div className="space-x-2">
                <button
                  type="button"
                  disabled={membersOffset === 0}
                  onClick={() => setMembersOffset(Math.max(0, membersOffset - PAGE_SIZE))}
                  className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={membersOffset + PAGE_SIZE >= membersTotal}
                  onClick={() => setMembersOffset(membersOffset + PAGE_SIZE)}
                  className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 4. INVITATIONS TAB */}
      {activeTab === "invitations" && canInvite && (
        <div className="space-y-6">
          {/* Create Invitation Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-[#101C32]">Invite Team Member</h2>
                <p className="text-xs text-slate-500">
                  Generates a single-use, 48-hour expiring invitation scoped to{" "}
                  <span className="font-semibold text-[#101C32]">{org?.name}</span>.
                </p>
              </div>
              <span className="inline-flex items-center px-2.5 py-1 rounded text-[11px] font-medium bg-amber-50 text-amber-900 border border-amber-200">
                Out-of-band delivery: Email transport not configured
              </span>
            </div>

            {inviteFormError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{inviteFormError}</span>
              </div>
            )}

            <form onSubmit={handleCreateInvitation} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@organization.gov.in"
                aria-label="Invitee email"
                className="px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] focus:outline-none focus:border-[#1769AA]"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                aria-label="Assigned role"
                className="px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-[#101C32] bg-white"
              >
                {assignableRoles.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={creatingInvite}
                className="inline-flex items-center justify-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold bg-[#1769AA] hover:bg-[#13568c] text-white transition disabled:opacity-60"
              >
                {creatingInvite ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <MailPlus className="w-4 h-4" />
                )}
                <span>Create Invitation</span>
              </button>
            </form>

            {issuedInvite && (
              <div className="p-4 rounded-lg bg-[#EAF2FA] border border-blue-200 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-[#101C32]">
                    Invitation created for <span className="font-mono">{issuedInvite.email}</span> (
                    {issuedInvite.role_name}) — share this single-use link out-of-band:
                  </p>
                  <button
                    type="button"
                    onClick={() => handleCopyInviteLink(issuedInvite.invitation_token)}
                    className="inline-flex items-center space-x-1 px-3 py-1 rounded bg-[#1769AA] text-white text-xs font-semibold hover:bg-[#13568c] shrink-0"
                  >
                    {copiedLink ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedLink ? "Copied" : "Copy Link"}</span>
                  </button>
                </div>
                <input
                  type="text"
                  readOnly
                  value={buildAcceptanceLink(issuedInvite.invitation_token)}
                  aria-label="Invitation acceptance link"
                  className="w-full px-3 py-1.5 rounded bg-white border border-blue-200 font-mono text-xs text-[#101C32]"
                />
                <p className="text-[11px] text-slate-600">
                  Expires at {new Date(issuedInvite.expires_at).toLocaleString()}. Email delivery
                  status: <span className="font-mono">{issuedInvite.email_delivery_status}</span>.
                </p>
              </div>
            )}
          </div>

          {/* Invitation History Table */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <h3 className="text-sm font-bold text-[#101C32]">
                Invitations ({invitationsTotal})
              </h3>
              <select
                value={invitationStatusFilter}
                onChange={(e) => {
                  setInvitationStatusFilter(e.target.value);
                  setInvitationsOffset(0);
                }}
                aria-label="Filter invitations by status"
                className="px-3 py-1.5 rounded-lg border border-slate-300 text-xs bg-white text-[#101C32]"
              >
                <option value="">All Statuses</option>
                <option value="PENDING">Pending</option>
                <option value="ACCEPTED">Accepted</option>
                <option value="EXPIRED">Expired</option>
                <option value="REVOKED">Revoked</option>
              </select>
            </div>

            {invitationsError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs">
                {invitationsError}
              </div>
            )}

            {loadingInvitations ? (
              <div className="py-8 flex justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-[#1769AA]" />
              </div>
            ) : invitations.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No invitations found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[11px]">
                      <th className="py-2.5 pr-4 font-semibold">Email</th>
                      <th className="py-2.5 px-4 font-semibold">Role</th>
                      <th className="py-2.5 px-4 font-semibold">Status</th>
                      <th className="py-2.5 px-4 font-semibold">Expires</th>
                      <th className="py-2.5 pl-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {invitations.map((inv) => {
                      const isBusy = busyInviteId === inv.id;
                      return (
                        <tr key={inv.id}>
                          <td className="py-3 pr-4 font-medium text-[#101C32]">{inv.email}</td>
                          <td className="py-3 px-4 font-mono">{inv.role_name}</td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                                inv.status === "PENDING"
                                  ? "bg-amber-50 text-amber-800 border border-amber-200"
                                  : inv.status === "ACCEPTED"
                                    ? "bg-emerald-50 text-[#16856B] border border-emerald-200"
                                    : inv.status === "REVOKED"
                                      ? "bg-red-50 text-red-700 border border-red-200"
                                      : "bg-slate-100 text-slate-600 border border-slate-200"
                              }`}
                            >
                              {inv.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-slate-600">
                            {new Date(inv.expires_at).toLocaleString()}
                          </td>
                          <td className="py-3 pl-4 text-right space-x-2">
                            {(inv.status === "PENDING" || inv.status === "EXPIRED") && (
                              <button
                                type="button"
                                disabled={isBusy}
                                onClick={() => handleResendInvitation(inv.id)}
                                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded border border-slate-300 text-[#1769AA] hover:bg-[#EAF2FA] transition disabled:opacity-50"
                              >
                                <RefreshCw className="w-3 h-3" />
                                <span>Resend</span>
                              </button>
                            )}
                            {inv.status === "PENDING" && (
                              <button
                                type="button"
                                disabled={isBusy}
                                onClick={() => handleRevokeInvitation(inv.id)}
                                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50 transition disabled:opacity-50"
                              >
                                <XCircle className="w-3 h-3" />
                                <span>Revoke</span>
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 5. ROLE MANAGEMENT TAB */}
      {activeTab === "roles" && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
          <div>
            <h2 className="text-base font-bold text-[#101C32]">RBAC Role Matrix</h2>
            <p className="text-xs text-slate-500">
              Authoritative backend role definitions. <span className="font-mono">SUPER_ADMIN</span>{" "}
              is platform-scoped and cannot be assigned through organization invitations or member
              controls.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {roles.map((r) => (
              <div
                key={r.name}
                className="border border-slate-200 rounded-lg p-4 space-y-2.5 bg-slate-50/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Shield className="w-4 h-4 text-[#1769AA]" />
                    <span className="font-bold text-xs text-[#101C32]">{r.name}</span>
                  </div>
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                      r.assignable_by_org_admin
                        ? "bg-[#EAF2FA] text-[#1769AA]"
                        : "bg-slate-200 text-slate-700"
                    }`}
                  >
                    {r.assignable_by_org_admin ? "Org Assignable" : "Platform Only"}
                  </span>
                </div>
                <p className="text-xs text-slate-600">{r.description}</p>
                <div className="flex flex-wrap gap-1 pt-1">
                  {r.permissions.map((p) => (
                    <span
                      key={p}
                      className="px-1.5 py-0.5 rounded bg-white border border-slate-200 font-mono text-[10px] text-slate-700"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
