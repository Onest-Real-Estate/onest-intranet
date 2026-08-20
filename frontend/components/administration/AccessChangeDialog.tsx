import { ShieldAlert } from "lucide-react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";

export interface AccessChange {
  label: string;
  from: string;
  to: string;
  /** What this change does to the person's access, in plain words. */
  impact: string;
}

/**
 * The confirmation step for a change that moves somebody's access.
 *
 * Deliberately not a generic "are you sure": it lists the old value, the new
 * value, and what the change does, because an administrator confirming an
 * office move needs to know it also retires that person's Agent assignment in
 * their old office.
 */
export function AccessChangeDialog({
  open,
  onOpenChange,
  title,
  description,
  changes,
  confirmLabel,
  onConfirm,
  submitting = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  changes: AccessChange[];
  confirmLabel: string;
  onConfirm: () => void;
  submitting?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl">
        <DialogHeader>
          <span className="bg-warning/18 text-warning-ink grid size-10 place-items-center rounded-xl">
            <ShieldAlert className="size-5" aria-hidden />
          </span>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <ul className="grid gap-3">
          {changes.map((change) => (
            <li
              key={change.label}
              className="border-border/60 bg-muted/35 grid gap-2 rounded-xl border p-4"
            >
              <p className="text-sm font-semibold">{change.label}</p>
              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm">
                <span className="text-muted-foreground min-w-0 truncate line-through">
                  {change.from || "—"}
                </span>
                <span className="text-muted-foreground" aria-hidden>
                  →
                </span>
                <span className="sr-only">changes to</span>
                <strong className="min-w-0 truncate">{change.to || "—"}</strong>
              </div>
              <p className="text-muted-foreground text-xs leading-5">{change.impact}</p>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline" disabled={submitting}>
              Keep editing
            </Button>
          </DialogClose>
          <Button
            type="button"
            disabled={submitting}
            aria-busy={submitting || undefined}
            onClick={onConfirm}
          >
            {submitting ? "Applying…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
