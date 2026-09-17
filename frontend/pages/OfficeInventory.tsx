import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Building2,
  CalendarRange,
  ImageOff,
  LayoutGrid,
  List,
  Package,
  PackageOpen,
  SearchX,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  EmptyState,
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  OfficeInventoryFilters,
  OfficeInventoryItemRow,
  OfficeInventoryPageProps,
} from "@/types";

const ALL = "__all__";
const SEARCH_DEBOUNCE_MS = 300;

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

function ItemPhoto({ item }: { item: OfficeInventoryItemRow }) {
  if (item.photoHref) {
    return (
      <img src={item.photoHref} alt="" className="bg-muted size-full object-cover" />
    );
  }
  return (
    <div
      className="bg-muted text-muted-foreground flex size-full items-center justify-center"
      aria-hidden
    >
      <ImageOff className="size-6" />
    </div>
  );
}

function AvailabilityBadge({ item }: { item: OfficeInventoryItemRow }) {
  const availability = item.availability;
  if (!availability) {
    return <StatusBadge status={{ label: "Dates not checked", tone: "neutral" }} />;
  }
  if (availability.isAvailable) {
    return (
      <StatusBadge
        status={{
          label: `${availability.availableQuantity} available`,
          tone: "success",
        }}
      />
    );
  }
  return (
    <StatusBadge
      status={{
        label: availability.reasonLabel || "Unavailable",
        tone: "warning",
      }}
    />
  );
}

function ItemCard({ item, view }: { item: OfficeInventoryItemRow; view: string }) {
  const isList = view === "list";
  return (
    <li
      className={cn(
        "border-border overflow-hidden rounded-lg border",
        isList
          ? "grid gap-3 p-3 sm:grid-cols-[5rem_minmax(0,1fr)_auto] sm:items-center"
          : "grid grid-rows-[9rem_minmax(0,1fr)]",
      )}
    >
      <div
        className={cn(
          "bg-muted overflow-hidden",
          isList ? "size-20 shrink-0 rounded-md" : "size-full",
        )}
      >
        <ItemPhoto item={item} />
      </div>
      <div className={cn("grid min-w-0 gap-1", !isList && "p-3 pt-2")}>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Link
            href={item.detailHref}
            className="text-foreground text-sm font-medium hover:underline"
          >
            {item.name}
          </Link>
          <AvailabilityBadge item={item} />
        </div>
        <p className="text-muted-foreground text-sm">
          {item.categoryLabel}
          {" · "}
          {item.conditionLabel}
          {" · "}
          {item.trackingModeLabel}
          {item.totalQuantity > 1 ? ` · Qty ${item.totalQuantity}` : ""}
        </p>
        <p className="text-muted-foreground text-xs">{item.ownerOffice.name}</p>
        {item.assetId ? (
          <p className="text-muted-foreground text-xs">Asset {item.assetId}</p>
        ) : null}
        {item.storageLocation ? (
          <p className="text-muted-foreground text-xs">
            Pickup: {item.storageLocation}
          </p>
        ) : null}
        {item.myReservation ? (
          <p className="text-foreground text-xs">
            Your reservation: {item.myReservation.statusLabel}
            {item.myReservation.returnDue
              ? ` · return ${item.myReservation.returnDue}`
              : ""}
          </p>
        ) : null}
      </div>
      <div
        className={cn(
          "flex items-center gap-2",
          isList ? "sm:justify-end" : "border-border border-t px-3 py-2",
        )}
      >
        <Button type="button" variant="outline" size="sm" asChild>
          <Link href={item.detailHref}>Details</Link>
        </Button>
        <Button
          type="button"
          size="sm"
          asChild
          disabled={Boolean(item.availability && !item.availability.isAvailable)}
        >
          <Link
            href={item.reserveHref}
            aria-disabled={Boolean(item.availability && !item.availability.isAvailable)}
            className={cn(
              item.availability &&
                !item.availability.isAvailable &&
                "pointer-events-none opacity-50",
            )}
          >
            Reserve
          </Link>
        </Button>
      </div>
    </li>
  );
}

/**
 * Agent Office Inventory browser — reservable stock at the signed-in user's
 * primary office with URL-backed filters and date-range availability.
 */
