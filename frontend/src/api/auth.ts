import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type BusinessRequest, type Business, type Me } from "./client";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await api<Me>("/auth/me/");
      } catch (err) {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return null;
        throw err;
      }
    },
    staleTime: 60_000,
  });
}

export interface Credentials {
  email: string;
  password: string;
  full_name?: string;
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: Credentials) => api<Me>("/auth/login/", { method: "POST", json: c }),
    onSuccess: (me) => qc.setQueryData(meKey, me),
  });
}

export function useSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: Credentials) => api<Me>("/auth/signup/", { method: "POST", json: c }),
    onSuccess: (me) => qc.setQueryData(meKey, me),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout/", { method: "POST" }),
    onSuccess: () => {
      qc.setQueryData(meKey, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  });
}

export function useCreateBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: BusinessRequest) => api<Business>("/businesses/", { method: "POST", json: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}
