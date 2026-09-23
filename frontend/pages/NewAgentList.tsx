import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowRight, CircleAlert } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  DatePicker,
  FilterControls,
  FilterField,
  Pagination,
  SearchControl,
  StatusBadge,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { PeopleHeader, peopleLayoutContext } from "@/components/people/PeopleHeader";
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
    <FilterField label={label} hideLabel>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label} className="w-full sm:w-44">
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Any {label.toLowerCase()}</SelectItem>
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
      <div className="grid gap-6">
        <Head title="New agents" />
        <PeopleHeader current="new-agents" scope={scopeLabel} />

        <section
          aria-label="Onboarding queue"
          className="bg-card shadow-card grid gap-4 rounded-(--radius-card) border p-5"
        >
          <FilterControls
            activeCount={activeCount}
            leading={
              <SearchControl
                label="Search new agents"
                value={filters.q}
                onValueChange={(q) => setFilters((current) => ({ ...current, q }))}
                onSearch={(q) => visit({ q }, 1)}
                onClear={() => visit({ q: "" }, 1)}
                placeholder="Name or work email"
              />
            }
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
          </FilterControls>

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
                sortable: true,
                cell: (row) => row.user.office ?? "Not assigned",
                hideBelow: "4xl",
              },
              {
                id: "owner",
                header: "Owner",
                sortable: true,
                cell: (row) => row.owner?.name ?? "Unassigned",
                hideBelow: "5xl",
              },
              {
                id: "startDate",
                header: "Starts",
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
        </section>
      </div>
    </PermissionRequired>
  );
}

NewAgentList.layout = () =>
  [
    HubLayout,
    {
      context: peopleLayoutContext("New agents"),
      variant: "wide",
    },
  ] as const;
