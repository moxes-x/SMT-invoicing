import { ReceiptText } from "lucide-react";
import type { ReactNode } from "react";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="bg-muted/40 flex min-h-svh flex-col items-center justify-center gap-6 p-4">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md">
          <ReceiptText className="size-5" />
        </span>
        Invoicing
      </div>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
