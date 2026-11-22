import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [qc] = useState(
    () => client ?? new QueryClient({ defaultOptions: { queries: { retry: 1 } } }),
  );
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
