import { useSyncExternalStore } from "react";

/** Chrome/Android's "Add to home screen" prompt, captured so the app can offer it in More. */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export function listenForInstallPrompt(): void {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e as InstallPromptEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    notify();
  });
}

export function useInstallPrompt(): (() => Promise<void>) | null {
  const available = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => deferred !== null,
    () => false,
  );
  if (!available) return null;
  return async () => {
    const e = deferred;
    if (!e) return;
    await e.prompt();
    await e.userChoice;
    deferred = null;
    notify();
  };
}
