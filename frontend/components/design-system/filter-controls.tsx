import { ChevronDown, ListFilter, RotateCcw } from "lucide-react";
import type * as React from "react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The filter toolbar for a list view: one pill that names the region and
 * carries the count of what is currently narrowing the list, the fields
 * themselves, and a reset that only exists while there is something to reset.
 *
 * The panel starts open. On an operational list the filters *are* the control
 * surface, and a reader who cannot see the constraint blames the data instead
 * of the filter — so collapsing is something they choose, not the default.
 */
export function FilterControls({
  children,
  activeCount = 0,
  onReset,
  disabled = false,
  collapsible = true,
  defaultOpen = true,
  className,
  ...props
}: React.ComponentProps<"section"> & {
  activeCount?: number;
  onReset?: () => void;
  disabled?: boolean;
  /** False where the fields are the page's primary control, as on a report. */
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(defaultOpen);
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
    <section aria-label="Filters" className={cn("grid gap-3", className)} {...props}>
      <div className="flex flex-wrap items-center gap-2">
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
              <span className="bg-primary text-primary-foreground grid min-w-5 place-items-center rounded-full px-1.5 text-xs tabular-nums">
                {activeCount}
              </span>
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
          "flex flex-wrap items-end gap-3",
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
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid min-w-36 gap-1.5", className)}>
      <span className="text-muted-foreground text-xs font-semibold">{label}</span>
      {children}
    </div>
  );
}
