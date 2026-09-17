import { Head, Link, router, usePage } from "@inertiajs/react";
import { CalendarClock, ChevronRight, Info, ShieldCheck } from "lucide-react";
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
import { IconWell, type IconWellTone } from "@/components/IconWell";
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
import { cn } from "@/lib/utils";
import type {
  ComplianceLibraryFilters,
  ComplianceLibraryRow,
  FilterOption,
  PoliciesCompliancePageProps,
} from "@/types";

const ANY = "__any__";

function activeFilterCount(filters: ComplianceLibraryFilters): number {
  return [filters.category, filters.jurisdiction].filter(Boolean).length;
}

function rejectedFilterMessage(filters: ComplianceLibraryFilters): string | null {
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

function rowTone(row: ComplianceLibraryRow): IconWellTone {
  if (row.acknowledged) {
    return "success";
  }
  if (row.required && row.dueAt && new Date(row.dueAt).getTime() < Date.now()) {
    return "destructive";
  }
  if (row.required) {
    return "warning";
  }
  return "muted";
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

function PolicyRow({ row }: { row: ComplianceLibraryRow }) {
  const waiting = row.required && !row.acknowledged;
  const titleId = `policy-${row.id}-title`;

  return (
    <li
      className={cn(
        "bg-card hover:border-border-strong relative flex items-start gap-3 rounded-lg border p-4 transition-colors duration-(--motion-fast)",
        waiting ? "border-chip-warning-edge" : "border-border/70",
      )}
    >
      <IconWell
        icon={ShieldCheck}
        tone={rowTone(row)}
        className="mt-0.5 hidden size-9 sm:grid"
      />
      <div className="grid min-w-0 flex-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          {row.category ? (
            <StatusBadge
              status={{
                label: row.category.label,
                tone: toStatusTone(row.category.tone),
              }}
            />
          ) : null}
          {row.isMandatory ? (
            <StatusBadge status={{ label: "Mandatory", tone: "warning" }} />
          ) : null}
          {row.acknowledged ? (
            <StatusBadge status={{ label: "Acknowledged", tone: "success" }} />
          ) : row.required ? (
            <StatusBadge status={{ label: "Ack required", tone: "destructive" }} />
          ) : null}
        </div>
        <h2 id={titleId} className="text-sm leading-snug font-medium text-balance">
          <Link
            href={routes.policy_detail(row.id)}
            className="focus-visible:outline-ring rounded-sm focus-visible:outline-2 focus-visible:-outline-offset-2"
          >
            <span className="absolute inset-0" aria-hidden />
            {row.title}
          </Link>
        </h2>
        {row.summary ? (
          <p className="text-muted-foreground line-clamp-2 text-sm leading-6">
            {row.summary}
          </p>
        ) : null}
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <CalendarClock className="size-3.5 shrink-0" aria-hidden />
          <span>
            Published {formatDay(row.publishedAt)}
            {row.dueAt && row.required ? ` · Due ${formatDay(row.dueAt)}` : ""}
          </span>
          <span aria-hidden>·</span>
          <span>
            {row.versionLabel} · {row.scope.label} · {row.scope.officeName}
          </span>
        </p>
      </div>
      <ChevronRight
        aria-hidden
        className="text-muted-foreground/60 mt-2 hidden size-4 shrink-0 sm:block"
      />
    </li>
  );
}

export default function PoliciesCompliance() {
  const { library, filterOptions, summary } =
    usePage<PoliciesCompliancePageProps>().props;
  const filters = library.filters as ComplianceLibraryFilters;
  const notice = rejectedFilterMessage(filters);
  const [query, setQuery] = useState(filters.q ?? "");
  const [jurisdiction, setJurisdiction] = useState(filters.jurisdiction);

  function visit(next: Partial<ComplianceLibraryFilters>, page?: number) {
    router.get(
      buildListUrl(routes.policies_compliance(), window.location.search, {
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
      <Head title="Policies" />
      <div className="grid gap-8">
        <PageHeader
          title="Policies"
          description="Published policies for your role and office."
        />

        <MetricStrip>
          <MetricCard label="Published" value={summary.published} />
          <MetricCard
            label="Outstanding"
            value={summary.outstanding}
            tone={summary.outstanding > 0 ? "warning" : "neutral"}
          />
          <MetricCard
            label="Overdue"
            value={summary.overdue}
            tone={summary.overdue > 0 ? "destructive" : "neutral"}
          />
        </MetricStrip>

        <SurfaceCard>
          <PanelHeader divided title="Library" />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() => {
                setQuery("");
                setJurisdiction("");
                visit({ category: "", jurisdiction: "", q: "" }, 1);
              }}
              leading={
                <SearchControl
                  label="Search policies"
                  value={query}
                  onValueChange={setQuery}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => {
                    setQuery("");
                    visit({ q: "" }, 1);
                  }}
                  placeholder="Title or summary"
                />
              }
            >
              <FilterSelect
                label="Category"
                value={filters.category}
                options={filterOptions.categories}
                onChange={(category) => visit({ category }, 1)}
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
                icon={ShieldCheck}
                title={
                  activeCount > 0
                    ? "No policies match these filters"
                    : "No policies published yet"
                }
                description={
                  activeCount > 0
                    ? "Reset the filters to see everything available to you."
                    : "Policies published to your role and office will appear here."
                }
              />
            ) : (
              <ul aria-label="Policies library" className="grid gap-3">
                {library.items.map((row) => (
                  <PolicyRow key={row.id} row={row} />
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

PoliciesCompliance.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Policies",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Policies" },
        ],
      },
      variant: "wide",
    },
  ] as const;
