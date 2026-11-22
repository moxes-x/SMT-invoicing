/** A same-site path to return to after logging in or signing up (`?next=/join/…`), or null. */
export function safeNext(params: URLSearchParams): string | null {
  const next = params.get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

export function withNext(path: string, next: string | null): string {
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}
