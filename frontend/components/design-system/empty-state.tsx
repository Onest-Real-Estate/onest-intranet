import type { LucideIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * `brand` is the gold well: a place where the reader is invited to put the
 * first thing. `muted` is for an absence they cannot act on — a module that is
 * not connected, a panel their access does not cover — where a brand moment
 * would celebrate a dead end.
 */
const toneClasses = {
  brand: "brand-well text-primary",
  muted: "bg-muted text-muted-foreground",
} as const;

export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  compact = false,
  tone = "brand",
  className,
  ...props
}: React.ComponentProps<"section"> & {
  icon: LucideIcon;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  compact?: boolean;
  tone?: keyof typeof toneClasses;
}) {
  return (
    <section
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 py-8" : "gap-3 px-5 py-14",
        className,
      )}
      {...props}
    >
      <span
        className={cn("grid size-10 place-items-center rounded-xl", toneClasses[tone])}
      >
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="max-w-md">
        <h3 className="font-semibold">{title}</h3>
        {description ? (
          <p className="text-muted-foreground mt-1 text-sm leading-5">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="mt-1 flex flex-wrap gap-2">{actions}</div> : null}
    </section>
  );
}
