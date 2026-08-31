import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, ImageOff, Package } from "lucide-react";
import { useEffect, useState } from "react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { OfficeInventoryItemPageProps } from "@/types";

export default function OfficeInventoryItem() {
  const { item, office, filters, dateErrors, serviceError } =
    usePage<OfficeInventoryItemPageProps>().props;
  const [pickup, setPickup] = useState(filters.pickup ?? "");
  const [returnDate, setReturnDate] = useState(filters.return ?? "");
  const [quantity, setQuantity] = useState(filters.quantity || "1");

  useEffect(() => {
    setPickup(filters.pickup ?? "");
    setReturnDate(filters.return ?? "");
    setQuantity(filters.quantity || "1");
  }, [filters.pickup, filters.return, filters.quantity]);

  function reload(next: { pickup?: string; return?: string; quantity?: string }) {
    router.get(
      buildListUrl(item.detailHref, window.location.search, {
        filters: {
          ...filters,
          pickup: next.pickup ?? pickup,
          return: next.return ?? returnDate,
          quantity: next.quantity ?? quantity,
        },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const availability = item.availability;
  const reserveDisabled = Boolean(availability && !availability.isAvailable);

  return (
    <div className="grid gap-8">
      <Head title={item.name} />
      <div>
        <Button type="button" variant="ghost" size="sm" asChild className="mb-2">
          <Link href={routes.office_inventory()}>
            <ArrowLeft className="size-4" aria-hidden />
            Back to inventory
          </Link>
        </Button>
        <PageHeader
          title={item.name}
          description={`${item.categoryLabel} · ${item.conditionLabel}`}
          meta={
            office ? (
              <span className="text-muted-foreground text-sm">{office.name}</span>
            ) : undefined
          }
        />
      </div>

      {serviceError ? (
        <SurfaceCard>
          <EmptyState
            icon={Package}
            title="Inventory is temporarily unavailable"
            description={serviceError}
          />
        </SurfaceCard>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
          <SurfaceCard className="overflow-hidden">
            <div className="bg-muted aspect-square">
              {item.photoHref ? (
                <img src={item.photoHref} alt="" className="size-full object-cover" />
              ) : (
                <div
                  className="text-muted-foreground flex size-full items-center justify-center"
                  aria-hidden
                >
                  <ImageOff className="size-8" />
                </div>
              )}
            </div>
          </SurfaceCard>

          <div className="grid gap-6">
            <SurfaceCard>
              <PanelHeader title="Item details" headingLevel="h2" divided />
              <SurfaceCardContent className="grid gap-3 text-sm">
                <dl className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <dt className="text-muted-foreground">Tracking</dt>
                    <dd className="text-foreground">{item.trackingModeLabel}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Quantity on hand</dt>
                    <dd className="text-foreground">{item.totalQuantity}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Office</dt>
                    <dd className="text-foreground">{item.ownerOffice.name}</dd>
                  </div>
                  {item.assetId ? (
                    <div>
                      <dt className="text-muted-foreground">Asset id</dt>
                      <dd className="text-foreground">{item.assetId}</dd>
                    </div>
                  ) : null}
                </dl>
                {item.storageLocation ? (
                  <div>
                    <p className="text-muted-foreground">Storage / pickup</p>
                    <p className="text-foreground">{item.storageLocation}</p>
                  </div>
                ) : null}
                {item.notes ? (
                  <div>
                    <p className="text-muted-foreground">Instructions</p>
                    <p className="text-foreground whitespace-pre-line">{item.notes}</p>
                  </div>
                ) : null}
                {item.myReservation ? (
                  <div className="border-border rounded-md border p-3">
                    <p className="text-foreground font-medium">
                      Your active reservation
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {item.myReservation.statusLabel}
                      {item.myReservation.returnDue
                        ? ` · return by ${item.myReservation.returnDue}`
                        : ""}
                    </p>
                  </div>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader title="Check availability" headingLevel="h2" divided />
              <SurfaceCardContent className="grid gap-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="grid gap-1.5">
                    <Label htmlFor="inventory-pickup">Pickup date</Label>
                    <Input
                      id="inventory-pickup"
                      type="date"
                      value={pickup}
                      onChange={(event) => setPickup(event.target.value)}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="inventory-return">Return date</Label>
                    <Input
                      id="inventory-return"
                      type="date"
                      value={returnDate}
                      onChange={(event) => setReturnDate(event.target.value)}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label htmlFor="inventory-quantity">Quantity</Label>
                    <Input
                      id="inventory-quantity"
                      type="number"
                      min={1}
                      value={quantity}
                      onChange={(event) => setQuantity(event.target.value)}
                    />
                  </div>
                </div>
                {dateErrors.length ? (
                  <ul className="text-destructive grid gap-1 text-sm" role="alert">
                    {dateErrors.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      reload({
                        pickup,
                        return: returnDate,
                        quantity: String(Math.max(1, Number(quantity) || 1)),
                      })
                    }
                  >
                    Check dates
                  </Button>
                  {availability ? (
                    <StatusBadge
                      status={{
                        label: availability.isAvailable
                          ? `${availability.availableQuantity} of ${availability.totalQuantity} available`
                          : availability.reasonLabel || "Unavailable",
                        tone: availability.isAvailable ? "success" : "warning",
                      }}
                    />
                  ) : (
                    <span className="text-muted-foreground text-sm">
                      Choose pickup and return dates to check capacity.
                    </span>
                  )}
                </div>
                <Button
                  type="button"
                  asChild
                  disabled={reserveDisabled}
                  className={cn(reserveDisabled && "pointer-events-none opacity-50")}
                >
                  <Link
                    href={item.reserveHref}
                    aria-disabled={reserveDisabled || undefined}
                  >
                    Start reservation
                  </Link>
                </Button>
              </SurfaceCardContent>
            </SurfaceCard>
          </div>
        </div>
      )}
    </div>
  );
}

OfficeInventoryItem.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Inventory item",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office inventory", href: routes.office_inventory() },
          { label: "Item" },
        ],
      },
    },
  ] as const;
