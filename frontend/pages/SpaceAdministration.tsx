import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Building2,
  DoorOpen,
  Hash,
  MapPin,
  Plus,
  Settings2,
  Users,
} from "lucide-react";
import { useState } from "react";

import {
  CreateSheet,
  DataTable,
  EmptyState,
  FilterControls,
  FilterField,
  FormErrorSummary,
  PageHeader,
  Pagination,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { NativeSelect } from "@/components/design-system/native-select";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { routes } from "@/lib/routes";
import type {
  SpaceAdminFilters,
  SpaceAdministrationPageProps,
  SpaceAdminRow,
} from "@/types";

const VIEW = { all: ["reservations.view_spaces"] };

/** Status drives the chip tone; a retired room must not read as merely paused. */
function statusTone(row: SpaceAdminRow) {
  if (row.status === "retired") return "neutral" as const;
  if (row.status === "inactive") return "warning" as const;
  return row.isReservable ? ("success" as const) : ("warning" as const);
}

function statusLabel(row: SpaceAdminRow) {
  if (row.status === "active" && !row.isReservable) return "Not bookable";
  return row.statusLabel;
}

function SpaceAdministrationPage() {
  const {
    spaces,
    pagination,
    filters,
    filterOptions,
    capabilities,
    errors,
    csrfToken,
  } = usePage<SpaceAdministrationPageProps>().props;
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  function visit(next: Partial<SpaceAdminFilters>) {
    const merged = { ...filters, ...next };
    const params = new URLSearchParams();
    if (merged.q) params.set("q", merged.q);
    if (merged.office) params.set("office", merged.office);
    if (merged.type) params.set("type", merged.type);
    if (merged.status) params.set("status", merged.status);
    if (merged.capacity) params.set("capacity", merged.capacity);
    if (merged.amenities.length) params.set("amenities", merged.amenities.join(","));
    router.get(
      `${routes.space_administration()}?${params.toString()}`,
      {},
      {
        preserveState: true,
        preserveScroll: true,
        replace: true,
        onStart: () => setLoading(true),
        onFinish: () => setLoading(false),
      },
    );
  }

  function goToPage(page: number) {
    const params = new URLSearchParams(window.location.search);
    params.set("page", String(page));
    router.get(
      `${routes.space_administration()}?${params.toString()}`,
      {},
      {
        preserveScroll: true,
      },
    );
  }

  const activeFilterCount = [
    filters.office,
    filters.type,
    filters.status,
    filters.capacity,
    ...filters.amenities,
  ].filter(Boolean).length;

  return (
    <div className="grid gap-6">
      <Head title="Rooms" />
      <PageHeader
        title="Rooms"
        description="Manage the rooms, schedules, and booking policy for every office you administer."
        actions={
          capabilities.canManageSpaces ? (
            <Button type="button" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              New room
            </Button>
          ) : undefined
        }
      />

      <FormErrorSummary errors={errors} />

      <SurfaceCard>
        <SurfaceCardContent className="flex flex-wrap items-end gap-3">
          <SearchControl
            label="Search rooms"
            placeholder="Name or location"
            defaultValue={filters.q}
            onSearch={(value) => visit({ q: value })}
            disabled={loading}
          />
          <FilterControls
            activeCount={activeFilterCount}
            disabled={loading}
            className="basis-full lg:basis-auto lg:has-[button[aria-expanded=true]]:basis-full"
            onReset={() =>
              visit({
                office: "",
                type: "",
                status: "",
                capacity: "",
                amenities: [],
              })
            }
          >
            <FilterField label="Office">
              <NativeSelect
                aria-label="Office"
                value={filters.office}
                onChange={(event) => visit({ office: event.target.value })}
              >
                <option value="">Every office</option>
                {filterOptions.offices.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FilterField>
            <FilterField label="Room type">
              <NativeSelect
                aria-label="Room type"
                value={filters.type}
                onChange={(event) => visit({ type: event.target.value })}
              >
                <option value="">Any type</option>
                {filterOptions.spaceTypes.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FilterField>
            <FilterField label="State">
              <NativeSelect
                aria-label="State"
                value={filters.status}
                onChange={(event) => visit({ status: event.target.value })}
              >
                <option value="">Any state</option>
                {filterOptions.statuses.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FilterField>
            <FilterField label="Minimum capacity">
              <Input
                type="number"
                aria-label="Minimum capacity"
                min={1}
                className="w-28"
                value={filters.capacity}
                onChange={(event) => visit({ capacity: event.target.value })}
              />
            </FilterField>
            <details className="border-input rounded-md border px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium">
                Amenities
                {filters.amenities.length ? ` (${filters.amenities.length})` : ""}
              </summary>
              <div className="mt-3 grid gap-2">
                {filterOptions.amenities.map((item) => {
                  const checked = filters.amenities.includes(item.value);
                  return (
                    <label
                      key={item.value}
                      htmlFor={`amenity-${item.value}`}
                      className="flex items-center gap-2 text-sm"
                    >
                      <Checkbox
                        id={`amenity-${item.value}`}
                        checked={checked}
                        onCheckedChange={() =>
                          visit({
                            amenities: checked
                              ? filters.amenities.filter((v) => v !== item.value)
                              : [...filters.amenities, item.value],
                          })
                        }
                      />
                      {item.label}
                    </label>
                  );
                })}
              </div>
            </details>
          </FilterControls>
        </SurfaceCardContent>
      </SurfaceCard>

      <div className="sr-only" aria-live="polite">
        {loading ? "Loading rooms" : `${pagination.totalItems} rooms`}
      </div>

      {spaces.length === 0 && !loading ? (
        <SurfaceCard>
          <EmptyState
            icon={DoorOpen}
            title={activeFilterCount || filters.q ? "No rooms match" : "No rooms yet"}
            description={
              activeFilterCount || filters.q
                ? "Clear a filter to widen the search."
                : "Create the first room for an office you administer."
            }
            actions={
              activeFilterCount || filters.q ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    visit({
                      q: "",
                      office: "",
                      type: "",
                      status: "",
                      capacity: "",
                      amenities: [],
                    })
                  }
                >
                  Clear filters
                </Button>
              ) : capabilities.canManageSpaces ? (
                <Button type="button" onClick={() => setCreating(true)}>
                  <Plus className="size-4" aria-hidden />
                  New room
                </Button>
              ) : undefined
            }
          />
        </SurfaceCard>
      ) : (
        <div className="grid gap-4">
          <DataTable
            caption="Rooms you administer"
            rows={spaces}
            rowKey={(row) => row.publicId}
            getRowLabel={(row) => row.name}
            loading={loading}
            columns={[
              {
                id: "name",
                header: "Room",
                icon: DoorOpen,
                cell: (row) => (
                  <div className="grid gap-0.5">
                    <Link
                      href={routes.space_administration_workspace(row.publicId)}
                      className="text-foreground font-semibold hover:underline"
                    >
                      {row.name}
                    </Link>
                    <span className="text-muted-foreground text-xs">
                      {row.spaceTypeLabel}
                    </span>
                  </div>
                ),
              },
              {
                id: "office",
                header: "Office",
                icon: Building2,
                hideBelow: "2xl",
                cell: (row) => row.officeName,
              },
              {
                id: "location",
                header: "Location",
                icon: MapPin,
                hideBelow: "4xl",
                cell: (row) =>
                  row.location || (
                    <span className="text-muted-foreground">Not set</span>
                  ),
              },
              {
                id: "capacity",
                header: "Seats",
                icon: Users,
                numeric: true,
                cell: (row) => row.capacity,
              },
              {
                id: "order",
                header: "Order",
                icon: Hash,
                numeric: true,
                hideBelow: "5xl",
                cell: (row) => row.displayOrder,
              },
              {
                id: "amenities",
                header: "Amenities",
                hideBelow: "6xl",
                cell: (row) =>
                  row.amenities.length ? (
                    <div className="flex flex-wrap gap-1">
                      {row.amenities.slice(0, 2).map((amenity) => (
                        <Badge key={amenity.code} variant="secondary">
                          {amenity.name}
                        </Badge>
                      ))}
                      {row.amenities.length > 2 ? (
                        <Badge variant="outline">+{row.amenities.length - 2}</Badge>
                      ) : null}
                    </div>
                  ) : (
                    <span className="text-muted-foreground">None</span>
                  ),
              },
              {
                id: "status",
                header: "State",
                cell: (row) => (
                  <StatusBadge
                    status={{ label: statusLabel(row), tone: statusTone(row) }}
                  />
                ),
              },
              {
                id: "actions",
                header: "Actions",
                cell: (row) => (
                  <Button asChild variant="ghost" size="sm">
                    <Link href={routes.space_administration_workspace(row.publicId)}>
                      <Settings2 className="size-4" aria-hidden />
                      Manage
                    </Link>
                  </Button>
                ),
              },
            ]}
          />
          {pagination.totalPages > 1 ? (
            <Pagination
              pagination={pagination}
              onPageChange={goToPage}
              disabled={loading}
            />
          ) : null}
        </div>
      )}

      {capabilities.canManageSpaces ? (
        <CreateSheet
          open={creating}
          onOpenChange={setCreating}
          title="New room"
          description="Identity now; schedule and booking policy on the next screen."
          submitLabel="Create room"
          action={routes.space_administration_create()}
          csrfToken={csrfToken}
          formId="new-room-form"
        >
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="new-room-office">Office</Label>
              <NativeSelect id="new-room-office" name="office" required>
                {filterOptions.offices.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-room-name">Name</Label>
              <Input id="new-room-name" name="name" required maxLength={200} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-room-type">Room type</Label>
              <NativeSelect id="new-room-type" name="spaceType" required>
                {filterOptions.spaceTypes.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-room-capacity">Seats</Label>
              <Input
                id="new-room-capacity"
                name="capacity"
                type="number"
                min={1}
                defaultValue={8}
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-room-location">Location</Label>
              <Input
                id="new-room-location"
                name="location"
                maxLength={240}
                placeholder="Second floor, east wing"
              />
            </div>
          </div>
        </CreateSheet>
      ) : null}
    </div>
  );
}

export default function SpaceAdministration() {
  return (
    <PermissionRequired permission={VIEW}>
      <SpaceAdministrationPage />
    </PermissionRequired>
  );
}

SpaceAdministration.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Rooms",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Rooms", href: routes.space_administration() },
        ],
      },
    },
  ] as const;
