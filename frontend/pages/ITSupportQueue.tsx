import { Head, Link, router, usePage } from "@inertiajs/react";

import {
  DataTable,
  type DataTableColumn,
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
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
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
  ITSupportQueuePageProps,
  SupportQueueFilters,
  SupportTicketRow,
} from "@/types";

/** `Select` cannot hold an empty value, so "any" needs a sentinel of its own. */
const ANY = "__any__";

const ACCESS = { all: ["web.view_it_support"] };

function formatDay(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
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
    <FilterField label={label}>
      <Select
        value={value || ANY}
        onValueChange={(next) => onChange(next === ANY ? "" : next)}
      >
        <SelectTrigger aria-label={label}>
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

/**
 * The IT desk's queue.
 *
 * Every row here already passed the server's scope filter, and every metric is
 * counted on that same scoped queryset — a triager whose reach is one branch
 * sees that branch's figures, not the brokerage's. The page cannot ask for a
 * wider set and could not receive one.
 */
export default function ITSupportQueue() {
  const { tickets, metrics, options, offices } =
    usePage<ITSupportQueuePageProps>().props;
  const filters = tickets.filters as SupportQueueFilters;

  function visit(next: Partial<SupportQueueFilters>, page?: number) {
    router.get(
      buildListUrl(routes.admin_it_support(), window.location.search, {
        page,
        ...next,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = [
    filters.status,
    filters.category,
    filters.priority,
    filters.assigned,
    filters.office,
    filters.q,
  ].filter(Boolean).length;

  const columns: DataTableColumn<SupportTicketRow>[] = [
    {
      id: "reference",
      header: "Ticket",
      cell: (row) => (
        <Link href={routes.it_support_ticket(row.id)} className="grid min-w-0 gap-0.5">
          <span className="truncate text-sm font-medium">{row.subject}</span>
          <span className="text-muted-foreground text-xs tabular-nums">
            {row.reference} · {row.category.label}
          </span>
        </Link>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      id: "priority",
      header: "Priority",
      cell: (row) => <StatusBadge status={row.priority} />,
      hideBelow: "2xl",
    },
    {
      id: "office",
      header: "Office",
      cell: (row) => (
        <span className="truncate text-sm">{row.office?.name ?? "—"}</span>
      ),
      hideBelow: "3xl",
    },
    {
      id: "assignee",
      header: "Owner",
      cell: (row) =>
        row.assignee ? (
          <span className="truncate text-sm">{row.assignee.name}</span>
        ) : (
          <span className="text-muted-foreground text-sm">Unassigned</span>
        ),
      hideBelow: "3xl",
    },
    {
      id: "updated",
      header: "Updated",
      cell: (row) => (
        <span className="text-muted-foreground text-sm tabular-nums">
          {formatDay(row.updatedAt)}
        </span>
      ),
      hideBelow: "4xl",
    },
  ];

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="IT support" />
        <PageHeader
          title="IT support"
          description="Requests raised across the offices you cover."
        />

        <MetricStrip>
          <MetricCard label="Open" value={metrics.open} />
          <MetricCard
            label="Urgent"
            value={metrics.urgent}
            tone={metrics.urgent > 0 ? "destructive" : "neutral"}
          />
          <MetricCard
            label="Unassigned"
            value={metrics.unassigned}
            tone={metrics.unassigned > 0 ? "warning" : "neutral"}
          />
          <MetricCard label="Waiting on requester" value={metrics.waitingUser} />
          <MetricCard label="Resolved this week" value={metrics.resolvedRecently} />
        </MetricStrip>

        <SurfaceCard>
          <PanelHeader divided title="Queue" />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() =>
                visit({
                  status: "",
                  category: "",
                  priority: "",
                  assigned: "",
                  office: "",
                  q: "",
                })
              }
              leading={
                <SearchControl
                  label="Search tickets"
                  value={filters.q}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => visit({ q: "" })}
                  placeholder="Subject or reference"
                />
              }
            >
              <FilterSelect
                label="Status"
                value={filters.status}
                options={options.statuses}
                onChange={(status) => visit({ status }, 1)}
              />
              <FilterSelect
                label="Priority"
                value={filters.priority}
                options={options.priorities}
                onChange={(priority) => visit({ priority }, 1)}
              />
              <FilterSelect
                label="Category"
                value={filters.category}
                options={options.categories}
                onChange={(category) => visit({ category }, 1)}
              />
              <FilterSelect
                label="Office"
                value={filters.office}
                options={offices}
                onChange={(office) => visit({ office }, 1)}
              />
              <FilterSelect
                label="Assignment"
                value={filters.assigned}
                options={[
                  { value: "me", label: "Assigned to me" },
                  { value: "unassigned", label: "Unassigned" },
                ]}
                onChange={(assigned) => visit({ assigned }, 1)}
              />
            </FilterControls>

            <DataTable
              frame="bleed"
              caption="IT support tickets in your scope"
              rows={tickets.items}
              rowKey={(row) => row.id}
              getRowLabel={(row) => row.subject}
              columns={columns}
              emptyTitle={
                activeCount > 0 ? "No tickets match these filters" : "Nothing waiting"
              }
              emptyDescription={
                activeCount > 0
                  ? "Reset the filters to see everything in your scope."
                  : "Requests raised in the offices you cover will appear here."
              }
            />
            {tickets.pagination.totalPages > 1 ? (
              <Pagination
                pagination={tickets.pagination}
                onPageChange={(page) => visit({}, page)}
              />
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

ITSupportQueue.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "IT support",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "IT support" },
        ],
      },
      variant: "wide",
    },
  ] as const;
