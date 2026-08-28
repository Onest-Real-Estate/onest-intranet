import { Head, Link, router, usePage } from "@inertiajs/react";
import { UserRound } from "lucide-react";

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
  FeedbackInboxFilters,
  FeedbackInboxPageProps,
  FeedbackRow,
  FilterOption,
} from "@/types";

const ANY = "__any__";
const ACCESS = { all: ["web.triage_feedback"] };

function formatMoment(value: string): string {
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

/**
 * The support queue.
 *
 * Which tickets appear is decided entirely by `for_reader` with
 * `can_triage=true`; the filters below can only narrow that set.
 * `PermissionRequired` keeps the page out of the way of somebody without the
 * grant, and the Django view refuses them independently.
 */
export default function FeedbackInbox() {
  const { tickets, filterOptions, summary } = usePage<FeedbackInboxPageProps>().props;
  const filters = tickets.filters as FeedbackInboxFilters;

  function visit(next: Partial<FeedbackInboxFilters>, page?: number) {
    router.get(
      buildListUrl(routes.admin_feedback(), window.location.search, {
        page,
        filters: { ...filters, ...next },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = [filters.status, filters.category, filters.assigned].filter(
    Boolean,
  ).length;

  const columns: DataTableColumn<FeedbackRow>[] = [
    {
      id: "reference",
      header: "Ref",
      cell: (row) => (
        <Link
          href={routes.feedback_detail(row.id)}
          className="hover:text-primary focus-visible:ring-ring rounded-sm font-medium tabular-nums focus-visible:ring-2 focus-visible:outline-none"
        >
          {row.reference}
        </Link>
      ),
      hideBelow: "2xl",
    },
    {
      id: "summary",
      header: "Report",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <Link
            href={routes.feedback_detail(row.id)}
            className="hover:text-primary focus-visible:ring-ring truncate rounded-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
          >
            {row.summary}
          </Link>
          <span className="text-muted-foreground truncate text-xs">
            {row.category.label}
            {row.submitter ? ` · ${row.submitter.name}` : ""}
          </span>
        </span>
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
      hideBelow: "3xl",
    },
    {
      id: "assignee",
      header: "Assignee",
      icon: UserRound,
      cell: (row) =>
        row.assignee ? (
          <span className="truncate text-sm">{row.assignee.name}</span>
        ) : (
          <span className="text-muted-foreground text-xs">Unassigned</span>
        ),
      hideBelow: "4xl",
    },
    {
      id: "created",
      header: "Sent",
      cell: (row) => (
        <span className="text-muted-foreground text-xs">
          {formatMoment(row.createdAt)}
        </span>
      ),
      hideBelow: "5xl",
    },
  ];

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Feedback" />
        <PageHeader
          title="Feedback"
          description="Reports from people in the offices you cover."
        />

        <MetricStrip>
          <MetricCard label="Open" value={summary.open} />
          <MetricCard label="Assigned to me" value={summary.mine} />
        </MetricStrip>

        <SurfaceCard>
          <PanelHeader divided title="Queue" />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() => visit({ status: "", category: "", assigned: "", q: "" })}
              leading={
                <SearchControl
                  label="Search reports"
                  value={filters.q}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => visit({ q: "" })}
                  placeholder="Search by summary"
                />
              }
            >
              <FilterSelect
                label="Status"
                value={filters.status}
                options={filterOptions.statuses}
                onChange={(status) => visit({ status }, 1)}
              />
              <FilterSelect
                label="Category"
                value={filters.category}
                options={filterOptions.categories}
                onChange={(category) => visit({ category }, 1)}
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
              caption="Feedback in your scope"
              rows={tickets.items}
              rowKey={(row) => row.id}
              getRowLabel={(row) => row.summary}
              columns={columns}
              emptyTitle={
                activeCount > 0 ? "No reports match these filters" : "Nothing waiting"
              }
              emptyDescription={
                activeCount > 0
                  ? "Reset the filters to see everything in your scope."
                  : "Reports from people in your offices will appear here."
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

FeedbackInbox.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Feedback",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Feedback", href: routes.admin_feedback() },
        ],
      },
      variant: "wide",
    },
  ] as const;
