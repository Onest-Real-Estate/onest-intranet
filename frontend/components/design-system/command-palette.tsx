import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Search } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A Spotlight-style command palette.
 *
 * Distinct from `Dialog` on purpose. A dialog is a decision you are asked to
 * make: it is centred, padded, titled, and has a close button, because it
 * interrupts. A palette is a place you *go*: it sits near the top where the
 * eye already is, carries no visible chrome, and closes the moment you have
 * what you came for. Giving them the same component would mean one of them
 * wearing the other's manners.
 *
 * It is still a Radix dialog underneath, so it keeps everything that makes an
 * overlay usable — focus trap, Escape, scroll lock, and `aria-modal` — and
 * carries an accessible name that is visually hidden rather than absent.
 */
export function CommandPalette({
  open,
  onOpenChange,
  label,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Accessible name. Visually hidden — the input is the visible affordance. */
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="bg-foreground/35 data-[state=closed]:animate-dialog-overlay-out data-[state=open]:animate-dialog-overlay-in fixed inset-0 z-50 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className={cn(
            "animate-palette bg-card text-card-foreground shadow-popover",
            // Anchored a fifth of the way down rather than centred: a palette
            // opens where the eye already is, and a growing result list then
            // extends downward instead of shifting the input under the cursor.
            "fixed top-[12vh] left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2",
            "grid overflow-hidden rounded-2xl border p-0 outline-none",
          )}
        >
          <DialogPrimitive.Title className="sr-only">{label}</DialogPrimitive.Title>
          {description ? (
            <DialogPrimitive.Description className="sr-only">
              {description}
            </DialogPrimitive.Description>
          ) : null}
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/**
 * The palette's query row: one borderless input on the surface itself.
 *
 * No box inside a box — the palette *is* the field, which is what makes it read
 * as a single object rather than a dialog containing a form.
 */
export function CommandPaletteInput({
  className,
  ...props
}: React.ComponentProps<"input">) {
  return (
    <div className="border-border/60 flex items-center gap-3 border-b px-4">
      <Search className="text-muted-foreground size-5 shrink-0" aria-hidden />
      <input
        type="text"
        autoComplete="off"
        spellCheck={false}
        className={cn(
          "placeholder:text-muted-foreground h-14 w-full min-w-0 bg-transparent text-base outline-none",
          className,
        )}
        {...props}
      />
    </div>
  );
}

/** The scrolling result region. Collapses to nothing when there is no content. */
export function CommandPaletteList({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("max-h-[min(24rem,50svh)] overflow-y-auto p-2", className)}
      {...props}
    />
  );
}

/** A small caps label above one group of options. */
export function CommandPaletteGroupLabel({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "text-muted-foreground px-3 pt-3 pb-1.5 text-[11px] font-semibold tracking-[0.06em] uppercase",
        className,
      )}
      {...props}
    />
  );
}

/**
 * One selectable row.
 *
 * `active` is *roving selection*, not focus: focus stays in the input so typing
 * never breaks, and the active row is pointed at with `aria-activedescendant`.
 * That is what lets the arrow keys move a highlight while the caret keeps
 * receiving characters.
 */
export function CommandPaletteOption({
  active,
  className,
  ...props
}: React.ComponentProps<"a"> & { active: boolean }) {
  return (
    <a
      role="option"
      aria-selected={active}
      className={cn(
        "grid scroll-m-2 gap-0.5 rounded-lg px-3 py-2.5 transition-colors",
        active ? "bg-muted" : "hover:bg-muted/60",
        className,
      )}
      {...props}
    />
  );
}

/**
 * The source filter strip.
 *
 * A `tablist` rather than a row of buttons, so a screen reader announces "tab,
 * 2 of 5" and the arrow keys are the expected way to move between them. The
 * strip only earns its space when there is more than one source to choose
 * between — a single tab is a label pretending to be a control.
 */
export function CommandPaletteTabs({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      role="tablist"
      className={cn(
        "border-border/60 flex items-center gap-1 overflow-x-auto border-b px-2 py-1.5",
        className,
      )}
      {...props}
    />
  );
}

export function CommandPaletteTab({
  active,
  count,
  className,
  children,
  ...props
}: Omit<React.ComponentProps<"button">, "type"> & {
  active: boolean;
  count?: number;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      className={cn(
        "focus-visible:ring-ring flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:outline-none",
        active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-muted",
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined ? (
        <span className={cn("tabular-nums", active ? "" : "text-muted-foreground/70")}>
          {count}
        </span>
      ) : null}
    </button>
  );
}

/** The palette's footer hint strip — the keys that work, said once. */
export function CommandPaletteFooter({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "border-border/60 text-muted-foreground flex items-center gap-4 border-t px-4 py-2.5 text-[11px]",
        className,
      )}
      {...props}
    />
  );
}

export function CommandPaletteKey({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="border-border/60 bg-muted/60 rounded border px-1.5 py-0.5 font-sans text-[10px] font-medium">
      {children}
    </kbd>
  );
}
