import { usePage } from "@inertiajs/react";
import { useEffect, useRef } from "react";

import { showFlashToast } from "@/lib/flash-toast";
import type { PageProps } from "@/types";

/**
 * Renders shared ``flash`` props as Sonner toasts once per payload.
 * Mount inside the Inertia tree (e.g. HubLayout) so ``usePage`` works.
 */
export function FlashToasts() {
  const flash = usePage<PageProps>().props.flash;
  const lastKey = useRef<string>("");

  useEffect(() => {
    if (!flash?.message) {
      return;
    }
    const key = `${flash.level}:${flash.message}`;
    if (key === lastKey.current) {
      return;
    }
    lastKey.current = key;
    showFlashToast(flash.level, flash.message);
  }, [flash]);

  return null;
}
