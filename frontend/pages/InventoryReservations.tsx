import { Head, Link, router, usePage } from "@inertiajs/react";
import { CalendarDays, Package } from "lucide-react";

import {
  EmptyState,
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { InventoryReservationsPageProps } from "@/types";

function statusTone(status: string): "success" | "warning" | "neutral" | "destructive" {
  if (status === "confirmed" || status === "ready_for_pickup") return "success";
  if (status === "requested") return "warning";
  if (status === "cancelled" || status === "denied") return "neutral";
  if (status === "overdue" || status === "lost" || status === "damaged") {
    return "destructive";
  }
  return "neutral";
}

export default function InventoryReservations() {
  const { reservations, links } = usePage<InventoryReservationsPageProps>().props;
  const rows = reservations.items;

  return (
    <div className="grid gap-8">
      <Head title="My reservations" />
      <PageHeader
        title="My reservations"
        description="Inventory holds for your office. Room bookings will join this list later."
        actions={
          <Button asChild>
            <Link href={links.inventoryHref}>Browse inventory</Link>
          </Button>
        }
      />

      {!rows.length ? (
        <SurfaceCard>
          <EmptyState
            icon={CalendarDays}
            title="No reservations yet"
            description="Reserve office inventory for a pickup and return window when you need it."
            actions={
              <Button asChild>
                <Link href={links.inventoryHref}>Browse office inventory</Link>
              </Button>
            }
          />
        </SurfaceCard>
      ) : (
        <ul className="grid gap-3">
          {rows.map((row) => (
            <li key={row.publicId}>
              <SurfaceCard>
                <SurfaceCardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="grid gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-foreground font-medium">{row.itemName}</p>
                      <StatusBadge
                        status={{
                          label: row.statusLabel,
                          tone: statusTone(row.status),
                        }}
                      />
                    </div>
                    <p className="text-muted-foreground text-sm">
                      {row.reference} · {row.pickupLabel} → {row.returnLabel}
                      {row.quantity > 1 ? ` · qty ${row.quantity}` : ""}
                    </p>
                    <p className="text-muted-foreground text-sm">{row.officeName}</p>
                  </div>
                  <Button asChild variant="outline" size="sm">
                    <Link href={row.detailHref}>
                      <Package className="size-4" aria-hidden />
                      Open
                    </Link>
                  </Button>
                </SurfaceCardContent>
              </SurfaceCard>
            </li>
          ))}
        </ul>
      )}

      {reservations.pagination && reservations.pagination.totalPages > 1 ? (
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={reservations.pagination.page <= 1}
            onClick={() =>
              router.get(
                routes.inventory_reservations_mine(),
                { page: reservations.pagination.page - 1 },
                { preserveState: true, replace: true },
              )
            }
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={
              reservations.pagination.page >= reservations.pagination.totalPages
            }
            onClick={() =>
              router.get(
                routes.inventory_reservations_mine(),
                { page: reservations.pagination.page + 1 },
                { preserveState: true, replace: true },
              )
            }
          >
            Next
          </Button>
        </div>
      ) : null}
    </div>
  );
}

InventoryReservations.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "My reservations",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My reservations" },
        ],
      },
    },
  ] as const;
