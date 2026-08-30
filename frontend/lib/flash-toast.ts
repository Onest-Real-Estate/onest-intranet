import { toast } from "sonner";

import type { FlashMessage } from "@/types";

/**
 * Levels aligned with Django ``messages`` tags and ``set_flash(..., level=)``.
 * ``debug`` is supported for parity; product flashes rarely use it.
 */
export const FLASH_LEVELS = [
  "debug",
  "info",
  "success",
  "warning",
  "error",
] as const satisfies readonly FlashMessage["level"][];

export type FlashLevel = (typeof FLASH_LEVELS)[number];

/**
 * Show a toast for a Django-style flash level.
 *
 * Used by ``FlashToasts`` after a redirect and by the design-system catalog
 * so demos cannot drift from production mapping.
 */
export function showFlashToast(level: string, message: string): void {
  switch (level) {
    case "success":
      toast.success(message);
      return;
    case "error":
      toast.error(message);
      return;
    case "warning":
      toast.warning(message);
      return;
    case "info":
      toast.info(message);
      return;
    case "debug":
      toast.message(message);
      return;
    default:
      toast.message(message);
  }
}
