import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  ArrowRight,
  Building2,
  CalendarClock,
  CircleUser,
  ClipboardCheck,
  FileSignature,
  IdCard,
  ShieldCheck,
  UserRoundX,
  Users,
} from "lucide-react";
import { useState } from "react";

import {
  Callout,
  DataTable,
  type DataTableColumn,
  FilterControls,
  FilterField,
  MetricCard,
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
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
import { initials } from "@/lib/utils";
import type {
  DirectoryFilters,
  DirectoryRow,
  FilterOption,
  UserDirectoryPageProps,
} from "@/types";

const ALL = "__all__";

/** Every filter key, so "Reset" clears exactly what the server accepts. */
const EMPTY_FILTERS: Omit<DirectoryFilters, "q"> = {
  office: "",
  region: "",
  role: "",
  status: "",
  account: "",
  onboarding: "",
  contract: "",
  lastLogin: "",
};

function relativeDay(value: string | null): string {
  if (!value) return "Never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Never";
  return parsed.toLocaleDateString(undefined, {
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
  disabled = false,
  hint,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  hint?: string;
}) {
  // aria-describedby is a whitespace-separated token list, so the id may not
  // contain spaces — derive it from the label instead of embedding it.
  const hintId = `${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-hint`;
  return (
    <FilterField label={label}>
      <Select
        value={value || ALL}
        disabled={disabled}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger
          aria-label={label}
          aria-describedby={hint ? hintId : undefined}
          className="w-full sm:w-44"
        >
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
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-xs leading-4">
          {hint}
        </p>
      ) : null}
    </FilterField>
  );
}

/**
 * The scoped people directory.
 *
 * Two things about this page are load-bearing and easy to undo by accident.
 * First, every row it shows already passed the server's scope filter — it
 * never asks for a wider set and could not receive one. Second, the
 * permission-gated columns are driven by keys being *absent* from the row, not
 * by a truthiness check: rendering a dash where `agentStatus` is missing would
 * quietly tell a reader that the field exists and they are not allowed to see
 * it. `visible` decides whether the column exists at all.
 */
