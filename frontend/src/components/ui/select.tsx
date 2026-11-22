import * as React from "react";

import { cn } from "@/lib/utils";

/** Native select: best UX on phones (OS picker), zero JS, accessible by default. */
export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive flex h-11 w-full rounded-md border px-3 text-base shadow-xs outline-none focus-visible:ring-[3px] disabled:opacity-50 sm:h-9 sm:text-sm",
        className,
      )}
      {...props}
    />
  );
}
