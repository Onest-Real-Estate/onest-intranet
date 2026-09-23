import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowDownUp, Users } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import {
  Callout,
  DataTable,
  type DataTableColumn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FilterControls,
  FilterField,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  NativeSelect,
  Pagination,
  SearchControl,
  StatusBadge,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { PeopleHeader, peopleLayoutContext } from "@/components/people/PeopleHeader";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { buildListUrl } from "@/lib/list-query";
import { hasPermission } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import { cn, initials } from "@/lib/utils";
import type {
  DirectoryFilters,
  DirectoryRow,
  FilterOption,
  UserDirectoryPageProps,
} from "@/types";
import type { SortState } from "@/types/design-system";

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

/** The sorts the toolbar offers, as the server's own sort keys. */
const SORTS: { value: string; label: string; sort: SortState }[] = [
  { value: "name-asc", label: "Name A–Z", sort: { key: "name", direction: "asc" } },
  { value: "name-desc", label: "Name Z–A", sort: { key: "name", direction: "desc" } },
  {
    value: "lastLogin-desc",
    label: "Recently signed in",
    sort: { key: "lastLogin", direction: "desc" },
  },
  { value: "office-asc", label: "Office", sort: { key: "office", direction: "asc" } },
];

/** How many role chips a row shows before folding the rest into "+N". */
const VISIBLE_ROLES = 2;

function shortDay(value: string | null): string {
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
    <FilterField label={label} hideLabel>
      <Select
        value={value || ALL}
        disabled={disabled}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger
          size="sm"
          aria-label={label}
          aria-describedby={hint ? hintId : undefined}
          className="w-full sm:w-44"
        >
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
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-xs leading-4">
          {hint}
        </p>
      ) : null}
    </FilterField>
  );
}

/**
 * Role chips, folded after two. The chips link into the person's role
 * workspace when the reader may assign roles — changing a role keeps its
 * preview and scope check there rather than happening in a row dropdown.
 */
function RoleChips({ row, canAssign }: { row: DirectoryRow; canAssign: boolean }) {
  if (row.roles.length === 0) {
    return <span className="text-muted-foreground text-sm">No role</span>;
  }
  const shown = row.roles.slice(0, VISIBLE_ROLES);
  const rest = row.roles.slice(VISIBLE_ROLES);
  const chips = (
    <span className="flex flex-wrap items-center gap-1.5">
      {shown.map((role) => (
        <span
          key={role}
          className="bg-chip-neutral border-chip-neutral-edge inline-flex h-6 items-center rounded-sm border px-2 text-xs font-medium whitespace-nowrap"
        >
          {role}
        </span>
      ))}
      {rest.length > 0 ? (
        <span
          title={rest.join(", ")}
          className="text-muted-foreground inline-flex h-6 items-center rounded-sm border px-1.5 text-xs font-medium tabular-nums"
        >
          +{rest.length}
        </span>
      ) : null}
    </span>
  );
  if (!canAssign) return chips;
  return (
    <Link
      href={routes.admin_assign_roles_user(row.id)}
      aria-label={`Manage roles for ${row.name}: ${row.roles.join(", ")}`}
      className="focus-visible:ring-ring/50 -m-1 inline-flex rounded-md p-1 outline-none transition-colors duration-(--motion-fast) hover:bg-muted focus-visible:ring-[3px]"
    >
      {chips}
    </Link>
  );
}

type AccountIntent = { row: DirectoryRow; action: "disable" | "reactivate" };

/**
 * Disable or reactivate from the row, with the reason the record requires.
 *
 * It posts to the same account-state write as the record page, marked to come
 * back here: success returns to this list with its filters, and a refusal
 * (a missing reason, or somebody else changed the record first) re-renders
 * the list with the dialog still open and the message in it.
 */
