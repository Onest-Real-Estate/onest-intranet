import { ChevronDown, ListFilter, RotateCcw } from "lucide-react";
import type * as React from "react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The filter toolbar for a list view: the search field, one button that names
 * the region and carries the count of what is currently narrowing the list,
 * the fields themselves, and a reset that only exists while there is something
 * to reset.
 *
 * The panel starts **closed**, so an untouched list page opens as a search box
 * and a button rather than as a wall of empty dropdowns. Filtering is the
 * exception on most visits; paying for it in vertical space on every visit is
 * the wrong default.
 *
 * The one case that would break — a reader who cannot see the constraint and
 * blames the data instead of the filter — is handled by opening the panel when
 * something is already narrowing the list. Arriving on a filtered URL, or
 * coming back to one, shows the fields that are doing it. The count on the
 * button and the reset beside it stay visible either way.
 */
export function FilterControls({
  children,
  leading,
  activeCount = 0,
  onReset,
  disabled = false,
  collapsible = true,
  defaultOpen,
  className,
  ...props
}: React.ComponentProps<"section"> & {
  /**
   * The list's search field, placed on the toggle's own row. Searching and
   * filtering are the same job — stacking them cost a whole row of the page
   * to say so twice.
   */
  leading?: React.ReactNode;
  activeCount?: number;
  onReset?: () => void;
  disabled?: boolean;
  /** False where the fields are the page's primary control, as on a report. */
  collapsible?: boolean;
  /**
   * Force the initial state. Unset means "open only if something is already
   * filtering", which is the right answer for every list page so far.
   */
  defaultOpen?: boolean;
}) {
  const panelId = useId();
  // Initial state only. Once the reader has opened or closed the panel it is
  // theirs; applying a filter from inside it must not slam it shut, and
  // clearing the last one must not hide the fields they are still using.
  const [open, setOpen] = useState(defaultOpen ?? activeCount > 0);
  const expanded = !collapsible || open;

  const reset =
    onReset && activeCount > 0 ? (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={onReset}
      >
        <RotateCcw className="size-4" aria-hidden />
        Reset
      </Button>
    ) : null;

  return (
    <section aria-label="Filters" className={cn("grid gap-2", className)} {...props}>
      <div className="flex flex-wrap items-center gap-2">
        {leading ? <div className="min-w-56 max-w-sm flex-1">{leading}</div> : null}
        {collapsible ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={() => setOpen((current) => !current)}
          >
            <ListFilter className="size-4" aria-hidden />
            Filters
            {activeCount > 0 ? (
              <span className="text-muted-foreground tabular-nums">{activeCount}</span>
            ) : null}
            <ChevronDown
              aria-hidden
              className={cn(
                "size-4 transition-transform duration-(--motion-fast) motion-reduce:transition-none",
                expanded ? "rotate-180" : "rotate-0",
              )}
            />
          </Button>
        ) : (
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-semibold">
            <ListFilter className="size-4" aria-hidden />
            Filters
          </div>
        )}
        {reset}
      </div>
      <div
        id={panelId}
        className={cn(
          "flex flex-wrap items-end gap-2",
          collapsible && !open && "hidden",
        )}
      >
        {children}
      </div>
    </section>
  );
}

export function FilterField({
  label,
  hideLabel = false,
  children,
  className,
}: {
  label: string;
  /**
   * Drop the printed label because the control already carries it — a select
   * reading "All office" under a label reading "Office" says the word twice
   * and costs a row of the page to do it. The label is still exposed to
   * assistive technology, so pair this with an `aria-label` on the control
   * only when the control does not already name itself.
   *
   * A date or free-text field keeps its label: nothing inside it says what it
   * is, and a bare date input is a puzzle.
   */
  hideLabel?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid min-w-36 gap-1.5", className)}>
      <span
        className={cn(
          "text-muted-foreground text-xs font-semibold",
          hideLabel && "sr-only",
        )}
      >
        {label}
      </span>
      {children}
    </div>
  );
}
