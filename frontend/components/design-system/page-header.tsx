import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The one page title per screen, plus the quiet facts and controls that belong
 * beside it.
 *
 * The title is a **fixed** 24px, not a fluid clamp. A viewport-scaled heading
 * is a landing-page device: it assumes the page is the thing being looked at.
 * An operational screen is looked *through*, at the data under it, and a title
 * that grows with the window only pushes that data further down a wide monitor
 * where there was already room. Fixed also means the heading is the same size
 * on every screen a reader moves between, so the masthead stops re-rendering
 * itself as they resize.
 */
export function PageHeader({
  title,
  description,
  breadcrumbs,
  actions,
  meta,
  rule = true,
  className,
  ...props
}: Omit<React.ComponentProps<"header">, "title"> & {
  title: React.ReactNode;
  description?: React.ReactNode;
  breadcrumbs?: React.ReactNode;
  actions?: React.ReactNode;
  /** Static facts about the page — a date, an owner, a count. Never controls. */
  meta?: React.ReactNode;
  /**
   * Close the masthead with a hairline. On by default: the rule is what makes
   * the title read as the top of the sheet rather than a caption floating
   * above it, and having it on every page is what makes the pages feel like
   * one application. Pass `rule={false}` for a header that is not the top of
   * a page — one inside a panel, or above content that draws its own top edge.
   */
  rule?: boolean;
}) {
  return (
    <header
      className={cn("grid gap-3", rule && "border-border/70 border-b pb-5", className)}
      {...props}
    >
      {breadcrumbs ? (
        <nav aria-label="Breadcrumb" className="text-muted-foreground text-sm">
          {breadcrumbs}
        </nav>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 max-w-3xl">
          <h1 className="text-2xl leading-8 font-bold tracking-[-0.02em]">{title}</h1>
          {description ? (
            <p className="text-muted-foreground mt-1.5 max-w-measure text-sm leading-6">
              {description}
            </p>
          ) : null}
          {meta ? (
            <div className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
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
