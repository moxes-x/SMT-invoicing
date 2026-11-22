import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { meKey, type Role } from "./auth";
import { api } from "./client";
import type { components } from "./schema";

type S = components["schemas"];
export type Team = S["Team"];
export type TeamMember = S["TeamMember"];
export type InviteInfo = S["InviteInfo"];
export type TeamInvite = S["Invite"];

export const ROLES: { value: Role; label: string; help: string }[] = [
  { value: "owner", label: "Owner", help: "Everything, including the team" },
  { value: "admin", label: "Admin", help: "Everything except changing owners" },
  { value: "staff", label: "Staff", help: "Customers, invoices, quotes and payments" },
  {
    value: "accountant",
    label: "Accountant",
    help: "Sees everything and exports. Changes nothing.",
  },
];

export const roleLabel = (r: string = "") => ROLES.find((x) => x.value === r)?.label ?? r;

const teamKey = ["team"] as const;

export function useTeam() {
  return useQuery({ queryKey: teamKey, queryFn: () => api<Team>("/team/") });
}

function useTeamMutation<V>(fn: (v: V) => Promise<Team>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: (team) => qc.setQueryData(teamKey, team) });
}

export function useInvite() {
  return useTeamMutation((v: { email: string; role: Role }) =>
    api<Team>("/team/invites/", { method: "POST", json: v }),
  );
}

export function useRevokeInvite() {
  return useTeamMutation((id: number) => api<Team>(`/team/invites/${id}/`, { method: "DELETE" }));
}

export function useChangeRole() {
  return useTeamMutation((v: { id: number; role: Role }) =>
    api<Team>(`/team/members/${v.id}/`, { method: "PATCH", json: { role: v.role } }),
  );
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; self: boolean }) =>
      api<Team>(`/team/members/${v.id}/`, { method: "DELETE" }),
    onSuccess: (team, v) => {
      if (v.self) {
        // Left the business: everything cached belonged to it.
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        return qc.invalidateQueries({ queryKey: meKey });
      }
      qc.setQueryData(teamKey, team);
    },
  });
}

export function useInviteInfo(token: string) {
  return useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<InviteInfo>(`/auth/invites/${token}/`),
    retry: false,
  });
}

export function useAcceptInvite(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>(`/auth/invites/${token}/accept/`, { method: "POST" }),
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      await qc.invalidateQueries({ queryKey: meKey });
    },
  });
}
