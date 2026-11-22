import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { meKey } from "./auth";
import { api } from "./client";
import type { components } from "./schema";

type S = components["schemas"];
export type Customer = S["Customer"];
export type CustomerRequest = S["CustomerRequest"];
export type Item = S["Item"];
export type ItemRequest = S["ItemRequest"];
export type Invoice = S["Invoice"];
export type InvoiceListItem = S["InvoiceList"];
export type InvoiceRequest = S["InvoiceRequest"];
export type InvoiceLineRequest = S["InvoiceLineRequest"];
export type Payment = S["Payment"];
export type PaymentRequest = S["PaymentRequest"];
export type Dashboard = S["Dashboard"];
export type DisplayStatus = Invoice["display_status"];
export type PaymentMethod = NonNullable<PaymentRequest["method"]>;
export type BusinessRequest = S["PatchedBusinessRequest"];

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ---- customers -----------------------------------------------------------------------------
export const customerKeys = {
  all: ["customers"] as const,
  list: (search: string) => ["customers", "list", search] as const,
  detail: (id: number) => ["customers", id] as const,
};

export function useCustomers(search = "") {
  return useQuery({
    queryKey: customerKeys.list(search),
    queryFn: () => api<Page<Customer>>(`/customers/${qs({ search, page_size: 100 })}`),
    placeholderData: keepPreviousData,
  });
}

export function useCustomer(id: number | undefined) {
  return useQuery({
    queryKey: customerKeys.detail(id ?? 0),
    queryFn: () => api<Customer>(`/customers/${id}/`),
    enabled: !!id,
  });
}

export function useSaveCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: CustomerRequest & { id?: number }) =>
      id
        ? api<Customer>(`/customers/${id}/`, { method: "PATCH", json: body })
        : api<Customer>("/customers/", { method: "POST", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKeys.all }),
  });
}

export function useDeleteCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/customers/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKeys.all }),
  });
}

// ---- items ---------------------------------------------------------------------------------
export const itemKeys = { all: ["items"] as const, list: (s: string) => ["items", s] as const };

export function useItems(search = "") {
  return useQuery({
    queryKey: itemKeys.list(search),
    queryFn: () => api<Page<Item>>(`/items/${qs({ search })}`),
    placeholderData: keepPreviousData,
  });
}

export function useSaveItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: ItemRequest & { id?: number }) =>
      id
        ? api<Item>(`/items/${id}/`, { method: "PATCH", json: body })
        : api<Item>("/items/", { method: "POST", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: itemKeys.all }),
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/items/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: itemKeys.all }),
  });
}

// ---- invoices ------------------------------------------------------------------------------
export const invoiceKeys = {
  all: ["invoices"] as const,
  list: (f: InvoiceFilters) => ["invoices", "list", f] as const,
  detail: (id: number) => ["invoices", id] as const,
};

export interface InvoiceFilters {
  status?: string;
  search?: string;
  customer?: number;
}

export function useInvoices(filters: InvoiceFilters = {}) {
  return useQuery({
    queryKey: invoiceKeys.list(filters),
    queryFn: () => api<Page<InvoiceListItem>>(`/invoices/${qs({ ...filters })}`),
    placeholderData: keepPreviousData,
  });
}

export function useInvoice(id: number | undefined) {
  return useQuery({
    queryKey: invoiceKeys.detail(id ?? 0),
    queryFn: () => api<Invoice>(`/invoices/${id}/`),
    enabled: !!id,
  });
}

/** Every invoice change can move dashboard numbers and lists, so refresh them together. */
function useInvalidateMoney() {
  const qc = useQueryClient();
  return (extra: QueryKey[] = []) =>
    Promise.all(
      [invoiceKeys.all, ["dashboard"], ["payments"], ...extra].map((queryKey) =>
        qc.invalidateQueries({ queryKey }),
      ),
    );
}

export function useSaveInvoice() {
  const invalidate = useInvalidateMoney();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: InvoiceRequest & { id?: number }) =>
      id
        ? api<Invoice>(`/invoices/${id}/`, { method: "PATCH", json: body })
        : api<Invoice>("/invoices/", { method: "POST", json: body }),
    onSuccess: (inv) => {
      qc.setQueryData(invoiceKeys.detail(inv.id), inv);
      return invalidate();
    },
  });
}

type InvoiceAction = "send" | "void" | "reissue";

export function useInvoiceAction(id: number) {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: ({ action, reason }: { action: InvoiceAction; reason?: string }) =>
      api<Invoice>(`/invoices/${id}/${action}/`, {
        method: "POST",
        json: reason ? { reason } : {},
      }),
    onSuccess: () => invalidate(),
  });
}

export function useRecordPayment(id: number) {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: (body: PaymentRequest) =>
      api<Payment>(`/invoices/${id}/payments/`, { method: "POST", json: body }),
    onSuccess: () => invalidate(),
  });
}

