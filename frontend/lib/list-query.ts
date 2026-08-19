import { router } from "@inertiajs/react";

import type { SortState } from "@/types/design-system";

export interface ListQueryState {
  q?: string;
  page?: number;
  pageSize?: number;
  sort?: SortState | null;
  filters?: Record<string, string | string[] | undefined>;
}

function setValue(params: URLSearchParams, key: string, value: unknown) {
  params.delete(key);
  if (Array.isArray(value)) {
    for (const item of value) {
      if (item) {
        params.append(key, item);
      }
    }
    return;
  }
  if (value !== undefined && value !== null && value !== "") {
    params.set(key, String(value));
  }
}

/**
 * The single URL convention for searchable/filterable lists. Query changes
 * reset pagination unless a page is explicitly supplied.
 */
export function buildListUrl(
  pathname: string,
  currentSearch: string,
  patch: ListQueryState,
): string {
  const params = new URLSearchParams(currentSearch);
  if (patch.q !== undefined) {
    setValue(params, "q", patch.q.trim());
  }
  if (patch.pageSize !== undefined) {
    setValue(params, "pageSize", patch.pageSize);
  }
  if (patch.sort !== undefined) {
    setValue(params, "sort", patch.sort?.key);
    setValue(params, "direction", patch.sort?.direction);
  }
  for (const [key, value] of Object.entries(patch.filters ?? {})) {
    setValue(params, key, value);
  }
  const changesListShape =
    patch.q !== undefined ||
    patch.pageSize !== undefined ||
    patch.sort !== undefined ||
    patch.filters !== undefined;
  setValue(params, "page", patch.page ?? (changesListShape ? 1 : undefined));
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function visitListUrl(url: string) {
  router.get(url, {}, { preserveState: true, preserveScroll: true, replace: true });
}