export default function UserDirectory() {
  const { users, summary, filterOptions, scope, visible, canOpenRecord } =
    usePage<UserDirectoryPageProps>().props;
  const [filters, setFilters] = useState<DirectoryFilters>(users.filters);

  const activeCount = Object.entries(filters).filter(
    ([key, value]) => key !== "q" && Boolean(value),
  ).length;
  const filtered = activeCount > 0 || Boolean(filters.q);

  function visit(next: Partial<DirectoryFilters>, page?: number) {
    const merged: DirectoryFilters = { ...filters, ...(next as DirectoryFilters) };
    setFilters(merged);
    router.get(
      buildListUrl(routes.admin_users(), window.location.search, {
        q: merged.q,
        page,
        filters: merged,
        sort: users.sort,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const columns: DataTableColumn<DirectoryRow>[] = [
    {
      id: "name",
      header: "Name",
      icon: CircleUser,
      sortable: true,
      cell: (row) => (
        <div className="flex min-w-40 items-center gap-3 sm:min-w-56">
          <Avatar className="ring-border size-9 ring-1" aria-hidden>
            <AvatarFallback className="bg-secondary text-secondary-foreground text-xs font-semibold">
              {initials(row.name)}
            </AvatarFallback>
          </Avatar>
          <div className="grid min-w-0 gap-0.5">
            <span className="truncate font-semibold">{row.name}</span>
            <span className="text-muted-foreground truncate text-xs">{row.email}</span>
          </div>
        </div>
      ),
    },
    {
      id: "office",
      header: "Office",
      icon: Building2,
      sortable: true,
      cell: (row) => (
        <div className="grid min-w-32 gap-0.5">
          <span className="truncate">{row.officeName ?? "Not assigned"}</span>
          {row.regionName ? (
            <span className="text-muted-foreground truncate text-xs">
              {row.regionName}
            </span>
          ) : null}
        </div>
      ),
      hideBelow: "2xl",
    },
    {
      id: "account",
      header: "Account",
      icon: ShieldCheck,
      cell: (row) => <StatusBadge status={row.accountState} />,
    },
  ];

  if (visible.administration) {
    columns.push({
      id: "status",
      header: "Agent status",
      icon: IdCard,
      sortable: true,
      cell: (row) =>
        row.agentStatus ? <StatusBadge status={row.agentStatus} /> : null,
      hideBelow: "5xl",
    });
  }
  if (visible.onboarding) {
    columns.push({
      id: "onboarding",
      header: "Onboarding",
      icon: ClipboardCheck,
      cell: (row) => <StatusBadge status={row.onboarding} />,
      hideBelow: "6xl",
    });
  }
  if (visible.contract) {
    columns.push({
      id: "contract",
      header: "Contract",
      icon: FileSignature,
      cell: (row) => (row.contract ? <StatusBadge status={row.contract} /> : null),
      hideBelow: "7xl",
    });
  }
  columns.push({
    id: "lastLogin",
    header: "Last sign-in",
    icon: CalendarClock,
    sortable: true,
    cell: (row) => (
      <span className="text-muted-foreground tabular-nums">
        {relativeDay(row.lastLoginAt)}
      </span>
    ),
    hideBelow: "4xl",
  });
  if (canOpenRecord) {
    columns.push({
      id: "actions",
      header: <span className="sr-only">Actions</span>,
      cell: (row) => (
        <Button
          variant="outline"
          size="sm"
          asChild
          className="ml-auto size-9 px-0 sm:h-8 sm:w-auto sm:px-3"
        >
          <Link href={routes.user_administration(row.id)}>
            <span className="sr-only">Open the record for {row.name}</span>
            <span className="hidden sm:inline" aria-hidden>
              Open
            </span>
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </Button>
      ),
      className: "text-right",
      headerClassName: "text-right",
    });
  }

  return (
    <PermissionRequired permission={{ all: ["web.view_users"] }}>
      <div className="grid gap-10">
        <Head title="Users" />
        <PageHeader
          title="Users"
          description="Search, review, and maintain the people inside your office and region scope."
          meta={
            <span className="text-muted-foreground text-sm font-medium">
              {scope.label}
            </span>
          }
        />

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="People in scope" value={summary.total} />
          <MetricCard label="Active accounts" value={summary.active} tone="success" />
          <MetricCard
            label="Disabled accounts"
            value={summary.disabled}
            tone={summary.disabled > 0 ? "warning" : "neutral"}
            subline={
              summary.disabled > 0 ? "Signed out on their next request." : undefined
            }
          />
          <MetricCard
            label="Onboarding incomplete"
            value={summary.pendingOnboarding}
            tone={summary.pendingOnboarding > 0 ? "warning" : "neutral"}
          />
        </div>

        <SurfaceCard>
          <PanelHeader
            divided
            title="People in your scope"
            description="Scope is applied before search, filters, and counts. Nothing outside it can be reached from here."
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {users.pagination.totalItems}{" "}
                {users.pagination.totalItems === 1 ? "person" : "people"}
              </span>
            }
          />
          <SurfaceCardContent className="grid gap-4">
            <SearchControl
              label="Search people"
              value={filters.q}
              onValueChange={(q) => setFilters((current) => ({ ...current, q }))}
              onSearch={(q) => visit({ q }, 1)}
              onClear={() => visit({ q: "" })}
              placeholder={
                visible.administration
                  ? "Name, work email, or agent ID"
                  : "Name or work email"
              }
              className="max-w-xl"
            />

            <FilterControls
              activeCount={activeCount}
              onReset={() => visit(EMPTY_FILTERS)}
            >
              <FilterSelect
                label="Office"
                value={filters.office}
                options={filterOptions.offices}
                onChange={(office) => visit({ office })}
              />
              <FilterSelect
                label="Region"
                value={filters.region}
                options={filterOptions.regions}
                onChange={(region) => visit({ region })}
              />
              <FilterSelect
                label="Role"
                value={filters.role}
                options={filterOptions.roles}
                onChange={(role) => visit({ role })}
              />
              <FilterSelect
                label="Account"
                value={filters.account}
                options={filterOptions.accountStates}
                onChange={(account) => visit({ account })}
              />
              {filterOptions.agentStatuses ? (
                <FilterSelect
                  label="Agent status"
                  value={filters.status}
                  options={filterOptions.agentStatuses.map((status) => ({
                    value: status.value,
                    label: status.label,
                  }))}
                  onChange={(status) => visit({ status })}
                />
              ) : null}
              <FilterSelect
                label="Onboarding"
                value={filters.onboarding}
                options={filterOptions.onboardingStates}
                onChange={(onboarding) => visit({ onboarding })}
              />
              {visible.contract ? (
                <FilterSelect
                  label="Contract"
                  value={filters.contract}
                  options={filterOptions.contract.options}
                  disabled={!filterOptions.contract.available}
                  hint={
                    filterOptions.contract.available
                      ? undefined
                      : filterOptions.contract.reason
                  }
                  onChange={(contract) => visit({ contract })}
                />
              ) : null}
              <FilterSelect
                label="Last sign-in"
                value={filters.lastLogin}
                options={filterOptions.lastLoginWindows}
                onChange={(lastLogin) => visit({ lastLogin })}
              />
            </FilterControls>

            <DataTable
              frame="bleed"
              caption="People you may administer"
              rows={users.items}
              rowKey={(row) => String(row.id)}
              getRowLabel={(row) => row.name}
              sort={users.sort}
              onSortChange={(sort) => {
                router.get(
                  buildListUrl(routes.admin_users(), window.location.search, { sort }),
                  {},
                  { preserveState: true, preserveScroll: true, replace: true },
                );
              }}
              emptyTitle={filtered ? "Nobody matches" : "Nobody in your scope yet"}
              emptyDescription={
                filtered
                  ? "Reset the filters or widen the search. People outside your office and region scope never appear here."
                  : "Your role does not scope you to anybody yet. Ask an administrator to widen your office or region assignment."
              }
              columns={columns}
            />
            <Pagination
              pagination={users.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          </SurfaceCardContent>
        </SurfaceCard>

        {!canOpenRecord ? (
          <Callout icon={Users}>
            You can look people up, but not open their administrative record. Ask for
            the user administration permission if you need to maintain offices, status,
            or credentials.
          </Callout>
        ) : null}

        {summary.disabled > 0 && !filters.account ? (
          <Callout
            tone="warning"
            icon={UserRoundX}
            action={
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => visit({ account: "disabled" })}
              >
                Show them
              </Button>
            }
          >
            {summary.disabled} disabled{" "}
            {summary.disabled === 1 ? "account is" : "accounts are"} still in your
            scope. Disabled accounts cannot sign in.
          </Callout>
        ) : null}
      </div>
    </PermissionRequired>
  );
}

UserDirectory.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Users",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Users", href: routes.admin_users() },
        ],
      },
      variant: "standard",
    },
  ] as const;
