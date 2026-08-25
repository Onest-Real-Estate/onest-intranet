import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  CalendarClock,
  ChevronDown,
  CircleAlert,
  CircleUser,
  Gauge,
  SlidersHorizontal,
  UserRoundCog,
} from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  DatePicker,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import type { FilterOption, NewAgentFilters, NewAgentListPageProps } from "@/types";

const ALL = "__all__";

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
}) {
  return (
    <FilterField label={label}>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger aria-label={label} className="w-full sm:w-44">
          <SelectValue placeholder={`All ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All {label.toLowerCase()}</SelectItem>
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

function dateLabel(value: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? "Not set" : parsed.toLocaleDateString();
}

export default function NewAgentList() {
  const { agents, filterOptions, scopeLabel } = usePage<NewAgentListPageProps>().props;
  const [filters, setFilters] = useState<NewAgentFilters>(agents.filters);

  const activeCount = Object.entries(filters).filter(
    ([key, value]) => key !== "q" && Boolean(value),
  ).length;

  function visit(next: Partial<NewAgentFilters>, page?: number) {
    const merged: NewAgentFilters = { ...filters };
    for (const [key, value] of Object.entries(next)) {
      if (value !== undefined) merged[key] = value;
    }
    setFilters(merged);
    const url = buildListUrl(routes.admin_new_agents(), window.location.search, {
      q: merged.q,
      page,
      filters: merged,
      sort: agents.sort,
    });
    router.get(url, {}, { preserveState: true, preserveScroll: true, replace: true });
  }

  return (
    <PermissionRequired permission={{ all: ["web.view_new_agents"] }}>
      <div className="grid gap-10">
        <Head title="New Agent List" />
        <PageHeader
          title="New Agent List"
          description="Activation progress, ownership, blockers, and the next safe action—derived from each source of record."
          meta={
            <span className="text-muted-foreground text-sm font-medium">
              {scopeLabel}
            </span>
          }
        />

        <SurfaceCard>
          <PanelHeader
            divided
            title="Onboarding queue"
            description="Every result is scoped before search, counts, or source lookups run."
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {agents.pagination.totalItems} active records
              </span>
            }
          />
          <SurfaceCardContent className="grid gap-4">
            <SearchControl
              label="Search new agents"
              value={filters.q}
              onValueChange={(q) => setFilters((current) => ({ ...current, q }))}
              onSearch={(q) => visit({ q }, 1)}
              onClear={() => visit({ q: "" }, 1)}
              placeholder="Name or work email"
              className="max-w-xl"
            />

            <FilterControls
              activeCount={activeCount}
              onReset={() =>
                visit({
                  office: "",
                  owner: "",
                  blocker: "",
                  overallStatus: "",
                  startFrom: "",
                  startTo: "",
                  contractStatus: "",
                  trainingStatus: "",
                })
              }
            >
              <FilterSelect
                label="Status"
                value={filters.overallStatus}
                options={filterOptions.overallStatuses}
                onChange={(overallStatus) => visit({ overallStatus })}
              />
              <FilterSelect
                label="Office"
                value={filters.office}
                options={filterOptions.offices}
                onChange={(office) => visit({ office })}
              />
              <FilterSelect
                label="Owner"
                value={filters.owner}
                options={filterOptions.owners}
                onChange={(owner) => visit({ owner })}
              />
              <FilterSelect
                label="Blocker"
                value={filters.blocker}
                options={filterOptions.blockers}
                onChange={(blocker) => visit({ blocker })}
              />
            </FilterControls>

            <details className="group">
              <summary className="focus-visible:ring-ring text-muted-foreground hover:text-foreground inline-flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-md text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-offset-2">
                <SlidersHorizontal className="size-4 shrink-0" aria-hidden />
                Contract, training, and start dates
                <ChevronDown
                  className="size-4 shrink-0 transition-transform group-open:rotate-180"
                  aria-hidden
                />
              </summary>
              <div className="grid gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-4">
                <FilterSelect
                  label="Contract"
                  value={filters.contractStatus}
                  options={filterOptions.sourceStatuses}
                  onChange={(contractStatus) => visit({ contractStatus })}
                />
                <FilterSelect
                  label="Training"
                  value={filters.trainingStatus}
                  options={filterOptions.sourceStatuses}
                  onChange={(trainingStatus) => visit({ trainingStatus })}
                />
                <FilterField label="Start from">
                  <DatePicker
                    id="start-from"
                    aria-label="Start date from"
                    value={filters.startFrom}
                    onChange={(startFrom) => visit({ startFrom })}
                    placeholder="Pick a start date"
                    className="w-full sm:w-44"
                  />
                </FilterField>
                <FilterField label="Start through">
                  <DatePicker
                    id="start-to"
                    aria-label="Start date through"
                    value={filters.startTo}
                    onChange={(startTo) => visit({ startTo })}
                    placeholder="Pick an end date"
                    className="w-full sm:w-44"
                  />
                </FilterField>
              </div>
            </details>

            <DataTable
              frame="bleed"
              caption="New agents in your effective scope"
              rows={agents.items}
              rowKey={(row) => String(row.user.id)}
              sort={agents.sort}
              onSortChange={(sort) => {
                const url = buildListUrl(
                  routes.admin_new_agents(),
                  window.location.search,
                  { sort },
                );
                router.get(
                  url,
                  {},
                  { preserveState: true, preserveScroll: true, replace: true },
                );
              }}
              emptyTitle="No onboarding records match"
              emptyDescription="Reset filters or check the office and date window. Records outside your scope never appear here."
              columns={[
                {
                  id: "name",
                  header: "Agent",
                  icon: CircleUser,
                  sortable: true,
                  cell: (row) => (
                    <div className="grid min-w-44 gap-0.5">
                      <span className="truncate font-semibold">{row.user.name}</span>
                      <span className="text-muted-foreground truncate text-xs">
                        {row.user.email}
                      </span>
                      {!row.user.isActive ? (
                        <span className="text-destructive text-xs font-medium">
                          Account disabled
                        </span>
                      ) : null}
                    </div>
                  ),
                },
                {
                  id: "overallStatus",
                  header: "Status",
                  icon: BadgeCheck,
                  sortable: true,
                  cell: (row) => (
                    <div className="grid gap-1.5">
                      <StatusBadge status={row.overall} />
                      {row.blockers.length ? (
                        <span className="text-destructive flex items-center gap-1 text-xs">
                          <CircleAlert className="size-3" aria-hidden />
                          {row.blockers.length} blocker
                          {row.blockers.length === 1 ? "" : "s"}
                        </span>
                      ) : null}
                    </div>
                  ),
                },
                {
                  id: "progress",
                  header: "Progress",
                  icon: Gauge,
                  cell: (row) => {
                    const percent = row.progress.total
                      ? Math.round((row.progress.complete / row.progress.total) * 100)
                      : 0;
                    return (
                      <div className="grid min-w-28 gap-1.5">
                        <Progress value={percent} aria-label={`${percent}% complete`} />
                        <span className="text-muted-foreground text-xs tabular-nums">
                          {row.progress.complete} of {row.progress.total}
                        </span>
                      </div>
                    );
                  },
                  hideBelow: "2xl",
                },
                {
                  id: "office",
                  header: "Office",
                  icon: Building2,
                  sortable: true,
                  cell: (row) => row.user.office ?? "Not assigned",
                  hideBelow: "4xl",
                },
                {
                  id: "owner",
                  header: "Owner",
                  icon: UserRoundCog,
                  sortable: true,
                  cell: (row) => row.owner?.name ?? "Unassigned",
                  hideBelow: "5xl",
                },
                {
                  id: "startDate",
                  header: "Starts",
                  icon: CalendarClock,
                  sortable: true,
                  cell: (row) => dateLabel(row.user.startDate),
                  hideBelow: "5xl",
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) => (
                    <Button variant="outline" size="sm" asChild>
                      <Link href={routes.new_agent_onboarding(row.user.id)}>
                        Review
                        <ArrowRight className="size-3.5" aria-hidden />
                      </Link>
                    </Button>
                  ),
                  className: "text-right",
                  headerClassName: "text-right",
                },
              ]}
            />
            <Pagination
              pagination={agents.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

NewAgentList.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "New Agent List",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "New Agent List", href: routes.admin_new_agents() },
        ],
      },
      variant: "standard",
    },
  ] as const;
