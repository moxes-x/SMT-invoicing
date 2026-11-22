import { forwardRef, type ComponentProps } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** A text input for amounts like "1,250.00". Parse with parseMoney(); never Number(). */
export const MoneyInput = forwardRef<
  HTMLInputElement,
  ComponentProps<"input"> & { prefix?: string }
>(function MoneyInput({ className, prefix = "K", ...props }, ref) {
  return (
    <div className="relative">
      <span className="text-muted-foreground pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm">
        {prefix}
      </span>
      <Input
        ref={ref}
        inputMode="decimal"
        autoComplete="off"
        placeholder="0.00"
        className={cn("pl-8 text-right tabular-nums", className)}
        {...props}
      />
    </div>
  );
});
