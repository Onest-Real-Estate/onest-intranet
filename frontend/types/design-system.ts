import type { LucideIcon } from "lucide-react";

/** Stable Django/Inertia validation payload. Keys remain Django field names. */
export interface ValidationErrors {
  fields: Record<string, string[]>;
  form: string[];
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
}

export interface SortState {
  key: string;
  direction: "asc" | "desc";
}

export interface ListResponse<Item, Filters extends Record<string, unknown>> {
  items: Item[];
  pagination: PaginationMeta;
  filters: Filters;
  sort: SortState | null;
}

export type StatusTone = "neutral" | "info" | "success" | "warning" | "destructive";

export interface StatusPresentation {
  label: string;
  tone: StatusTone;
  icon?: LucideIcon;
}
