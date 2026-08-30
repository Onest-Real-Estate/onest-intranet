import { usePage } from "@inertiajs/react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

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

    if (flash.level === "success") {
      toast.success(flash.message);
    } else if (flash.level === "error") {
      toast.error(flash.message);
    } else {
      toast.message(flash.message);
    }
  }, [flash]);

  return null;
}
