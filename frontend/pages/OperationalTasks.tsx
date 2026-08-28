import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarClock,
  Columns3,
  ListIcon,
  Plus,
  TriangleAlert,
  UserRound,
} from "lucide-react";

import {
  DataTable,
  type DataTableColumn,
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
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
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
  FilterOption,
  OperationalTasksPageProps,
  TaskFilters,
  TaskRow,
} from "@/types";

/** `Select` cannot hold an empty value, so "any" needs a sentinel of its own. */
const ANY = "__any__";

const ACCESS = { all: ["web.view_operational_tasks"] };

function formatDue(value: string | null): string {
  if (!value) return "No due date";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
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

/**
 * The due date, and whether it has passed.
 *
 * Overdue is decided server-side and arrives on the row: a terminal task is
 * never overdue however far past its date it sits, and re-deriving that in the
 * client would be a second answer to the same question.
 */
function DueCell({ row }: { row: TaskRow }) {
  if (!row.dueAt) {
    return <span className="text-muted-foreground text-xs">—</span>;
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs",
        row.isOverdue ? "text-destructive font-medium" : "text-muted-foreground",
      )}
    >
      {row.isOverdue ? (
        <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
      ) : (
        <CalendarClock className="size-3.5 shrink-0" aria-hidden />
      )}
      {formatDue(row.dueAt)}
      {row.isOverdue ? <span className="sr-only">(overdue)</span> : null}
    </span>
  );
}

function AssigneeCell({ row }: { row: TaskRow }) {
  if (!row.assignee) {
    return <span className="text-muted-foreground text-xs">Unassigned</span>;
  }
  return <span className="truncate text-sm">{row.assignee.name}</span>;
}

/**
 * One card on the board.
 *
 * The whole card is the target, with the title carrying the accessible name
 * and the only tab stop — a board of five separate links per card is a
 * keyboard maze.
 */
function BoardCard({ row }: { row: TaskRow }) {
  return (
    <article className="border-border/70 bg-card hover:border-border-strong relative grid gap-2 rounded-lg border p-3 transition-colors duration-(--motion-fast)">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusBadge status={row.priority} />
        {row.isOverdue ? (
          <StatusBadge status={{ label: "Overdue", tone: "destructive" }} />
        ) : null}
      </div>
      <h3 className="text-sm leading-snug font-medium text-balance">
        <Link
          href={routes.operational_task_detail(row.id)}
          className="focus-visible:outline-ring rounded-sm focus-visible:outline-2 focus-visible:-outline-offset-2"
        >
          <span className="absolute inset-0" aria-hidden />
          {row.title}
        </Link>
      </h3>
      <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
        <span className="font-medium tabular-nums">{row.reference}</span>
        <span aria-hidden>·</span>
        <span className="truncate">{row.assignee?.name ?? "Unassigned"}</span>
      </p>
    </article>
  );
}

/**
 * One dashboard for internal operational work: onboarding issues, permission
 * requests, tool setup, incidents, and support follow-up.
 *
 * Which rows appear is decided entirely server-side by `for_reader`; the
 * filters below can only narrow that set. `PermissionRequired` hides the page
 * from somebody without the grant, and the Django view refuses them
 * independently — the guard here is for tidiness, never for security.
 */
