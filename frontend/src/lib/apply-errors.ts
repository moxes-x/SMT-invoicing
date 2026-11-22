import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/api/client";

/** Push DRF field errors into react-hook-form; returns a top-level message, if any. */
export function applyApiErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
): string | null {
  if (!(err instanceof ApiError))
    return "Something went wrong. Check your connection and try again.";
  let unmatched: string | null = null;
  for (const [key, messages] of Object.entries(err.fields)) {
    if ((fields as readonly string[]).includes(key)) {
      setError(key as Path<T>, { message: messages[0] });
    } else {
      unmatched ??= messages[0] ?? null;
    }
  }
  return unmatched ?? (Object.keys(err.fields).length ? null : err.message);
}
