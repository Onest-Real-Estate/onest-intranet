import { Head, Link, router, usePage } from "@inertiajs/react";
import { CalendarClock, ChevronRight, Info, ShieldCheck } from "lucide-react";
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
  ComplianceLibraryFilters,
  ComplianceLibraryRow,
  FilterOption,
  PoliciesCompliancePageProps,
} from "@/types";

const ANY = "__any__";

function activeFilterCount(filters: ComplianceLibraryFilters): number {
  return [filters.category, filters.jurisdiction, filters.q].filter(Boolean).length;
}

function rejectedFilterMessage(filters: ComplianceLibraryFilters): string | null {
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

function PolicyCard({ row }: { row: ComplianceLibraryRow }) {
  const titleId = `policy-${row.id}-title`;

  return (
    <article aria-labelledby={titleId}>
      <SurfaceCard interactive className="group relative">
        <SurfaceCardContent className="flex min-w-0 items-start gap-4">
          <div className="bg-muted text-muted-foreground flex size-16 shrink-0 items-center justify-center rounded-md">
            <ShieldCheck className="size-5" aria-hidden />
          </div>
          <div className="grid min-w-0 flex-1 gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                status={{
                  label: row.status.label,
                  tone: toStatusTone(row.status.tone),
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
              {row.isMandatory ? (
                <StatusBadge status={{ label: "Mandatory", tone: "warning" }} />
              ) : null}
              {row.acknowledged ? (
                <StatusBadge status={{ label: "Acknowledged", tone: "success" }} />
              ) : row.required ? (
                <StatusBadge status={{ label: "Ack required", tone: "destructive" }} />
              ) : null}
              <span className="text-muted-foreground text-xs">
                {row.versionLabel} · {row.scope.label} · {row.scope.officeName}
              </span>
            </div>
            <h2
              id={titleId}
              className="text-base leading-snug font-semibold text-balance"
            >
              <Link
                href={routes.policy_detail(row.id)}
                className="group-hover:text-primary focus-visible:ring-ring rounded-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none"
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
            <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <CalendarClock className="size-3.5 shrink-0" aria-hidden />
              Published{" "}
              {row.publishedAt
                ? new Date(row.publishedAt).toLocaleDateString()
                : "recently"}
              {row.dueAt && row.required
                ? ` · Due ${new Date(row.dueAt).toLocaleDateString()}`
                : ""}
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

export default function PoliciesCompliance() {
  const { library, filterOptions } = usePage<PoliciesCompliancePageProps>().props;
  const filters = library.filters as ComplianceLibraryFilters;
  const notice = rejectedFilterMessage(filters);
  const [jurisdiction, setJurisdiction] = useState(filters.jurisdiction);

  function visit(next: Partial<ComplianceLibraryFilters>, page?: number) {
    router.get(
      buildListUrl(routes.policies_compliance(), window.location.search, {
        page,
        filters: { ...filters, ...next, rejected: undefined },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Policies & compliance" />
      <div className="grid gap-8">
        <PageHeader
          title="Policies & compliance"
          description="Published policies for your role and office. Acknowledge mandatory ones before their due date."
        />

        <FilterControls
          activeCount={activeFilterCount(filters)}
          onReset={() => {
            setJurisdiction("");
            visit({ category: "", jurisdiction: "", q: "" });
          }}
        >
          <SearchControl
            value={filters.q}
            onSearch={(next) => visit({ q: next })}
            label="Search policies"
            placeholder="Search title or summary"
          />
          <FilterSelect
            label="Category"
            value={filters.category}
            options={filterOptions.categories}
            onChange={(next) => visit({ category: next })}
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
              icon={ShieldCheck}
              title={
                activeFilterCount(filters) > 0
                  ? "No policies match these filters"
                  : "No policies published yet"
              }
              description={
                activeFilterCount(filters) > 0
                  ? "Reset the filters to see everything available to you."
                  : "Policies published to your role and office will appear here."
              }
            />
          </SurfaceCard>
        ) : (
          <section aria-label="Policies library" className="grid gap-3">
            {library.items.map((row) => (
              <PolicyCard key={row.id} row={row} />
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

PoliciesCompliance.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Policies & compliance",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Policies & compliance" },
        ],
      },
    },
  ] as const;
