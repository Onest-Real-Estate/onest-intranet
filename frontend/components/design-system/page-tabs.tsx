import { Link } from "@inertiajs/react";
import type * as React from "react";

import { cn } from "@/lib/utils";

export interface PageTab {
  key: string;
  label: string;
  href: string;
}

/**
 * Sibling destinations of one page, as tabs across its top.
 *
 * Each tab is a real link to its own URL, so a tab can be bookmarked, opened
 * in a new window, and authorized on its own — the page behind it is a full
 * Inertia visit, not a panel hidden in the DOM. The current tab takes the
 * gold-tinted surface, the same signal the sidebar gives the page you are on.
 */
export function PageTabs({
  label,
  tabs,
  current,
  actions,
  className,
}: {
  /** Names the tab row for assistive technology, e.g. "People sections". */
  label: string;
  tabs: PageTab[];
  current: string;
  /** Controls that act on the whole section, set at the row's right edge. */
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 border-b pb-3 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <nav aria-label={label} className="-mx-1 overflow-x-auto px-1">
        <ul className="flex gap-1">
          {tabs.map((tab) => {
            const active = tab.key === current;
            return (
              <li key={tab.key}>
                <Link
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "focus-visible:ring-ring/50 inline-flex h-9 items-center rounded-md px-4 text-sm font-medium whitespace-nowrap outline-none transition-colors duration-(--motion-fast) focus-visible:ring-[3px]",
                    active
                      ? "bg-chip-primary text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
