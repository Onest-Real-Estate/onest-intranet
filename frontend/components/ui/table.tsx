import type * as React from "react";
import { useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A table wide enough to scroll sideways needs that scroll box to be operable
 * from the keyboard, or the columns past the edge are simply unreachable
 * without a mouse (WCAG 2.1.1). The affordance is added only while the box
 * actually overflows: a permanently focusable wrapper would put a tab stop in
 * front of every table that never scrolls at all.
 */
function useOverflowing(ref: React.RefObject<HTMLElement | null>): boolean {
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const measure = () => setOverflowing(node.scrollWidth - node.clientWidth > 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    // The row content can change width without the box changing size.
    for (const child of Array.from(node.children)) observer.observe(child);
    return () => observer.disconnect();
  }, [ref]);
  return overflowing;
}

function Table({ className, ...props }: React.ComponentProps<"table">) {
  const containerRef = useRef<HTMLElement>(null);
  const overflowing = useOverflowing(containerRef);
  const box =
    "focus-visible:ring-ring relative w-full overflow-x-auto rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2";
  const table = (
    <table
      data-slot="table"
      className={cn("w-full caption-bottom text-sm", className)}
      {...props}
    />
  );

  // Two spellings rather than one with conditional ARIA: a labelled region is
  // a different element contract from a plain box, and writing it out keeps
  // the pairing verifiable instead of something a linter has to take on faith.
  if (overflowing) {
    return (
      <section
        ref={containerRef}
        data-slot="table-container"
        className={box}
        // A scrollable region has to be focusable or its off-screen columns
        // cannot be reached without a mouse; `tabindex="0"` on the scroll box
        // is the technique WCAG names for SC 2.1.1. The rule cannot tell this
        // from a decorative div, and it is applied only while the box scrolls.
        // biome-ignore lint/a11y/noNoninteractiveTabindex: WCAG 2.1.1 scrollable region
        tabIndex={0}
        aria-label="Table, scrolls horizontally"
      >
        {table}
      </section>
    );
  }

  // Same element in both branches: swapping the tag would remount the node,
  // detaching the observer that decides which branch to render.
  return (
    <section ref={containerRef} data-slot="table-container" className={box}>
      {table}
    </section>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("bg-muted/40 [&_tr]:border-b", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "hover:bg-muted/40 data-[state=selected]:bg-muted border-b transition-colors",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "text-muted-foreground border-border/60 h-11 px-4 text-left align-middle text-xs font-semibold whitespace-nowrap",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "border-border/50 px-4 py-3 align-middle whitespace-nowrap",
        className,
      )}
      {...props}
    />
  );
}

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow };
