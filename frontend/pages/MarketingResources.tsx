import { Head, Link, router, usePage } from "@inertiajs/react";
import { CalendarClock, ChevronRight, Info, Megaphone } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  MetricCard,
  MetricStrip,
  PageHeader,
  Pagination,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { IconWell } from "@/components/IconWell";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import type {
  FilterOption,
  MarketingLibraryFilters,
  MarketingLibraryRow,
  MarketingResourcesPageProps,
} from "@/types";

const ANY = "__any__";

function activeFilterCount(filters: MarketingLibraryFilters): number {
  return [filters.category, filters.type, filters.jurisdiction, filters.brand].filter(
    Boolean,
  ).length;
}

function rejectedFilterMessage(filters: MarketingLibraryFilters): string | null {
  if (!filters.rejected?.length) {
    return null;
  }
  return "Some filters were ignored because they are not valid for this library.";
}

function formatDay(value: string | null): string {
  if (!value) {
    return "recently";
  }
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
}) {
  return (
    <FilterField label={label} hideLabel>
      <Select
        value={value || ANY}
        onValueChange={(next) => onChange(next === ANY ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label} className="w-full sm:w-44">
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

function ResourceRow({ row }: { row: MarketingLibraryRow }) {
  const titleId = `marketing-${row.id}-title`;

  return (
    <li className="bg-card hover:border-border-strong relative flex items-start gap-3 rounded-lg border border-border/70 p-4 transition-colors duration-(--motion-fast)">
      {row.previewUrl ? (
        <img
          src={row.previewUrl}
          alt=""
          className="border-border mt-0.5 hidden size-9 shrink-0 rounded-md border object-cover sm:block"
        />
      ) : (
        <IconWell
          icon={Megaphone}
          tone="muted"
          className="mt-0.5 hidden size-9 sm:grid"
        />
      )}
      <div className="grid min-w-0 flex-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            status={{
              label: row.assetType.label,
              tone: toStatusTone(row.assetType.tone),
            }}
          />
          {row.category ? (
            <StatusBadge
              status={{
                label: row.category.label,
                tone: toStatusTone(row.category.tone),
              }}
            />
          ) : null}
        </div>
        <h2 id={titleId} className="text-sm leading-snug font-medium text-balance">
          <Link
            href={routes.marketing_resource_detail(row.id)}
            className="focus-visible:outline-ring rounded-sm focus-visible:outline-2 focus-visible:-outline-offset-2"
          >
            <span className="absolute inset-0" aria-hidden />
            {row.title}
          </Link>
        </h2>
        {row.description ? (
          <p className="text-muted-foreground line-clamp-2 text-sm leading-6">
            {row.description}
          </p>
        ) : null}
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <CalendarClock className="size-3.5 shrink-0" aria-hidden />
          <span>Published {formatDay(row.publishedAt)}</span>
          <span aria-hidden>·</span>
          <span>
            {row.versionLabel} · {row.scope.label} · {row.scope.officeName}
          </span>
          {row.exportCount > 0 ? (
            <>
              <span aria-hidden>·</span>
              <span className="tabular-nums">
                {row.exportCount} {row.exportCount === 1 ? "file" : "files"}
              </span>
            </>
          ) : null}
        </p>
      </div>
      <ChevronRight
        aria-hidden
        className="text-muted-foreground/60 mt-2 hidden size-4 shrink-0 sm:block"
      />
    </li>
  );
}

export default function MarketingResources() {
  const { library, filterOptions, summary } =
    usePage<MarketingResourcesPageProps>().props;
  const filters = library.filters as MarketingLibraryFilters;
  const notice = rejectedFilterMessage(filters);
  const [query, setQuery] = useState(filters.q ?? "");
  const [jurisdiction, setJurisdiction] = useState(filters.jurisdiction);
  const [brand, setBrand] = useState(filters.brand);

  function visit(next: Partial<MarketingLibraryFilters>, page?: number) {
    router.get(
      buildListUrl(routes.marketing_resources(), window.location.search, {
        page,
        filters: { ...filters, q: query, ...next, rejected: undefined },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = activeFilterCount(filters);

  return (
    <>
      <Head title="Marketing" />
      <div className="grid gap-8">
        <PageHeader
          title="Marketing"
          description="Approved logos, templates, and collateral for your role and office."
        />

        <MetricStrip>
          <MetricCard label="Published" value={summary.published} />
          <MetricCard label="Logos" value={summary.logos} />
          <MetricCard label="Templates" value={summary.templates} />
        </MetricStrip>

        <SurfaceCard>
          <PanelHeader divided title="Library" />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() => {
                setQuery("");
                setJurisdiction("");
                setBrand("");
                visit(
                  { category: "", type: "", jurisdiction: "", brand: "", q: "" },
                  1,
                );
              }}
              leading={
                <SearchControl
                  label="Search marketing resources"
                  value={query}
                  onValueChange={setQuery}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => {
                    setQuery("");
                    visit({ q: "" }, 1);
                  }}
                  placeholder="Title or description"
                />
              }
            >
              <FilterSelect
                label="Category"
                value={filters.category}
                options={filterOptions.categories}
                onChange={(category) => visit({ category }, 1)}
              />
              <FilterSelect
                label="Type"
                value={filters.type}
                options={filterOptions.assetTypes}
                onChange={(type) => visit({ type }, 1)}
              />
              <FilterField label="Jurisdiction" hideLabel>
                <Input
                  aria-label="Jurisdiction"
                  value={jurisdiction}
                  maxLength={2}
                  placeholder="State"
                  className="h-8 w-20 uppercase"
                  onChange={(event) =>
                    setJurisdiction(event.target.value.toUpperCase())
                  }
                  onBlur={() => {
                    if (jurisdiction !== filters.jurisdiction) {
                      visit({ jurisdiction }, 1);
                    }
                  }}
                />
              </FilterField>
              <FilterField label="Brand" hideLabel>
                <Input
                  aria-label="Brand"
                  value={brand}
                  placeholder="Brand"
                  className="h-8 w-28"
                  onChange={(event) => setBrand(event.target.value)}
                  onBlur={() => {
                    if (brand !== filters.brand) {
                      visit({ brand }, 1);
                    }
                  }}
                />
              </FilterField>
            </FilterControls>

            {notice ? (
              <p
                role="status"
                className="text-muted-foreground flex items-start gap-2 text-sm"
              >
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
                {notice}
              </p>
            ) : null}

            {library.items.length === 0 ? (
              <EmptyState
                icon={Megaphone}
                title={
                  activeCount > 0
                    ? "No marketing resources match these filters"
                    : "No marketing resources published yet"
                }
                description={
                  activeCount > 0
                    ? "Reset the filters to see everything available to you."
                    : "Assets published to your role and office will appear here."
                }
              />
            ) : (
              <ul aria-label="Marketing resource library" className="grid gap-3">
                {library.items.map((row) => (
                  <ResourceRow key={row.id} row={row} />
                ))}
              </ul>
            )}

            {library.pagination.totalPages > 1 ? (
              <Pagination
                pagination={library.pagination}
                onPageChange={(page) => visit({}, page)}
              />
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

MarketingResources.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Marketing",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Marketing" },
        ],
      },
      variant: "wide",
    },
  ] as const;
