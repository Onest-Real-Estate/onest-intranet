/**
 * How a resolved widget list becomes rows on a twelve-column grid.
 *
 * The dashboard used to be two independent stacks — a wide reading column and
 * a narrow rail — and each stack ended wherever its own contents ran out. On a
 * populated dashboard the two happened to finish near each other; on a sparse
 * one the shorter stack stopped hundreds of pixels early and the page ended in
 * a column of blank canvas beside a column of panels.
 *
 * So placement is computed instead of assumed. Widgets keep their reviewed
 * reading order and their natural width, they are packed into rows of exactly
 * twelve, and a row that cannot be filled by the widgets that belong in it
 * widens those widgets until it is. Every row closes flush, so the page closes
 * flush, whatever mix of widgets a role happens to resolve to.
 *
 * Nothing here reads a height, a clock, or the DOM: the same widget list always
 * produces the same rows, on the server-rendered first paint and after every
 * partial reload.
 */

import type { PendingModule } from "@/components/dashboard/PendingModules";
import type { ResolvedDashboardWidget } from "@/lib/dashboard/resolve";
import type { DashboardWidgetDefinition } from "@/lib/dashboard/widget-registry";
import type { DashboardPageProps } from "@/types";

/** The grid every dashboard row is measured in. */
export const DASHBOARD_COLUMNS = 12;

/**
 * Twelfths a widget asks for before packing.
 *
 * `span` on the definition is an explicit request and wins. Otherwise width
 * follows the widget's column role: a `main` widget is a reading-width panel,
 * a `rail` widget is a narrow one, and a `wide` widget owns its own band.
 */
export function naturalSpan(definition: DashboardWidgetDefinition): number {
  if (definition.span) {
    return Math.min(Math.max(definition.span, 1), DASHBOARD_COLUMNS);
  }
  switch (definition.column) {
    case "rail":
      return 4;
    case "main":
      return 8;
    default:
      return DASHBOARD_COLUMNS;
  }
}

export interface PackedItem<T> {
  item: T;
  /** Final twelfths, after short rows have been widened to close. */
  span: number;
  /** Zero-based row this item lands in. Exposed for tests and debugging. */
  row: number;
}

/**
 * Pack items into rows of twelve, then widen short rows until they close.
 *
 * Placement is first-fit: an item goes into the earliest row with room for it,
 * which is what `grid-auto-flow: dense` does with the same spans. Computing it
 * here rather than leaving it to CSS is what makes the widening possible — the
 * browser can close a gap by moving a later widget into it, but it cannot
 * decide that the last row should simply be wider.
 *
 * The leftover twelfths of a short row are shared out over that row's own
 * items, earliest first, so one trailing widget becomes a full-width band and
 * two become an even pair rather than a pair with a hole beside it.
 */
export function packRows<T>(items: readonly T[], spanOf: (item: T) => number) {
  const spans = items.map((item) =>
    Math.min(Math.max(spanOf(item), 1), DASHBOARD_COLUMNS),
  );
  const rows: number[][] = [];
  const remaining: number[] = [];
  const rowOf: number[] = [];

  spans.forEach((span, index) => {
    let row = remaining.findIndex((left) => left >= span);
    if (row === -1) {
      rows.push([]);
      remaining.push(DASHBOARD_COLUMNS);
      row = rows.length - 1;
    }
    rows[row].push(index);
    remaining[row] -= span;
    rowOf[index] = row;
  });

  rows.forEach((row, index) => {
    const deficit = remaining[index];
    if (deficit <= 0) {
      return;
    }
    const share = Math.floor(deficit / row.length);
    const odd = deficit % row.length;
    row.forEach((member, position) => {
      spans[member] += share + (position < odd ? 1 : 0);
    });
  });

  return items.map<PackedItem<T>>((item, index) => ({
    item,
    span: spans[index],
    row: rowOf[index],
  }));
}

/**
 * Column spans as literal classes.
 *
 * Tailwind scans source text, so a computed `xl:col-span-${n}` would emit no
 * CSS at all. Below `xl` every panel is full width: a twelfth of a tablet is
 * not a panel, it is a stripe.
 */
const SPAN_CLASS: Readonly<Record<number, string>> = {
  1: "xl:col-span-1",
  2: "xl:col-span-2",
  3: "xl:col-span-3",
  4: "xl:col-span-4",
  5: "xl:col-span-5",
  6: "xl:col-span-6",
  7: "xl:col-span-7",
  8: "xl:col-span-8",
  9: "xl:col-span-9",
  10: "xl:col-span-10",
  11: "xl:col-span-11",
  12: "xl:col-span-12",
};

export function spanClass(span: number): string {
  return SPAN_CLASS[span] ?? SPAN_CLASS[DASHBOARD_COLUMNS];
}

/**
 * Split resolved widgets into the ones that get a panel and the ones that get
 * a line in the closing band.
 *
 * A widget is demoted only when the page can *prove* there is nothing behind
 * it: the registry says no provider has shipped, or the provider answered
 * `unavailable` and said the condition is not retryable. Everything else keeps
 * its panel — including a deferred prop that has not landed yet, which still
 * renders its own skeleton, and a provider that failed this request, which
 * still renders its own retry.
 */
export function partitionPending(
  widgets: readonly ResolvedDashboardWidget[],
  page: DashboardPageProps,
): {
  laidOut: ResolvedDashboardWidget[];
  pending: PendingModule[];
} {
  const laidOut: ResolvedDashboardWidget[] = [];
  const pending: PendingModule[] = [];

  for (const widget of widgets) {
    const module = pendingModule(widget, page);
    if (module) {
      pending.push(module);
    } else {
      laidOut.push(widget);
    }
  }
  return { laidOut, pending };
}

function pendingModule(
  resolved: ResolvedDashboardWidget,
  page: DashboardPageProps,
): PendingModule | null {
  const { definition, withheld } = resolved;
  // A withheld panel is the one absence that has to stay prominent: a
  // compliance dashboard whose compliance panel became a footnote reads as a
  // dashboard with nothing to review.
  if (withheld) {
    return null;
  }

  const envelope = page[definition.prop];
  // Real data always wins over the registry flag, exactly as the widget slot
  // decides it — a provider that shipped without `backed` being flipped must
  // never end up summarised as "not connected".
  if (envelope && envelope.status !== "unavailable") {
    return null;
  }
  if (definition.backed) {
    if (!envelope || envelope.unavailable.retryable) {
      return null;
    }
    return {
      prop: definition.prop,
      title: definition.title,
      reason: envelope.unavailable.reason,
      actionLabel: envelope.unavailable.actionLabel,
      actionHref: envelope.unavailable.actionHref,
    };
  }
  // No provider, so no server-authored reason either. The band's own heading
  // already says why every entry is there; repeating one generic sentence under
  // seven module names turns a short list into a wall of the same sentence.
  return {
    prop: definition.prop,
    title: definition.title,
    reason: envelope?.unavailable.reason,
    actionLabel: envelope?.unavailable.actionLabel,
    actionHref: envelope?.unavailable.actionHref,
  };
}