export default function OperationalTasks() {
  const { tasks, board, view, filterOptions, summary, can } =
    usePage<OperationalTasksPageProps>().props;
  const filters = tasks.filters as TaskFilters;

  function visit(next: Partial<TaskFilters & { view: string }>, page?: number) {
    router.get(
      buildListUrl(routes.operational_tasks(), window.location.search, {
        page,
        filters: { ...filters, ...next },
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
  ].filter(Boolean).length;

  const columns: DataTableColumn<TaskRow>[] = [
    {
      id: "reference",
      header: "Ref",
      cell: (row) => (
        <Link
          href={routes.operational_task_detail(row.id)}
          className="hover:text-primary focus-visible:ring-ring rounded-sm font-medium tabular-nums focus-visible:ring-2 focus-visible:outline-none"
        >
          {row.reference}
        </Link>
      ),
      hideBelow: "2xl",
    },
    {
      id: "title",
      header: "Task",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <Link
            href={routes.operational_task_detail(row.id)}
            className="hover:text-primary focus-visible:ring-ring truncate rounded-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
          >
            {row.title}
          </Link>
          <span className="text-muted-foreground truncate text-xs">
            {row.category.label} · {row.office.name}
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
      cell: (row) => <AssigneeCell row={row} />,
      hideBelow: "4xl",
    },
    {
      id: "due",
      header: "Due",
      icon: CalendarClock,
      cell: (row) => <DueCell row={row} />,
      hideBelow: "5xl",
    },
  ];

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Tasks" />
        <PageHeader
          title="Tasks"
          description="Internal operational work across the offices you cover."
          actions={
            can.manage ? (
              <Button asChild>
                <Link href={`${routes.operational_tasks()}?create=1`}>
                  <Plus aria-hidden />
                  New task
                </Link>
              </Button>
            ) : null
          }
        />

        <MetricStrip>
          <MetricCard label="Open" value={summary.open} />
          <MetricCard
            label="Overdue"
            value={summary.overdue}
            tone={summary.overdue > 0 ? "warning" : "neutral"}
          />
          <MetricCard label="Assigned to me" value={summary.mine} />
        </MetricStrip>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Queue"
            action={
              // A segmented pair rather than a dropdown: two options, and the
              // one you are not on is the whole affordance.
              <fieldset
                aria-label="Layout"
                className="border-border/70 flex items-center gap-0.5 rounded-md border p-0.5"
              >
                <Button
                  variant={view === "list" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7 px-2"
                  aria-pressed={view === "list"}
                  onClick={() => visit({ view: "list" })}
                >
                  <ListIcon aria-hidden />
                  List
                </Button>
                <Button
                  variant={view === "board" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7 px-2"
                  aria-pressed={view === "board"}
                  onClick={() => visit({ view: "board" })}
                >
                  <Columns3 aria-hidden />
                  Board
                </Button>
              </fieldset>
            }
          />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() =>
                visit({ status: "", category: "", priority: "", assigned: "", q: "" })
              }
              leading={
                <SearchControl
                  label="Search tasks"
                  value={filters.q}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => visit({ q: "" })}
                  placeholder="Search by title"
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
                label="Priority"
                value={filters.priority}
                options={filterOptions.priorities}
                onChange={(priority) => visit({ priority }, 1)}
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

            {view === "board" ? (
              board?.some((column) => column.count > 0) ? (
                // Horizontal scroll rather than a wrapping grid: a board whose
                // columns reflow stops being a board.
                <div className="-mx-5 overflow-x-auto px-5 pb-1">
                  <div className="grid min-w-[52rem] grid-cols-5 gap-3 [@media(min-width:80rem)]:min-w-0">
                    {board.map((column) => (
                      <section
                        key={column.status.code}
                        aria-label={column.status.label}
                        className="bg-muted/40 grid content-start gap-2 rounded-lg p-2"
                      >
                        <header className="flex items-center justify-between gap-2 px-1">
                          <h2 className="text-xs font-semibold tracking-[0.06em] uppercase">
                            {column.status.label}
                          </h2>
                          <span className="text-muted-foreground text-xs tabular-nums">
                            {column.count}
                          </span>
                        </header>
                        {column.items.map((row) => (
                          <BoardCard key={row.id} row={row} />
                        ))}
                      </section>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={Columns3}
                  tone="muted"
                  title="Nothing on the board"
                  description="Tasks appear here once there is live work in your scope."
                />
              )
            ) : (
              <>
                <DataTable
                  frame="bleed"
                  caption="Operational tasks in your scope"
                  rows={tasks.items}
                  rowKey={(row) => row.id}
                  getRowLabel={(row) => row.title}
                  columns={columns}
                  emptyTitle={
                    activeCount > 0 ? "No tasks match these filters" : "No tasks yet"
                  }
                  emptyDescription={
                    activeCount > 0
                      ? "Reset the filters to see everything in your scope."
                      : "Work raised for the offices you cover will appear here."
                  }
                />
                {tasks.pagination.totalPages > 1 ? (
                  <Pagination
                    pagination={tasks.pagination}
                    onPageChange={(page) => visit({}, page)}
                  />
                ) : null}
              </>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

OperationalTasks.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Tasks",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Tasks", href: routes.operational_tasks() },
        ],
      },
      variant: "wide",
    },
  ] as const;
