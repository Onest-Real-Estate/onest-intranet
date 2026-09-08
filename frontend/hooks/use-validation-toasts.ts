import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { hasValidationErrors, validationEntries } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

type Options = {
  title?: string;
};

/**
 * When Inertia returns validation errors after a mutating visit, surface them
 * as a toast instead of a sticky page-top banner.
 */
export function useValidationToasts(
  errors: ValidationErrors | undefined,
  options: Options = {},
) {
  const lastFingerprint = useRef<string>("");

  useEffect(() => {
    if (!hasValidationErrors(errors)) {
      lastFingerprint.current = "";
      return;
    }
    const entries = validationEntries(errors);
    const fingerprint = entries
      .map((entry) => `${entry.id}:${entry.message}`)
      .join("|");
    if (fingerprint === lastFingerprint.current) {
      return;
    }
    lastFingerprint.current = fingerprint;

    const fieldEntries = entries.filter((entry) => entry.field);
    const formEntries = entries.filter((entry) => !entry.field);

    // Form-only refusals (lifecycle, permissions) are the message itself —
    // "Check the highlighted fields" is misleading when nothing is highlighted.
    if (fieldEntries.length === 0 && formEntries.length === 1) {
      toast.error(formEntries[0]?.message ?? "Something went wrong", {
        duration: 8_000,
      });
      return;
    }

    const title =
      options.title ??
      (fieldEntries.length > 0
        ? "Check the highlighted fields"
        : "Could not complete that action");
    const description = entries
      .map((entry) =>
        entry.field ? `${entry.label}: ${entry.message}` : entry.message,
      )
      .join("\n");

    toast.error(title, {
      description,
      duration: 8_000,
    });
  }, [errors, options.title]);
}