function AccountDialog({
  intent,
  errors,
  onClose,
}: {
  intent: AccountIntent | null;
  errors: UserDirectoryPageProps["errors"];
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [processing, setProcessing] = useState(false);
  const disabling = intent?.action === "disable";

  useEffect(() => {
    if (intent) setReason("");
  }, [intent]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!intent) return;
    router.post(
      routes.user_account_state(intent.row.id),
      {
        action: intent.action,
        business_reason: reason,
        expected_version: intent.row.account?.version ?? "",
        returnTo: "users",
        returnQuery: window.location.search,
      },
      {
        preserveScroll: true,
        preserveState: true,
        onStart: () => setProcessing(true),
        onFinish: () => setProcessing(false),
        onSuccess: (page) => {
          const next = page.props as unknown as UserDirectoryPageProps;
          const refused =
            next.errors.form.length > 0 || Object.keys(next.errors.fields).length > 0;
          if (!refused) onClose();
        },
      },
    );
  }

  const reasonError = errors.fields.business_reason?.[0];

  return (
    <Dialog open={intent !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="max-w-md">
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>
              {disabling ? "Deactivate" : "Reactivate"} {intent?.row.name}
            </DialogTitle>
            <DialogDescription>
              {disabling
                ? "They are signed out on their next request and cannot sign in until reactivated."
                : "They can sign in again with their Microsoft account."}
            </DialogDescription>
          </DialogHeader>

          <FormErrorSummary
            errors={{ fields: {}, form: errors.form }}
            title="This change was not saved"
          />

          <FormField>
            <FormLabel htmlFor="business_reason" required>
              Business reason
            </FormLabel>
            <Textarea
              id="business_reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              maxLength={500}
              placeholder={
                disabling
                  ? "Left the brokerage on 30 September."
                  : "Rejoined the Fairfax office."
              }
              aria-invalid={Boolean(reasonError) || undefined}
              aria-describedby={reasonError ? "business_reason_error" : "reason-help"}
            />
            <p id="reason-help" className="text-muted-foreground text-xs">
              Recorded on their account history with your name.
            </p>
            <FormFieldError id="business_reason_error" message={reasonError} />
          </FormField>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant={disabling ? "destructive" : "default"}
              disabled={processing || !reason.trim()}
            >
              {processing
                ? "Saving…"
                : disabling
                  ? "Deactivate account"
                  : "Reactivate account"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Users — the first People tab.
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
  const {
    users,
    summary,
    filterOptions,
    scope,
    visible,
    canOpenRecord,
    pageSizeOptions,
    errors,
    user: viewer,
  } = usePage<UserDirectoryPageProps>().props;
  const [filters, setFilters] = useState<DirectoryFilters>(users.filters);
  const [intent, setIntent] = useState<AccountIntent | null>(null);
  const canAssign = hasPermission(viewer, { all: ["web.assign_user_roles"] });

  const activeCount = Object.entries(filters).filter(
    ([key, value]) => key !== "q" && Boolean(value),
  ).length;
  const filtered = activeCount > 0 || Boolean(filters.q);
  const currentSort =
    SORTS.find(
      (option) =>
        option.sort.key === users.sort?.key &&
        option.sort.direction === users.sort?.direction,
    )?.value ?? "";

  function go(url: string) {
    router.get(url, {}, { preserveState: true, preserveScroll: true, replace: true });
  }

  function visit(next: Partial<DirectoryFilters>, page?: number) {
    const merged: DirectoryFilters = { ...filters, ...(next as DirectoryFilters) };
    setFilters(merged);
    go(
      buildListUrl(routes.admin_users(), window.location.search, {
        q: merged.q,
        page,
        filters: merged,
        sort: users.sort,
      }),
    );
  }

  const columns: DataTableColumn<DirectoryRow>[] = [
    {
      id: "name",
      header: "User",
      sortable: true,
      cell: (row) => (
        <div className="flex min-w-48 items-center gap-3">
          <Avatar className="size-10" aria-hidden>
            <AvatarFallback className="bg-foreground text-background text-xs font-semibold">
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
      id: "account",
      header: "Status",
      // Onboarding rides under the account state rather than taking a column:
      // it only matters while it is unfinished, and a column of "Complete"
      // would spend the width the row's actions need.
      cell: (row) => (
        <div className="grid justify-items-start gap-1">
          <StatusBadge status={row.accountState} />
          {visible.onboarding && row.onboarding.value !== "complete" ? (
            <span className="text-muted-foreground text-xs whitespace-nowrap">
              Onboarding {row.onboarding.label.toLowerCase()}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      id: "roles",
      header: "Role",
      cell: (row) => <RoleChips row={row} canAssign={canAssign} />,
      hideBelow: "3xl",
    },
    {
      id: "office",
      header: "Office",
      sortable: true,
      cell: (row) => (
        <div className="grid min-w-32 gap-0.5" title={row.officePathLabel ?? undefined}>
          <span className="truncate">{row.officeName ?? "Not assigned"}</span>
          {row.regionName ? (
            <span className="text-muted-foreground truncate text-xs">
              {row.regionName}
            </span>
          ) : null}
        </div>
      ),
      hideBelow: "4xl",
    },
  ];

  if (visible.administration) {
    columns.push({
      id: "status",
      header: "Agent status",
      sortable: true,
      cell: (row) =>
        row.agentStatus ? <StatusBadge status={row.agentStatus} /> : null,
      hideBelow: "6xl",
    });
  }
  if (visible.contract) {
    columns.push({
      id: "contract",
      header: "Contract",
      cell: (row) => (row.contract ? <StatusBadge status={row.contract} /> : null),
      hideBelow: "7xl",
    });
  }
  columns.push({
    id: "lastLogin",
    header: "Last sign-in",
    sortable: true,
    cell: (row) => (
      <span className="text-muted-foreground tabular-nums">
        {shortDay(row.lastLoginAt)}
      </span>
    ),
    hideBelow: "5xl",
  });
  if (canOpenRecord || users.items.some((row) => row.account)) {
    columns.push({
      id: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="flex justify-end gap-2">
          {row.account ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="bg-card min-w-24"
              onClick={() =>
                setIntent({ row, action: row.isActive ? "disable" : "reactivate" })
              }
            >
              <span className="sr-only">{row.name}: </span>
              {row.isActive ? "Deactivate" : "Activate"}
            </Button>
          ) : null}
          {canOpenRecord ? (
            <Button variant="outline" size="sm" asChild className="bg-card">
              <Link href={routes.user_administration(row.id)}>
                <span className="sr-only">{row.name}: </span>
                Edit
              </Link>
            </Button>
          ) : null}
        </div>
      ),
      className: "text-right",
      headerClassName: "text-right",
    });
  }

  return (
    <PermissionRequired permission={{ all: ["web.view_users"] }}>
      <div className="grid gap-6">
        <Head title="Users" />
        <PeopleHeader current="users" scope={scope.label} />

        <fieldset className="flex flex-wrap items-center gap-1.5 border-0 p-0">
          <legend className="sr-only">Quick view</legend>
          {[
            { value: "", label: "Everyone", count: summary.total },
            { value: "active", label: "Active", count: summary.active },
            { value: "disabled", label: "Deactivated", count: summary.disabled },
          ].map((option) => {
            const active = (filters.account || "") === option.value;
            return (
              <button
                key={option.label}
                type="button"
                aria-pressed={active}
                onClick={() => visit({ account: option.value })}
                className={cn(
                  "focus-visible:ring-ring/50 inline-flex h-8 items-center gap-2 rounded-md border px-3 text-sm font-medium outline-none transition-colors duration-(--motion-fast) focus-visible:ring-[3px]",
                  active
                    ? "bg-card border-foreground/30 text-foreground shadow-card"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )}
              >
                {option.label}
                <span className="text-muted-foreground tabular-nums">
                  {option.count}
                </span>
              </button>
            );
          })}
          {summary.pendingOnboarding > 0 ? (
            <span className="text-muted-foreground ml-auto text-sm">
              <span className="text-warning-ink font-medium tabular-nums">
                {summary.pendingOnboarding}
              </span>{" "}
              still onboarding
            </span>
          ) : null}
        </fieldset>

        <section
          aria-label="People in your scope"
          className="bg-card shadow-card grid gap-4 rounded-(--radius-card) border p-5"
        >
          <FilterControls
            activeCount={activeCount}
            onReset={() => visit(EMPTY_FILTERS)}
            leading={
              <SearchControl
                label="Search people"
                value={filters.q}
                onValueChange={(q) => setFilters((current) => ({ ...current, q }))}
                onSearch={(q) => visit({ q }, 1)}
                onClear={() => visit({ q: "" })}
                placeholder={
                  visible.administration
                    ? "Search by name, work email, or agent ID"
                    : "Search by name or work email"
                }
              />
            }
            trailing={
              <div className="relative flex items-center">
                <NativeSelect
                  aria-label="Sort by"
                  value={currentSort}
                  onChange={(event) => {
                    const option = SORTS.find(
                      (item) => item.value === event.target.value,
                    );
                    if (option) {
                      go(
                        buildListUrl(routes.admin_users(), window.location.search, {
                          sort: option.sort,
                        }),
                      );
                    }
                  }}
                  className="bg-card h-9 w-48 pl-9"
                >
                  {currentSort ? null : <option value="">Sort by</option>}
                  {SORTS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </NativeSelect>
                <ArrowDownUp
                  className="text-muted-foreground pointer-events-none absolute left-3 size-4"
                  aria-hidden
                />
              </div>
            }
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
            onSortChange={(sort) =>
              go(buildListUrl(routes.admin_users(), window.location.search, { sort }))
            }
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
            pageSizeOptions={pageSizeOptions}
            onPageSizeChange={(pageSize) =>
              go(
                buildListUrl(routes.admin_users(), window.location.search, {
                  pageSize,
                }),
              )
            }
          />
        </section>

        {!canOpenRecord ? (
          <Callout icon={Users}>
            You can look people up, but not open their administrative record. Ask for
            the user administration permission if you need to maintain offices, status,
            or credentials.
          </Callout>
        ) : null}
      </div>

      <AccountDialog intent={intent} errors={errors} onClose={() => setIntent(null)} />
    </PermissionRequired>
  );
}

UserDirectory.layout = () =>
  [
    HubLayout,
    {
      context: peopleLayoutContext("Users"),
      variant: "wide",
    },
  ] as const;
