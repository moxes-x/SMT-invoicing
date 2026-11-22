import type { components } from "./schema";

export type Me = components["schemas"]["Me"];
export type Business = components["schemas"]["Business"];
export type BusinessRequest = components["schemas"]["BusinessRequest"];

/** Field errors from DRF: { field: ["message"], non_field_errors: [...] } */
export class ApiError extends Error {
  readonly status: number;
  readonly fields: Record<string, string[]>;

  constructor(status: number, body: unknown) {
    const fields =
      body && typeof body === "object" ? (body as Record<string, string[] | string>) : {};
    const normalised: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(fields)) normalised[k] = Array.isArray(v) ? v : [String(v)];
    const message =
      normalised.detail?.[0] ?? normalised.non_field_errors?.[0] ?? `Request failed (${status})`;
    super(message);
    this.status = status;
    this.fields = normalised;
  }
}

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.split("=")[1];
}

let csrfReady: Promise<void> | null = null;
/** Make sure Django has set the csrftoken cookie before the first unsafe request. */
export function ensureCsrf(): Promise<void> {
  if (readCookie("csrftoken")) return Promise.resolve();
  csrfReady ??= fetch("/api/auth/csrf/", { credentials: "same-origin" }).then(() => undefined);
  return csrfReady;
}

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    await ensureCsrf();
    const token = readCookie("csrftoken");
    if (token) headers.set("X-CSRFToken", decodeURIComponent(token));
  }
  const res = await fetch(`/api${path}`, {
    ...init,
    method,
    headers,
    body,
    credentials: "same-origin",
  });
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}
