import { QueryClient } from "@tanstack/react-query";

import { clearSavedData, restoreSavedData, saveDataOnChange } from "./offline";

const KEY = "invoicing-cache";

describe("saved data for offline use", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    clearSavedData();
  });
  afterEach(() => vi.useRealTimers());

  it("saves successful queries and restores them in a new session", () => {
    const qc = new QueryClient();
    const stop = saveDataOnChange(qc);
    qc.setQueryData(["me"], { user: { email: "a@example.com" } });
    qc.setQueryData(["customers", "list", ""], { results: [{ id: 1, name: "Bwalya" }] });
    qc.setQueryData(["invite", "t"], { business: "X" });
    vi.advanceTimersByTime(1100);
    stop();

    const next = new QueryClient();
    restoreSavedData(next);
    expect(next.getQueryData(["customers", "list", ""])).toEqual({
      results: [{ id: 1, name: "Bwalya" }],
    });
    expect(next.getQueryData(["invite", "t"])).toBeUndefined();
  });

  it("forgets everything once logged out", () => {
    const qc = new QueryClient();
    const stop = saveDataOnChange(qc);
    qc.setQueryData(["customers", "list", ""], { results: [] });
    vi.advanceTimersByTime(1100);
    expect(localStorage.getItem(KEY)).not.toBeNull();
    qc.setQueryData(["me"], null);
    vi.advanceTimersByTime(1100);
    expect(localStorage.getItem(KEY)).toBeNull();
    stop();
  });

  it("ignores old or broken saved data", () => {
    localStorage.setItem(KEY, "{not json");
    restoreSavedData(new QueryClient());
    expect(localStorage.getItem(KEY)).toBeNull();
    localStorage.setItem(KEY, JSON.stringify({ version: 1, savedAt: 0, state: {} }));
    restoreSavedData(new QueryClient());
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});
