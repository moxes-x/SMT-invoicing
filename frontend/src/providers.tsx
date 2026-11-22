import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { restoreSavedData, saveDataOnChange, syncInitialOnlineState } from "@/lib/offline";

const DAY = 24 * 60 * 60 * 1000;

function makeClient(): QueryClient {
  // Keep loaded data for a day (not 5 minutes) so it's there to save and to show offline.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, gcTime: DAY } } });
  restoreSavedData(qc);
  syncInitialOnlineState();
  return qc;
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [qc] = useState(() => client ?? makeClient());
  useEffect(() => (client ? undefined : saveDataOnChange(qc)), [qc, client]);
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
