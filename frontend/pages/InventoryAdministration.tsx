import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowRight, Package, Tag, Warehouse } from "lucide-react";
import { useState } from "react";

import {
  CreateSheet,
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
import { InventoryFormFields } from "@/components/inventory/InventoryFormFields";
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
import { hasValidationErrors } from "@/lib/validation";
import type {
  AdminInventoryRow,
  FilterOption,
  InventoryAdministrationPageProps,
  InventoryListFilters,
} from "@/types";

const VIEW = { all: ["web.view_inventory"] };
const ALL = "__all__";

const STATE_TONES: Record<
  string,
  { label: string; tone: "success" | "neutral" | "warning" | "destructive" }
> = {
  active: { label: "Active", tone: "success" },
  available: { label: "Available", tone: "success" },
  temporarily_unavailable: { label: "Unavailable", tone: "warning" },
  damaged: { label: "Damaged", tone: "destructive" },
  lost: { label: "Lost", tone: "destructive" },
  retired: { label: "Retired", tone: "neutral" },
};

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

export default function InventoryAdministration() {
  const {
    items,
    filterOptions,
    capabilities,
    scope,
    validation,
    createSheet,
    writableOffices,
    csrfToken,
  } = usePage<InventoryAdministrationPageProps>().props;
  const [query, setQuery] = useState(items.filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(
    Boolean(createSheet?.open) || hasValidationErrors(validation),
  );
  const filters = items.filters as InventoryListFilters;
  const draft = (createSheet?.draft ?? {}) as Record<string, string>;

  function visit(next: Partial<InventoryListFilters>, page?: number) {
    const merged = { ...filters, ...next };
    router.get(
      buildListUrl(routes.admin_inventory(), window.location.search, {
        q: next.q !== undefined ? next.q : query,
        page,
        filters: merged,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = (
    ["category", "tracking_mode", "condition", "state", "owner"] as const
  ).filter((key) => Boolean(filters[key])).length;

  return (
    <PermissionRequired permission={VIEW}>
      <Head title="Inventory" />
      <div className="grid gap-8">
        <PageHeader
          title="Inventory"
          description="Physical assets and pooled stock owned by offices in your scope."
          meta={<span className="text-muted-foreground text-sm">{scope.label}</span>}
          actions={
            capabilities.canManage ? (
              <Button type="button" onClick={() => setCreateOpen(true)}>
                New item
              </Button>
            ) : undefined
          }
        />

        {capabilities.canManage && createOpen ? (
          <CreateSheet
            open={createOpen}
            onOpenChange={setCreateOpen}
            title="New inventory item"
            description="Add serialized equipment or pooled stock to an office you manage."
            action={routes.admin_inventory_create()}
            csrfToken={csrfToken}
            formId="inventory-create-form"
            submitLabel="Create item"
          >
            <input type="hidden" name="context" value="sheet" />
            <InventoryFormFields
              defaults={draft}
              categories={filterOptions.categories}
              trackingModes={filterOptions.trackingModes}
              conditions={filterOptions.conditions}
              writableOffices={writableOffices}
              canViewSensitive={capabilities.canViewSensitive}
            />
          </CreateSheet>
        ) : null}

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount + Number(Boolean(items.filters.q))}
              onReset={() =>
                visit({
                  q: "",
                  category: "",
                  tracking_mode: "",
                  condition: "",
                  state: "",
                  owner: "",
                  include_retired: "",
                })
              }
            >
              <SearchControl
                value={query}
                onValueChange={setQuery}
                onSearch={() => visit({ q: query }, 1)}
                placeholder="Search name, asset id, location"
                className="min-w-56"
              />
              <FilterSelect
                label="Category"
                value={filters.category ?? ""}
                options={filterOptions.categories}
                onChange={(category) => visit({ category }, 1)}
              />
              <FilterSelect
                label="Tracking"
                value={filters.tracking_mode ?? ""}
                options={filterOptions.trackingModes}
                onChange={(tracking_mode) => visit({ tracking_mode }, 1)}
              />
              <FilterSelect
                label="State"
                value={filters.state ?? ""}
                options={filterOptions.states}
                onChange={(state) => visit({ state }, 1)}
              />
              <FilterSelect
                label="Office"
                value={filters.owner ?? ""}
                options={filterOptions.owners}
                onChange={(owner) => visit({ owner }, 1)}
              />
            </FilterControls>

            <DataTable
              caption="Inventory in your administrative scope"
              rows={items.items}
              rowKey={(row) => row.publicId}
              sort={items.sort}
              onSortChange={(sort) => {
                router.get(
                  buildListUrl(routes.admin_inventory(), window.location.search, {
                    sort,
                  }),
                  {},
                  { preserveState: true, preserveScroll: true, replace: true },
                );
              }}
              emptyTitle="No inventory in scope"
              emptyDescription="Nothing matches these filters inside your administrative reach."
              columns={[
                {
                  id: "name",
                  header: "Item",
                  icon: Package,
                  sortable: true,
                  cell: (row: AdminInventoryRow) => (
                    <span className="grid min-w-0 gap-0.5">
                      <Link
                        href={routes.admin_inventory_item(row.publicId)}
                        className="text-primary font-medium underline-offset-2 hover:underline"
                      >
                        {row.name}
                      </Link>
                      <span className="text-muted-foreground truncate text-xs">
                        {row.ownerOffice.name}
                      </span>
                    </span>
                  ),
                },
                {
                  id: "category",
                  header: "Category",
                  icon: Tag,
                  sortable: true,
                  cell: (row) => row.categoryLabel,
                  hideBelow: "2xl",
                },
                {
                  id: "tracking",
                  header: "Tracking",
                  icon: Warehouse,
                  sortable: true,
                  cell: (row) => row.trackingModeLabel,
                  hideBelow: "3xl",
                },
                {
                  id: "quantity",
                  header: "Qty",
                  sortable: true,
                  cell: (row) => String(row.totalQuantity),
                  className: "tabular-nums",
                  headerClassName: "tabular-nums",
                  hideBelow: "4xl",
                },
                {
                  id: "state",
                  header: "State",
                  sortable: true,
                  cell: (row: AdminInventoryRow) => {
                    const tone = STATE_TONES[row.availabilityState] ?? {
                      label: row.availabilityStateLabel,
                      tone: "neutral" as const,
                    };
                    return (
                      <StatusBadge status={{ label: tone.label, tone: tone.tone }} />
                    );
                  },
                },
                {
                  id: "open",
                  header: "",
                  cell: (row: AdminInventoryRow) => (
                    <Link
                      href={routes.admin_inventory_item(row.publicId)}
                      className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                    >
                      Open
                      <ArrowRight className="size-3.5" aria-hidden />
                    </Link>
                  ),
                  className: "w-0 text-right",
                },
              ]}
            />
            <Pagination
              pagination={items.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

InventoryAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Inventory",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Inventory" },
        ],
      },
      variant: "wide",
    },
  ] as const;
