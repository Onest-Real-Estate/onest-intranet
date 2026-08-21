import { Head, router, usePage } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  RoleBadge,
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
import type {
  FilterOption,
  RoleAssignmentAdministrationPageProps,
  RoleAssignmentListFilters,
  RoleAssignmentListRow,
} from "@/types";

const ASSIGN = { all: ["web.assign_user_roles"] };
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
  onChange: (next: string) => void;
}) {
  return (
    <FilterField label={label}>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger aria-label={label}>
          <SelectValue placeholder="Any" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Any</SelectItem>
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
 * Assign User Roles — pick a person, then manage their assignments.
 */
function RoleAssignmentAdministrationPage() {
  const { users, filterOptions, scope } =
    usePage<RoleAssignmentAdministrationPageProps>().props;
  const [query, setQuery] = useState(users.filters.q ?? "");

  function visit(next: Partial<RoleAssignmentListFilters> = {}, page?: number) {
    const filters: Record<string, string> = {
      q: next.q !== undefined ? next.q : (users.filters.q ?? ""),
      role: next.role !== undefined ? next.role : (users.filters.role ?? ""),
      status: next.status !== undefined ? next.status : (users.filters.status ?? ""),
      office: next.office !== undefined ? next.office : (users.filters.office ?? ""),
      region: next.region !== undefined ? next.region : (users.filters.region ?? ""),
    };
    router.get(
      buildListUrl(routes.admin_assign_roles(), window.location.search, {
        page,
        filters,
      }),
      {},
      { preserveState: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Assign User Roles" />
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
        <PageHeader
          title="Assign User Roles"
          description="Grant, schedule, and revoke roles inside the offices and regions you may delegate."
          meta={<span className="text-muted-foreground text-sm">{scope.label}</span>}
        />

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={
                Number(Boolean(users.filters.q)) +
                Number(Boolean(users.filters.role)) +
                Number(Boolean(users.filters.status)) +
                Number(Boolean(users.filters.office)) +
                Number(Boolean(users.filters.region))
              }
              onReset={() =>
                visit({ q: "", role: "", status: "", office: "", region: "" })
              }
            >
              <SearchControl
                value={query}
                onValueChange={setQuery}
                onSearch={() => visit({ q: query })}
                placeholder="Search by name or email"
              />
              <FilterSelect
                label="Role"
                value={users.filters.role ?? ""}
                options={filterOptions.roles}
                onChange={(role) => visit({ role })}
              />
              <FilterSelect
                label="Status"
                value={users.filters.status ?? ""}
                options={filterOptions.statuses}
                onChange={(status) => visit({ status })}
              />
              <FilterSelect
                label="Office or region"
                value={users.filters.office || users.filters.region || ""}
                options={filterOptions.offices.map((office) => ({
                  value: String(office.id),
                  label: office.pathLabel,
                }))}
                onChange={(raw) => {
                  const office = filterOptions.offices.find(
                    (item) => String(item.id) === raw,
                  );
                  if (!office) {
                    visit({ office: "", region: "" });
                    return;
                  }
                  if (office.kind === "region") {
                    visit({ region: String(office.id), office: "" });
                  } else {
                    visit({ office: String(office.id), region: "" });
                  }
                }}
              />
            </FilterControls>

            <DataTable
              caption="People you may assign roles to"
              rows={users.items}
              rowKey={(row) => String(row.id)}
              emptyTitle="No people in scope"
              emptyDescription="Nobody matches these filters inside your delegation reach."
              columns={[
                {
                  id: "person",
                  header: "Person",
                  cell: (row: RoleAssignmentListRow) => (
                    <span className="grid gap-0.5">
                      <span className="font-medium">{row.displayName}</span>
                      <span className="text-muted-foreground text-xs">{row.email}</span>
                    </span>
                  ),
                },
                {
                  id: "office",
                  header: "Office",
                  cell: (row) => row.office?.pathLabel ?? "—",
                  className: "hidden md:table-cell",
                  headerClassName: "hidden md:table-cell",
                },
                {
                  id: "roles",
                  header: "Live roles",
                  cell: (row) =>
                    row.liveRoles.length === 0 ? (
                      <span className="text-muted-foreground text-sm">None</span>
                    ) : (
                      <span className="flex flex-wrap gap-1.5">
                        {row.liveRoles.map((role) => (
                          <RoleBadge
                            key={`${role.role}-${role.scopeLabel}`}
                            code={role.role}
                            label={role.roleLabel}
                            scopeLabel={role.scopeLabel}
                          />
                        ))}
                      </span>
                    ),
                },
                {
                  id: "account",
                  header: "Account",
                  cell: (row) => (
                    <StatusBadge
                      status={{
                        label: row.isActive ? "Active" : "Disabled",
                        tone: row.isActive ? "success" : "destructive",
                      }}
                    />
                  ),
                  className: "hidden lg:table-cell",
                  headerClassName: "hidden lg:table-cell",
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Open</span>,
                  cell: (row) =>
                    row.isSelf ? (
                      <span className="text-muted-foreground text-xs">Your record</span>
                    ) : (
                      <Button asChild variant="outline" size="sm">
                        <a href={routes.admin_assign_roles_user(row.id)}>
                          Manage
                          <ArrowRight className="size-3.5" aria-hidden />
                        </a>
                      </Button>
                    ),
                },
              ]}
            />

            <Pagination
              pagination={users.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

function RoleAssignmentAdministration() {
  return (
    <PermissionRequired permission={ASSIGN}>
      <RoleAssignmentAdministrationPage />
    </PermissionRequired>
  );
}

RoleAssignmentAdministration.layout = (page: React.ReactNode) => (
  <HubLayout>{page}</HubLayout>
);

export default RoleAssignmentAdministration;
