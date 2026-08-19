import type { LucideIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  compact = false,
  className,
  ...props
}: React.ComponentProps<"section"> & {
  icon: LucideIcon;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  compact?: boolean;
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
      <span className="brand-well text-primary grid size-10 place-items-center rounded-xl">
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
