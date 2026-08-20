import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Database,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import type * as React from "react";

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

export interface DataTableColumn<Row> {
  id: string;
  header: React.ReactNode;
  cell: (row: Row) => React.ReactNode;
  sortable?: boolean;
  numeric?: boolean;
  className?: string;
  headerClassName?: string;
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

  return (
    <div
      className={cn(
        "overflow-hidden",
        frame === "bordered" && "rounded-xl border",
        frame === "bleed" &&
          "border-border/60 -mx-5 border-y [&_tr>*:first-child]:pl-5 [&_tr>*:last-child]:pr-5",
        className,
      )}
    >
      <Table>
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
                  className={cn(column.numeric && "text-right", column.headerClassName)}
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
                      {column.header}
                      <SortIcon className="size-3.5" aria-hidden />
                    </button>
                  ) : (
                    column.header
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={columnCount} className="h-40 text-center">
                <span
                  role="status"
                  className="text-muted-foreground inline-flex items-center gap-2"
                >
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                  Loading results
                </span>
              </TableCell>
            </TableRow>
          ) : error ? (
            <TableRow>
              <TableCell colSpan={columnCount} className="h-40 text-center">
                <span
                  role="alert"
                  className="text-destructive inline-flex items-center gap-2"
                >
                  <TriangleAlert className="size-4" aria-hidden />
                  {error}
                </span>
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
                      className={cn(column.numeric && "text-right", column.className)}
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
    </div>
  );
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
  return (
    <nav
      aria-label="Pagination"
      className={cn(
        "flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <p className="text-muted-foreground text-sm">
        Page <strong className="text-foreground">{pagination.page}</strong> of{" "}
        <strong className="text-foreground">{pagination.totalPages}</strong>
        <span className="hidden sm:inline"> · {pagination.totalItems} total</span>
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || !pagination.hasPrevious}
          onClick={() => onPageChange(pagination.page - 1)}
        >
          <ChevronLeft className="size-4" aria-hidden />
          Previous
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || !pagination.hasNext}
          onClick={() => onPageChange(pagination.page + 1)}
        >
          Next
          <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
