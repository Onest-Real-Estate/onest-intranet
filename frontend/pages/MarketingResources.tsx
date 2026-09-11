import { Head, Link, router, usePage } from "@inertiajs/react";
import { CalendarClock, ChevronRight, Info, Megaphone } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
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
  return [
    filters.category,
    filters.type,
    filters.jurisdiction,
    filters.brand,
    filters.q,
  ].filter(Boolean).length;
}

function rejectedFilterMessage(filters: MarketingLibraryFilters): string | null {
  if (!filters.rejected?.length) {
    return null;
  }
  return "Some filters were ignored because they are not valid for this library.";
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
        <SelectTrigger size="sm" aria-label={label}>
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

function ResourceCard({ row }: { row: MarketingLibraryRow }) {
  const titleId = `marketing-${row.id}-title`;
  const assetTone = toStatusTone(row.assetType.tone);

  return (
    <article aria-labelledby={titleId}>
      <SurfaceCard interactive className="group relative">
        <SurfaceCardContent className="flex min-w-0 items-start gap-4">
          {row.previewUrl ? (
            <img
              src={row.previewUrl}
              alt=""
              className="border-border size-16 shrink-0 rounded-md border object-cover"
            />
          ) : (
            <div className="bg-muted text-muted-foreground flex size-16 shrink-0 items-center justify-center rounded-md">
              <Megaphone className="size-5" aria-hidden />
            </div>
          )}
          <div className="grid min-w-0 flex-1 gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={{ label: row.assetType.label, tone: assetTone }} />
              {row.category ? (
                <StatusBadge
                  status={{
                    label: row.category.label,
                    tone: toStatusTone(row.category.tone),
                  }}
                />
              ) : null}
              <span className="text-muted-foreground text-xs">
                {row.versionLabel} · {row.scope.label} · {row.scope.officeName}
              </span>
              {row.exportCount > 0 ? (
                <span className="text-muted-foreground text-xs tabular-nums">
                  {row.exportCount} {row.exportCount === 1 ? "file" : "files"}
                </span>
              ) : null}
            </div>
            <h2
              id={titleId}
              className="text-base leading-snug font-semibold text-balance"
            >
              <Link
                href={routes.marketing_resource_detail(row.id)}
                className="group-hover:text-primary focus-visible:ring-ring rounded-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none"
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
            <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <CalendarClock className="size-3.5 shrink-0" aria-hidden />
              Published{" "}
              {row.publishedAt
                ? new Date(row.publishedAt).toLocaleDateString()
                : "recently"}
            </div>
          </div>
          <ChevronRight
            aria-hidden
            className="text-muted-foreground/60 group-hover:text-foreground mt-2 hidden size-4 shrink-0 transition-colors duration-(--motion-fast) sm:block"
          />
        </SurfaceCardContent>
      </SurfaceCard>
    </article>
  );
}

export default function MarketingResources() {
  const { library, filterOptions } = usePage<MarketingResourcesPageProps>().props;
  const filters = library.filters as MarketingLibraryFilters;
  const notice = rejectedFilterMessage(filters);
  const [jurisdiction, setJurisdiction] = useState(filters.jurisdiction);
  const [brand, setBrand] = useState(filters.brand);

  function visit(next: Partial<MarketingLibraryFilters>, page?: number) {
    router.get(
      buildListUrl(routes.marketing_resources(), window.location.search, {
        page,
        filters: { ...filters, ...next, rejected: undefined },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Marketing resources" />
      <div className="grid gap-8">
        <PageHeader
          title="Marketing resources"
          description="Approved logos, templates, flyers, and collateral for your role and office."
        />

        <FilterControls
          activeCount={activeFilterCount(filters)}
          onReset={() => {
            setJurisdiction("");
            setBrand("");
            visit({
              category: "",
              type: "",
              jurisdiction: "",
              brand: "",
              q: "",
            });
          }}
        >
          <SearchControl
            value={filters.q}
            onSearch={(next) => visit({ q: next })}
            label="Search marketing resources"
            placeholder="Search title or description"
          />
          <FilterSelect
            label="Category"
            value={filters.category}
            options={filterOptions.categories}
            onChange={(next) => visit({ category: next })}
          />
          <FilterSelect
            label="Type"
            value={filters.type}
            options={filterOptions.assetTypes}
            onChange={(next) => visit({ type: next })}
          />
          <FilterField label="Jurisdiction" hideLabel>
            <Input
              aria-label="Jurisdiction state code"
              value={jurisdiction}
              maxLength={2}
              placeholder="State"
              className="h-8 w-20 uppercase"
              onChange={(event) => setJurisdiction(event.target.value.toUpperCase())}
              onBlur={() => {
                if (jurisdiction !== filters.jurisdiction) {
                  visit({ jurisdiction });
                }
              }}
            />
          </FilterField>
          <FilterField label="Brand" hideLabel>
            <Input
              aria-label="Brand code"
              value={brand}
              placeholder="Brand"
              className="h-8 w-28"
              onChange={(event) => setBrand(event.target.value)}
              onBlur={() => {
                if (brand !== filters.brand) {
                  visit({ brand });
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
          <SurfaceCard>
            <EmptyState
              icon={Megaphone}
              title={
                activeFilterCount(filters) > 0
                  ? "No marketing resources match these filters"
                  : "No marketing resources published yet"
              }
              description={
                activeFilterCount(filters) > 0
                  ? "Reset the filters to see everything available to you."
                  : "Assets published to your role and office will appear here."
              }
            />
          </SurfaceCard>
        ) : (
          <section aria-label="Marketing resource library" className="grid gap-3">
            {library.items.map((row) => (
              <ResourceCard key={row.id} row={row} />
            ))}
          </section>
        )}

        {library.pagination.totalPages > 1 ? (
          <Pagination
            pagination={library.pagination}
            onPageChange={(page) => visit({}, page)}
          />
        ) : null}
      </div>
    </>
  );
}

MarketingResources.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Marketing resources",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Marketing resources" },
        ],
      },
    },
  ] as const;
