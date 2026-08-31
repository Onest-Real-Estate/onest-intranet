import { Head, Link, router, usePage } from "@inertiajs/react";

import {
  DataTable,
  type DataTableColumn,
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
  AdminReservationsPageProps,
  FilterOption,
  InventoryReservationListRow,
} from "@/types";

const ANY = "__any__";
const ACCESS = { all: ["web.view_reservations"] };

function statusTone(status: string): "success" | "warning" | "neutral" | "destructive" {
  if (status === "confirmed" || status === "ready_for_pickup") return "success";
  if (status === "requested") return "warning";
  if (status === "cancelled" || status === "denied") return "neutral";
  if (status === "overdue" || status === "lost" || status === "damaged") {
    return "destructive";
  }
  return "neutral";
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

export default function AdminReservations() {
  const { reservations, filterOptions, scope } =
    usePage<AdminReservationsPageProps>().props;
  const filters = reservations.filters;

  function visit(next: Partial<typeof filters>, page?: number) {
    router.get(
      buildListUrl(routes.admin_reservations(), window.location.search, {
        page,
        filters: { ...filters, ...next },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = [filters.status, filters.q].filter(Boolean).length;

  const columns: DataTableColumn<InventoryReservationListRow>[] = [
    {
      id: "reference",
      header: "Reference",
      cell: (row) => (
        <Link href={row.detailHref} className="font-medium hover:underline">
          {row.reference}
        </Link>
      ),
    },
    {
      id: "item",
      header: "Item",
      cell: (row) => row.itemName,
    },
    {
      id: "owner",
      header: "Agent",
      cell: (row) => row.owner?.name ?? "—",
    },
    {
      id: "office",
      header: "Office",
      cell: (row) => row.officeName,
    },
    {
      id: "schedule",
      header: "Pickup → return",
      cell: (row) => `${row.pickupLabel} → ${row.returnLabel}`,
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <StatusBadge
          status={{ label: row.statusLabel, tone: statusTone(row.status) }}
        />
      ),
    },
  ];

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Reservations" />
        <PageHeader
          title="Reservations"
          description={`Inventory holds in ${scope.label}. Lifecycle changes run through the transition service.`}
        />

        <SurfaceCard>
          <PanelHeader title="Reservations" headingLevel="h2" divided />
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount}
              onReset={() => visit({ q: "", status: "" }, 1)}
              leading={
                <SearchControl
                  label="Search reservations"
                  value={filters.q}
                  onSearch={(q) => visit({ q }, 1)}
                  onClear={() => visit({ q: "" }, 1)}
                  placeholder="Reference, item, agent…"
                />
              }
            >
              <FilterSelect
                label="Status"
                value={filters.status}
                options={filterOptions.statuses}
                onChange={(status) => visit({ status }, 1)}
              />
            </FilterControls>

            <DataTable
              frame="bleed"
              caption="Inventory reservations in your scope"
              rows={reservations.items}
              rowKey={(row) => row.publicId}
              getRowLabel={(row) => row.reference}
              columns={columns}
              emptyTitle={
                activeCount > 0 ? "No reservations match" : "No reservations yet"
              }
              emptyDescription={
                activeCount > 0
                  ? "Reset filters to see everything in your scope."
                  : "Agent holds for your offices will appear here."
              }
            />
            {reservations.pagination.totalPages > 1 ? (
              <Pagination
                pagination={reservations.pagination}
                onPageChange={(page) => visit({}, page)}
              />
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

AdminReservations.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reservations",
        breadcrumbs: [
          { label: "Operations", href: routes.admin_reservations() },
          { label: "Reservations" },
        ],
      },
    },
  ] as const;
