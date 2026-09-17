import { router } from "@inertiajs/react";
import { useEffect, useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";

/**
 * Guards a section with unsaved local edits.
 *
 * The browser's own unload prompt covers closing the tab or reloading. Inertia
 * GET visits — the stepper, Back, an Edit link on review — are intercepted and
 * held until the reader decides. Partial reloads (after a photo upload) and
 * the section's own POST are never held.
 */
export function useUnsavedChangesGuard(dirty: boolean) {
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);
  const bypass = useRef(false);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    const removeRouterGuard = router.on("before", (event) => {
      const visit = event.detail.visit;
      if (bypass.current || visit.method !== "get" || visit.only.length > 0) {
        return;
      }
      setPendingUrl(visit.url.href);
      return false;
    });
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      removeRouterGuard();
    };
  }, [dirty]);

  return {
    pendingUrl,
    stay: () => setPendingUrl(null),
    leave: () => {
      const url = pendingUrl;
      setPendingUrl(null);
      if (!url) {
        return;
      }
      bypass.current = true;
      router.visit(url, {
        onFinish: () => {
          bypass.current = false;
        },
      });
    },
  };
}

export function UnsavedChangesDialog({
  open,
  onStay,
  onLeave,
  title = "Leave this section without saving?",
  description = "The changes you made here have not been saved. Everything you saved earlier stays exactly as it was.",
  leaveLabel = "Discard changes",
  stayLabel = "Keep editing",
}: {
  open: boolean;
  onStay: () => void;
  onLeave: () => void;
  title?: string;
  description?: string;
  leaveLabel?: string;
  stayLabel?: string;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onStay();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onLeave}>
            {leaveLabel}
          </Button>
          <Button type="button" onClick={onStay} autoFocus>
            {stayLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
