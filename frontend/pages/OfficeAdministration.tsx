import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowRight, BadgeCheck, Building2, Tag } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
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
  OfficeAdministrationPageProps,
  OfficeListFilters,
  OfficeListRow,
} from "@/types";

const MANAGE = { all: ["web.manage_offices"] };
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
    <FilterField label={label} hideLabel>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label}>
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

function OfficeAdministrationPage() {
  const { offices, filterOptions, scope, capabilities } =
    usePage<OfficeAdministrationPageProps>().props;
  const [query, setQuery] = useState(offices.filters.q ?? "");

  function visit(next: Partial<OfficeListFilters> = {}, page?: number) {
    const filters: Record<string, string> = {
      q: next.q !== undefined ? next.q : (offices.filters.q ?? ""),
      kind: next.kind !== undefined ? next.kind : (offices.filters.kind ?? ""),
      status: next.status !== undefined ? next.status : (offices.filters.status ?? ""),
      region: next.region !== undefined ? next.region : (offices.filters.region ?? ""),
    };
    router.get(
      buildListUrl(routes.admin_offices(), window.location.search, {
        page,
        filters,
      }),
      {},
      { preserveState: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Offices" />
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Offices"
          description="Manage branch information, contacts, and hierarchy in your scope."
          meta={
            <span className="text-muted-foreground text-sm">
              {scope.label}
              {capabilities.companyWide ? " · Company structure" : ""}
            </span>
          }
        />

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={
                Number(Boolean(offices.filters.q)) +
                Number(Boolean(offices.filters.kind)) +
                Number(Boolean(offices.filters.status)) +
                Number(Boolean(offices.filters.region))
              }
              onReset={() => visit({ q: "", kind: "", status: "", region: "" })}
            >
              <SearchControl
                value={query}
                onValueChange={setQuery}
                onSearch={() => visit({ q: query }, 1)}
                placeholder="Search offices"
              />
              <FilterSelect
                label="Kind"
                value={offices.filters.kind ?? ""}
                options={filterOptions.kinds}
                onChange={(kind) => visit({ kind }, 1)}
              />
              <FilterSelect
                label="Status"
                value={offices.filters.status ?? ""}
                options={filterOptions.statuses}
                onChange={(status) => visit({ status }, 1)}
              />
              <FilterSelect
                label="Region"
                value={offices.filters.region ?? ""}
                options={filterOptions.regions}
                onChange={(region) => visit({ region }, 1)}
              />
            </FilterControls>

            <DataTable
              caption="Offices in your administrative scope"
              rows={offices.items}
              rowKey={(row) => String(row.id)}
              emptyTitle="No offices in scope"
              emptyDescription="Nothing matches these filters inside your administrative reach."
              columns={[
                {
                  id: "name",
                  header: "Office",
                  icon: Building2,
                  cell: (row: OfficeListRow) => (
                    <span className="grid gap-0.5">
                      <Link
                        href={routes.admin_office(row.id)}
                        className="text-primary font-medium underline-offset-2 hover:underline"
                      >
                        {row.name}
                      </Link>
                      <span className="text-muted-foreground text-xs">
                        {row.pathLabel}
                      </span>
                    </span>
                  ),
                },
                {
                  id: "kind",
                  header: "Kind",
                  icon: Tag,
                  cell: (row) => row.kindLabel,
                  hideBelow: "2xl",
                },
                {
                  id: "region",
                  header: "Region",
                  icon: Building2,
                  cell: (row) => row.regionName,
                  hideBelow: "4xl",
                },
                {
                  id: "status",
                  header: "Status",
                  icon: BadgeCheck,
                  cell: (row) => (
                    <StatusBadge
                      status={{
                        label: row.isActive ? "Active" : "Inactive",
                        tone: row.isActive ? "success" : "neutral",
                      }}
                    />
                  ),
                  hideBelow: "4xl",
                },
                {
                  id: "open",
                  header: <span className="sr-only">Open</span>,
                  cell: (row) => (
                    <Button asChild variant="outline" size="sm">
                      <Link href={routes.admin_office(row.id)}>
                        Open
                        <ArrowRight className="size-3.5" aria-hidden />
                      </Link>
                    </Button>
                  ),
                },
              ]}
            />

            <Pagination
              pagination={offices.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

export default function OfficeAdministration() {
  return (
    <PermissionRequired permission={MANAGE}>
      <OfficeAdministrationPage />
    </PermissionRequired>
  );
}

OfficeAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Offices",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Offices" },
        ],
      },
    },
  ] as const;
