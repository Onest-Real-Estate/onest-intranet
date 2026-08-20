import { ListFilter, RotateCcw } from "lucide-react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function FilterControls({
  children,
  activeCount = 0,
  onReset,
  disabled = false,
  className,
  ...props
}: React.ComponentProps<"section"> & {
  activeCount?: number;
  onReset?: () => void;
  disabled?: boolean;
}) {
  return (
    <section
      aria-label="Filters"
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end",
        className,
      )}
      {...props}
    >
      <div className="text-muted-foreground flex h-10 shrink-0 items-center gap-2 text-sm font-medium">
        <ListFilter className="size-4" aria-hidden />
        Filters
        {activeCount > 0 ? (
          <span className="bg-primary text-primary-foreground grid min-w-5 place-items-center rounded-full px-1.5 py-0.5 text-xs tabular-nums">
            {activeCount}
          </span>
        ) : null}
      </div>
      <div className="flex min-w-0 flex-1 flex-wrap items-end gap-2">{children}</div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={disabled || activeCount === 0}
        onClick={onReset}
      >
        <RotateCcw className="size-4" aria-hidden />
        Reset
      </Button>
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
