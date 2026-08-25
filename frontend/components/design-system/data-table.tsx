import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Database,
  LoaderCircle,
  type LucideIcon,
  TriangleAlert,
} from "lucide-react";
import type * as React from "react";
import { useLayoutEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/design-system/empty-state";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { PaginationMeta, SortState } from "@/types/design-system";

/**
 * The column id a table uses for its row actions. In the card layout it is
 * lifted out of the value list and given the card's footer, because a row's
 * control is not one of its facts.
 */
export const ACTION_COLUMN_ID = "actions";

export interface DataTableColumn<Row> {
  /** `ACTION_COLUMN_ID` marks the row-action column; see the card layout. */
  id: string;
  header: React.ReactNode;
  /**
   * Optional mark shown before the column name. It labels the *kind* of value
   * in the column, so a reader scanning a wide table finds the one they want
   * before reading any header text. Purely decorative — the header word is
   * still the accessible name.
   */
  icon?: LucideIcon;
  cell: (row: Row) => React.ReactNode;
  sortable?: boolean;
  numeric?: boolean;
  className?: string;
  headerClassName?: string;
  /**
   * Drop this column while the table's own box is narrower than the named
   * width. Pages declare *when a column stops fitting*, never a viewport
   * breakpoint: a table in a 736px panel cannot see that the window is 1280px
   * wide, and a `md:` rule would keep a column the panel has no room for.
   *
   * Pick the step from the width the columns actually need, not from a device.
   * Nothing is lost below it — the card layout shows every column.
   */
  hideBelow?: HideBelow;
}

/**
 * Container-width steps a column may be dropped below. The class strings are
 * spelled out because Tailwind only emits what it can see in the source.
 */
const HIDE_BELOW_CLASS = {
  "2xl": "hidden @2xl:table-cell",
  "3xl": "hidden @3xl:table-cell",
  "4xl": "hidden @4xl:table-cell",
  "5xl": "hidden @5xl:table-cell",
  "6xl": "hidden @6xl:table-cell",
  "7xl": "hidden @7xl:table-cell",
} as const;

export type HideBelow = keyof typeof HIDE_BELOW_CLASS;

/**
 * Below this container width the table becomes a list of cards. A phone-width
 * grid of eight columns is not a dense table, it is an unreadable one, and
 * hiding columns until it fits would hide most of the record.
 */
const CARD_LAYOUT_BELOW = 576;

/**
 * The table's own width, watched rather than assumed.
 *
 * Two things depend on it and neither can be answered by a media query: which
 * layout the rows take, and whether the scroll box needs to be reachable from
 * the keyboard.
 */
function useBoxWidth(): [React.RefObject<HTMLDivElement | null>, number | null] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const measure = () => setWidth(node.getBoundingClientRect().width);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  caption,
  sort,
  onSortChange,
  selectedKeys,
  onSelectionChange,
  getRowLabel,
  loading = false,
  error,
  emptyTitle = "Nothing here yet",
  emptyDescription = "Items will appear here when they become available.",
  frame = "bordered",
  className,
}: {
  rows: Row[];
  columns: DataTableColumn<Row>[];
  rowKey: (row: Row) => string;
  caption: string;
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  selectedKeys?: Set<string>;
  onSelectionChange?: (keys: Set<string>) => void;
  getRowLabel?: (row: Row) => string;
  loading?: boolean;
  error?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  /**
   * `bordered` is the standalone table. `bare` drops the frame for a table
   * that already sits inside a card, so the two borders do not double up.
   * `bleed` is `bare` plus the geometry for a table filling the width of a
   * `SurfaceCardContent`: it cancels the card's 20px inset so the row
   * separators reach both edges, then hands that inset back to the outer
   * columns — the first column keeps its left edge on the panel heading
   * instead of sitting 8px inside it.
   */
  frame?: "bordered" | "bare" | "bleed";
  className?: string;
}) {
  const [boxRef, boxWidth] = useBoxWidth();
  // Cards require a positive measurement below the threshold. Zero means "not
  // laid out yet" — a headless renderer, a detached tree, a hidden tab — never
  // "extremely narrow", and the table is the honest default for an unknown
  // width because it is what every wider reader gets.
  const asCards = boxWidth !== null && boxWidth > 0 && boxWidth < CARD_LAYOUT_BELOW;
  const selectable = Boolean(selectedKeys && onSelectionChange);
  const allSelected =
    selectable &&
    rows.length > 0 &&
    rows.every((row) => selectedKeys?.has(rowKey(row)));
  const someSelected =
    selectable && rows.some((row) => selectedKeys?.has(rowKey(row))) && !allSelected;
  const columnCount = columns.length + (selectable ? 1 : 0);

  function toggleAll() {
    if (!selectedKeys || !onSelectionChange) return;
    const next = new Set(selectedKeys);
    if (allSelected) {
      for (const row of rows) next.delete(rowKey(row));
    } else {
      for (const row of rows) next.add(rowKey(row));
    }
    onSelectionChange(next);
  }

  // Loading, error, and empty read the same in either layout, so they are
  // written once and placed by whichever branch is rendering.
  const status = loading ? (
    <span
      role="status"
      className="text-muted-foreground inline-flex items-center gap-2"
    >
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      Loading results
    </span>
  ) : error ? (
    <span role="alert" className="text-destructive inline-flex items-center gap-2">
      <TriangleAlert className="size-4" aria-hidden />
      {error}
    </span>
  ) : null;

  const cards = (
    <>
      {status ? (
        <div className="grid h-40 place-items-center text-center">{status}</div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Database}
          title={emptyTitle}
          description={emptyDescription}
          compact
        />
      ) : (
        <ul className="grid gap-3" aria-label={caption}>
          {rows.map((row) => {
            const key = rowKey(row);
            const selected = selectedKeys?.has(key) ?? false;
            const [identity, ...rest] = columns;
            // The first column identifies the record and titles the card; the
            // action column becomes its footer; everything else is a fact.
            const detail = rest.filter((c) => c.id !== ACTION_COLUMN_ID);
            const actions = rest.find((c) => c.id === ACTION_COLUMN_ID);
            return (
              <li
                key={key}
                data-state={selected ? "selected" : undefined}
                className="bg-card data-[state=selected]:border-ring/50 grid gap-3 rounded-xl border p-4"
              >
                <div className="flex items-start gap-3">
                  {selectable ? (
                    <Checkbox
                      className="mt-1"
                      checked={selected}
                      aria-label={`Select ${getRowLabel?.(row) ?? "row"}`}
                      onCheckedChange={() => {
                        if (!selectedKeys || !onSelectionChange) return;
                        const next = new Set(selectedKeys);
                        selected ? next.delete(key) : next.add(key);
                        onSelectionChange(next);
                      }}
                    />
                  ) : null}
                  {/* The identity is what the card is about, so it carries
                      heading semantics — a reader navigating by heading can
                      move between records. `role` rather than an `<h3>` because
                      the cell renders arbitrary flow content that a heading
                      element may not contain. */}
                  <div role="heading" aria-level={3} className="min-w-0 flex-1">
                    {identity?.cell(row)}
                  </div>
                </div>
                {/* Every column the table would have dropped is present here:
                      a card has vertical room, so narrow never means less. */}
                <dl className="grid gap-2 border-t pt-3 text-sm">
                  {detail.map((column) => (
                    <div
                      key={column.id}
                      className="grid grid-cols-[minmax(0,8rem)_1fr] items-baseline gap-3"
                    >
                      <dt className="text-muted-foreground text-xs font-semibold">
                        {column.header}
                      </dt>
                      <dd className="min-w-0">{column.cell(row)}</dd>
                    </div>
                  ))}
                </dl>
                {actions ? (
                  <div className="flex justify-end border-t pt-3">
                    {actions.cell(row)}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );

  const table = (
    <>
      {/* Vertical rules between cells turn a list of values back into a grid:
          across a wide table the column edge is what keeps the eye on one
          record. They live on the table, not the frame wrapper, so `bare` and
          `bleed` still contribute no outer border of their own. */}
      <Table className="[&_tr>*+*]:border-l">
        <caption className="sr-only">{caption}</caption>
        {/* Micro-caps headers: the column names read as labels rather than as
            another row of data competing with the values below them. */}
        <TableHeader className="[&_th]:tracking-[0.06em] [&_th]:uppercase">
          <TableRow>
            {selectable ? (
              <TableHead className="w-11">
                <Checkbox
                  checked={someSelected ? "indeterminate" : allSelected}
                  onCheckedChange={toggleAll}
                  aria-label={
                    allSelected
                      ? "Deselect all visible rows"
                      : "Select all visible rows"
                  }
                />
              </TableHead>
            ) : null}
            {columns.map((column) => {
              const active = sort?.key === column.id;
              const SortIcon = !active
                ? ArrowUpDown
                : sort.direction === "asc"
                  ? ArrowUp
                  : ArrowDown;
              return (
                <TableHead
                  key={column.id}
                  scope="col"
                  aria-sort={
                    active
                      ? sort.direction === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                  className={cn(
                    column.numeric && "text-right",
                    column.hideBelow && HIDE_BELOW_CLASS[column.hideBelow],
                    column.headerClassName,
                  )}
                >
                  {column.sortable && onSortChange ? (
                    <button
                      type="button"
                      className={cn(
                        // `uppercase` is repeated here on purpose: the CSS reset
                        // sets `text-transform: none` on buttons, so a sortable
                        // header would otherwise opt out of the micro-caps.
                        "hover:text-foreground focus-visible:ring-ring inline-flex min-h-9 items-center gap-1.5 rounded-md tracking-[0.06em] uppercase outline-none focus-visible:ring-2",
                        column.numeric && "ml-auto",
                      )}
                      onClick={() =>
                        onSortChange({
                          key: column.id,
                          direction:
                            active && sort.direction === "asc" ? "desc" : "asc",
                        })
                      }
                    >
                      {column.icon ? (
                        <column.icon className="size-3.5 opacity-70" aria-hidden />
                      ) : null}
                      {column.header}
                      <SortIcon className="size-3.5" aria-hidden />
                    </button>
                  ) : column.icon ? (
                    <span className="inline-flex items-center gap-1.5">
                      <column.icon className="size-3.5 opacity-70" aria-hidden />
                      {column.header}
                    </span>
                  ) : (
                    column.header
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {status ? (
            <TableRow>
              <TableCell colSpan={columnCount} className="h-40 text-center">
                {status}
              </TableCell>
            </TableRow>
          ) : rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columnCount}>
                <EmptyState
                  icon={Database}
                  title={emptyTitle}
                  description={emptyDescription}
                  compact
                />
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => {
              const key = rowKey(row);
              const selected = selectedKeys?.has(key) ?? false;
              return (
                <TableRow key={key} data-state={selected ? "selected" : undefined}>
                  {selectable ? (
                    <TableCell>
                      <Checkbox
                        checked={selected}
                        aria-label={`Select ${getRowLabel?.(row) ?? "row"}`}
                        onCheckedChange={() => {
                          if (!selectedKeys || !onSelectionChange) return;
                          const next = new Set(selectedKeys);
                          selected ? next.delete(key) : next.add(key);
                          onSelectionChange(next);
                        }}
                      />
                    </TableCell>
                  ) : null}
                  {columns.map((column) => (
                    <TableCell
                      key={column.id}
                      className={cn(
                        column.numeric && "text-right",
                        column.hideBelow && HIDE_BELOW_CLASS[column.hideBelow],
                        column.className,
                      )}
                    >
                      {column.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </>
  );

  // One wrapper for both layouts. It is the element the ResizeObserver watches,
  // so it must survive the switch: hang the observer off a node that unmounts
  // when the layout changes and it measures exactly once, then never again.
  return (
    <div
      ref={boxRef}
      className={cn(
        // The table's own box is the container its columns answer to.
        "@container",
        !asCards && "overflow-hidden",
        frame === "bordered" &&
          (asCards ? "rounded-xl border p-3" : "rounded-xl border"),
        frame === "bleed" &&
          (asCards
            ? "-mx-5 px-5"
            : "border-border/60 -mx-5 border-y [&_tr>*:first-child]:pl-5 [&_tr>*:last-child]:pr-5"),
        className,
      )}
    >
      {asCards ? cards : table}
    </div>
  );
}

/**
 * The page numbers worth rendering: always the first and last page, always a
 * window around the current one, and a gap marker for everything skipped. A
 * pager that lists every page of a 90-page result is not a control, it is a
 * wall — but one that only says "next" hides where the reader is.
 */
export interface PaginationItem {
  /** Stable across renders: the page it stands for, or the gap it fills. */
  key: string;
  /** Null marks an elided run of pages rather than a page to visit. */
  page: number | null;
}

export function paginationItems(page: number, totalPages: number): PaginationItem[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => ({
      key: String(index + 1),
      page: index + 1,
    }));
  }
  const window = new Set([1, totalPages, page, page - 1, page + 1]);
  if (page <= 3) {
    window.add(2).add(3).add(4);
  }
  if (page >= totalPages - 2) {
    window
      .add(totalPages - 1)
      .add(totalPages - 2)
      .add(totalPages - 3);
  }
  const pages = [...window]
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((a, b) => a - b);

  const items: PaginationItem[] = [];
  let previous = 0;
  for (const value of pages) {
    if (previous && value - previous > 1) {
      items.push({ key: `gap-${previous}`, page: null });
    }
    items.push({ key: String(value), page: value });
    previous = value;
  }
  return items;
}

export function Pagination({
  pagination,
  onPageChange,
  disabled = false,
  className,
}: {
  pagination: PaginationMeta;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
}) {
  const items = paginationItems(pagination.page, pagination.totalPages);

  return (
    <nav
      aria-label="Pagination"
      className={cn(
        "flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <p className="text-muted-foreground text-sm tabular-nums">
        <strong className="text-foreground font-semibold">
          {pagination.totalItems}
        </strong>{" "}
        {pagination.totalItems === 1 ? "result" : "results"}
        <span className="hidden sm:inline">
          {" "}
          · page {pagination.page} of {pagination.totalPages}
        </span>
      </p>
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled || !pagination.hasPrevious}
          onClick={() => onPageChange(pagination.page - 1)}
        >
          <ChevronLeft className="size-4" aria-hidden />
          <span className="hidden sm:inline">Previous</span>
        </Button>
        {items.map(({ key, page }) =>
          page === null ? (
            <span key={key} aria-hidden className="text-muted-foreground px-1 text-sm">
              …
            </span>
          ) : (
            <Button
              key={key}
              type="button"
              variant={page === pagination.page ? "secondary" : "ghost"}
              size="sm"
              disabled={disabled}
              aria-current={page === pagination.page ? "page" : undefined}
              aria-label={`Page ${page}`}
              className={cn(
                // 36px suits a mouse; a finger needs the full target, and the
                // pointer type says which one is in use better than width does.
                "size-9 px-0 tabular-nums pointer-coarse:size-11",
                page === pagination.page && "text-foreground font-semibold",
              )}
              onClick={() => onPageChange(page)}
            >
              {page}
            </Button>
          ),
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled || !pagination.hasNext}
          onClick={() => onPageChange(pagination.page + 1)}
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
