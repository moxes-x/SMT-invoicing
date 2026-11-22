import {
  dehydrate,
  hydrate,
  onlineManager,
  useMutationState,
  type QueryClient,
} from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

/**
 * Keeps the last data the app loaded on this phone, so it opens and shows invoices,
 * customers and reports without a connection. Changes made offline wait (TanStack pauses
 * mutations) and are sent when the connection comes back, while the app stays open.
 */
const KEY = "invoicing-cache";
const VERSION = 1; // bump when cached shapes change
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_BYTES = 3_000_000;
// Short-lived or one-off data that shouldn't come back after a restart.
const SKIP = new Set(["invite"]);

interface Saved {
  version: number;
  savedAt: number;
  state: unknown;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // private mode, blocked storage
  }
}

export function clearSavedData(): void {
  try {
    storage()?.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** Load what was saved last time into the cache. Call once, before the first render. */
export function restoreSavedData(qc: QueryClient): void {
  try {
    const raw = storage()?.getItem(KEY);
    if (!raw) return;
    const saved = JSON.parse(raw) as Saved;
    if (saved.version !== VERSION || Date.now() - saved.savedAt > MAX_AGE_MS) {
      clearSavedData();
      return;
    }
    hydrate(qc, saved.state as Parameters<typeof hydrate>[1]);
  } catch {
    clearSavedData();
  }
}

/** Save the cache (successful queries only) whenever it changes, at most once a second. */
export function saveDataOnChange(qc: QueryClient): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    timer = undefined;
    // Logged out (or the session ended): nothing of this user's stays on the phone.
    if (qc.getQueryData(["me"]) === null) return clearSavedData();
    try {
      const state = dehydrate(qc, {
        shouldDehydrateQuery: (q) =>
          q.state.status === "success" && !SKIP.has(String(q.queryKey[0])),
      });
      const raw = JSON.stringify({ version: VERSION, savedAt: Date.now(), state });
      if (raw.length > MAX_BYTES) return;
      storage()?.setItem(KEY, raw);
    } catch {
      /* quota exceeded or storage blocked: the app still works online */
    }
  };
  const unsubscribe = qc.getQueryCache().subscribe(() => {
    timer ??= setTimeout(save, 1000);
  });
  // Leaving or backgrounding the app: save now rather than lose the last second.
  const flush = () => {
    if (timer) {
      clearTimeout(timer);
      save();
    }
  };
  const onHidden = () => document.visibilityState === "hidden" && flush();
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", onHidden);
  return () => {
    unsubscribe();
    if (timer) clearTimeout(timer);
    window.removeEventListener("pagehide", flush);
    document.removeEventListener("visibilitychange", onHidden);
  };
}

/** TanStack only listens for online/offline events, so an app opened offline would think it's
 * online. Start from the browser's own view; the "online" event then switches it back. */
export function syncInitialOnlineState(): void {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    onlineManager.setOnline(false);
  }
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => onlineManager.subscribe(cb),
    () => onlineManager.isOnline(),
    () => true,
  );
}

/** Changes made while offline that are waiting to be sent. */
export function useWaitingChanges(): number {
  return useMutationState({ filters: { predicate: (m) => m.state.isPaused } }).length;
}
