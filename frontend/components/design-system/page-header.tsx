import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The one page title per screen, plus the quiet facts and controls that belong
 * beside it. The title tops out at 30px: large enough to anchor the page,
 * small enough that a dense operational screen still reads as a workspace
 * rather than a landing page.
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  breadcrumbs,
  actions,
  meta,
  className,
  ...props
}: React.ComponentProps<"header"> & {
  title: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  breadcrumbs?: React.ReactNode;
  actions?: React.ReactNode;
  /** Static facts about the page — a date, an owner, a count. Never controls. */
  meta?: React.ReactNode;
}) {
  return (
    <header className={cn("grid gap-4", className)} {...props}>
      {breadcrumbs ? (
        <nav aria-label="Breadcrumb" className="text-muted-foreground text-sm">
          {breadcrumbs}
        </nav>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 max-w-3xl">
          {eyebrow ? (
            <p className="text-muted-foreground mb-1.5 text-xs font-semibold tracking-[0.08em] uppercase">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="text-[clamp(1.5rem,2.4vw,1.875rem)] leading-tight font-semibold tracking-[-0.02em]">
            {title}
          </h1>
          {description ? (
            <p className="text-muted-foreground mt-1.5 max-w-2xl text-sm leading-6">
              {description}
            </p>
          ) : null}
          {meta ? (
            <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              {meta}
            </div>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </header>
  );
}