export function useDeletePayment() {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: (paymentId: number) => api<void>(`/payments/${paymentId}/`, { method: "DELETE" }),
    onSuccess: () => invalidate(),
  });
}

// ---- dashboard & business ------------------------------------------------------------------
export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard/") });
}

export function useUpdateBusiness(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BusinessRequest) =>
      api<S["Business"]>(`/businesses/${id}/`, { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });
}

// ---- Phase 2: sending, reminders, quotes, recurring ------------------------------------------
export type Quote = S["Quote"];
export type QuoteListItem = S["QuoteList"];
export type QuoteRequest = S["QuoteRequest"];
export type QuoteDisplayStatus = Quote["display_status"];
export type Recurring = S["RecurringInvoice"];
export type RecurringRequest = S["RecurringInvoiceRequest"];
export type Delivery = S["Delivery"];
export type SendChannel = S["SendRequestRequest"]["channel"];
export type SendResult = S["SendResult"];

export function useAppConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: () => api<S["Config"]>("/config/"),
    staleTime: 5 * 60_000,
  });
}

export interface SendBody {
  channel: SendChannel;
  to?: string;
  message?: string;
}

/** Send an invoice (deliver) or chase it (remind). */
export function useSendInvoice(id: number, kind: "deliver" | "remind") {
  const invalidate = useInvalidateMoney();
  return useMutation({
    mutationFn: (body: SendBody) =>
      api<SendResult>(`/invoices/${id}/${kind}/`, { method: "POST", json: body }),
    onSuccess: () => invalidate(),
  });
}

export function usePauseReminders(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paused: boolean) =>
      api<Invoice>(`/invoices/${id}/reminders/`, { method: "POST", json: { paused } }),
    onSuccess: (inv) => qc.setQueryData(invoiceKeys.detail(inv.id), inv),
  });
}

export const quoteKeys = {
  all: ["quotes"] as const,
  list: (f: { status?: string; search?: string }) => ["quotes", "list", f] as const,
  detail: (id: number) => ["quotes", id] as const,
};

export function useQuotes(filters: { status?: string; search?: string } = {}) {
  return useQuery({
    queryKey: quoteKeys.list(filters),
    queryFn: () => api<Page<QuoteListItem>>(`/quotes/${qs({ ...filters })}`),
    placeholderData: keepPreviousData,
  });
}

export function useQuote(id: number | undefined) {
  return useQuery({
    queryKey: quoteKeys.detail(id ?? 0),
    queryFn: () => api<Quote>(`/quotes/${id}/`),
    enabled: !!id,
  });
}

export function useSaveQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: QuoteRequest & { id?: number }) =>
      id
        ? api<Quote>(`/quotes/${id}/`, { method: "PATCH", json: body })
        : api<Quote>("/quotes/", { method: "POST", json: body }),
    onSuccess: (q) => {
      qc.setQueryData(quoteKeys.detail(q.id), q);
      return qc.invalidateQueries({ queryKey: quoteKeys.all });
    },
  });
}

export function useQuoteAction(id: number) {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: quoteKeys.all }),
      qc.invalidateQueries({ queryKey: invoiceKeys.all }),
      qc.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  return {
    send: useMutation({
      mutationFn: (body: SendBody) =>
        api<SendResult>(`/quotes/${id}/deliver/`, { method: "POST", json: body }),
      onSuccess: refresh,
    }),
    respond: useMutation({
      mutationFn: (accepted: boolean) =>
        api<Quote>(`/quotes/${id}/respond/`, { method: "POST", json: { accepted } }),
      onSuccess: refresh,
    }),
    convert: useMutation({
      mutationFn: (days_until_due: number) =>
        api<{ id: number; number: string }>(`/quotes/${id}/convert/`, {
          method: "POST",
          json: { days_until_due },
        }),
      onSuccess: refresh,
    }),
  };
}

export const recurringKeys = {
  all: ["recurring"] as const,
  detail: (id: number) => ["recurring", id] as const,
};

export function useRecurringList() {
  return useQuery({
    queryKey: recurringKeys.all,
    queryFn: () => api<Page<Recurring>>("/recurring/"),
  });
}

export function useRecurring(id: number | undefined) {
  return useQuery({
    queryKey: recurringKeys.detail(id ?? 0),
    queryFn: () => api<Recurring>(`/recurring/${id}/`),
    enabled: !!id,
  });
}

export function useSaveRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<RecurringRequest> & { id?: number }) =>
      id
        ? api<Recurring>(`/recurring/${id}/`, { method: "PATCH", json: body })
        : api<Recurring>("/recurring/", { method: "POST", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: recurringKeys.all }),
  });
}

export function useDeleteRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/recurring/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: recurringKeys.all }),
  });
}