export default function OfficeInventory() {
  const {
    items,
    office,
    filterOptions,
    capabilities,
    dateErrors,
    serviceError,
    empty,
  } = usePage<OfficeInventoryPageProps>().props;
  const filters = items.filters as OfficeInventoryFilters;
  const [query, setQuery] = useState(filters.q ?? "");
  const [pickup, setPickup] = useState(filters.pickup ?? "");
  const [returnDate, setReturnDate] = useState(filters.return ?? "");
  const [quantity, setQuantity] = useState(filters.quantity || "1");
  const view = filters.view === "list" ? "list" : "grid";
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    setQuery(filters.q ?? "");
    setPickup(filters.pickup ?? "");
    setReturnDate(filters.return ?? "");
    setQuantity(filters.quantity || "1");
  }, [filters.q, filters.pickup, filters.return, filters.quantity]);

  useEffect(() => {
    const serverQuery = filtersRef.current.q ?? "";
    if (query === serverQuery) {
      return;
    }
    const handle = window.setTimeout(() => {
      const current = filtersRef.current;
      router.get(
        buildListUrl(routes.office_inventory(), window.location.search, {
          q: query,
          page: 1,
          filters: { ...current, q: query },
        }),
        {},
        { preserveState: true, preserveScroll: true, replace: true },
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  function visit(next: Partial<OfficeInventoryFilters>, page?: number) {
    const merged = { ...filters, ...next };
    router.get(
      buildListUrl(routes.office_inventory(), window.location.search, {
        q: next.q !== undefined ? next.q : query,
        page,
        filters: merged,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = (
    ["category", "condition", "pickup", "return", "available_only"] as const
  ).filter((key) => Boolean(filters[key])).length;

  const emptyIcon =
    empty?.kind === "no-office"
      ? Building2
      : empty?.kind === "unavailable-range"
        ? CalendarRange
        : empty?.kind === "no-results"
          ? SearchX
          : PackageOpen;

  return (
    <div className="grid gap-8">
      <Head title="Office inventory" />
      <PageHeader
        title="Office inventory"
        description="Browse reservable equipment and stock at your office."
        meta={
          office ? (
            <span className="text-muted-foreground text-sm">{office.name}</span>
          ) : undefined
        }
      />

      {serviceError ? (
        <SurfaceCard>
          <EmptyState
            icon={Package}
            title="Inventory is temporarily unavailable"
            description={serviceError}
          />
        </SurfaceCard>
      ) : empty?.kind === "no-office" ? (
        <SurfaceCard>
          <EmptyState
            icon={Building2}
            title={empty.title}
            description={empty.description}
            actions={
              <Button asChild variant="outline">
                <Link href={routes.profile()}>Open profile</Link>
              </Button>
            }
          />
        </SurfaceCard>
      ) : (
        <>
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4">
              <FilterControls
                activeCount={activeCount + Number(Boolean(filters.q))}
                onReset={() => {
                  setQuery("");
                  setPickup("");
                  setReturnDate("");
                  setQuantity("1");
                  visit({
                    q: "",
                    category: "",
                    condition: "",
                    pickup: "",
                    return: "",
                    quantity: "1",
                    available_only: "",
                    view,
                  });
                }}
                leading={
                  <SearchControl
                    value={query}
                    onValueChange={setQuery}
                    onSearch={(next) => visit({ q: next }, 1)}
                    onClear={() => visit({ q: "" }, 1)}
                    label="Search inventory"
                    placeholder={
                      capabilities.canViewSensitive
                        ? "Search name or asset id"
                        : "Search by item name"
                    }
                  />
                }
              >
                <FilterSelect
                  label="Category"
                  value={filters.category ?? ""}
                  options={filterOptions.categories}
                  onChange={(category) => visit({ category }, 1)}
                />
                <FilterSelect
                  label="Condition"
                  value={filters.condition ?? ""}
                  options={filterOptions.conditions}
                  onChange={(condition) => visit({ condition }, 1)}
                />
                <FilterField label="Pickup date">
                  <Input
                    type="date"
                    value={pickup}
                    aria-label="Pickup date"
                    onChange={(event) => setPickup(event.target.value)}
                    onBlur={() => visit({ pickup }, 1)}
                  />
                </FilterField>
                <FilterField label="Return date">
                  <Input
                    type="date"
                    value={returnDate}
                    aria-label="Return date"
                    onChange={(event) => setReturnDate(event.target.value)}
                    onBlur={() => visit({ return: returnDate }, 1)}
                  />
                </FilterField>
                <FilterField label="Quantity">
                  <Input
                    type="number"
                    min={1}
                    value={quantity}
                    aria-label="Requested quantity"
                    className="w-24"
                    onChange={(event) => setQuantity(event.target.value)}
                    onBlur={() =>
                      visit({ quantity: String(Math.max(1, Number(quantity) || 1)) }, 1)
                    }
                  />
                </FilterField>
                <FilterField label="Availability filter" hideLabel>
                  <Select
                    value={filters.available_only ? "available" : "all"}
                    onValueChange={(next) =>
                      visit({ available_only: next === "available" ? "1" : "" }, 1)
                    }
                  >
                    <SelectTrigger size="sm" aria-label="Availability filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any availability</SelectItem>
                      <SelectItem value="available">Available for dates</SelectItem>
                    </SelectContent>
                  </Select>
                </FilterField>
                <fieldset className="flex items-center gap-1 border-0 p-0">
                  <legend className="sr-only">Layout</legend>
                  <Button
                    type="button"
                    size="icon"
                    variant={view === "grid" ? "secondary" : "ghost"}
                    aria-pressed={view === "grid"}
                    aria-label="Grid view"
                    onClick={() => visit({ view: "grid" })}
                  >
                    <LayoutGrid className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant={view === "list" ? "secondary" : "ghost"}
                    aria-pressed={view === "list"}
                    aria-label="List view"
                    onClick={() => visit({ view: "list" })}
                  >
                    <List className="size-4" />
                  </Button>
                </fieldset>
              </FilterControls>
              {dateErrors.length ? (
                <ul className="text-destructive grid gap-1 text-sm" role="alert">
                  {dateErrors.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          {empty ? (
            <SurfaceCard>
              <EmptyState
                icon={emptyIcon}
                title={empty.title}
                description={empty.description}
                actions={
                  empty.kind === "no-results" || empty.kind === "unavailable-range" ? (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setQuery("");
                        setPickup("");
                        setReturnDate("");
                        visit({
                          q: "",
                          category: "",
                          condition: "",
                          pickup: "",
                          return: "",
                          available_only: "",
                          quantity: "1",
                          view,
                        });
                      }}
                    >
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
            </SurfaceCard>
          ) : (
            <>
              <ul
                className={cn(
                  "grid gap-4",
                  view === "grid" ? "sm:grid-cols-2 xl:grid-cols-3" : "grid-cols-1",
                )}
              >
                {items.items.map((item) => (
                  <ItemCard key={item.publicId} item={item} view={view} />
                ))}
              </ul>
              <Pagination
                pagination={items.pagination}
                onPageChange={(page) => visit({}, page)}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

OfficeInventory.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Office inventory",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office inventory" },
        ],
      },
    },
  ] as const;
