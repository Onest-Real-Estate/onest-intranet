import { Head, Link, router, usePage } from "@inertiajs/react";
import { ChevronLeft, Clock3, DoorOpen, MapPin, Package } from "lucide-react";
import { useState } from "react";

import {
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { MyReservationDetailPageProps } from "@/types";

const SOURCE_ICON = { room: DoorOpen, inventory: Package } as const;

export default function MyReservationDetail() {
  const { reservation, links } = usePage<MyReservationDetailPageProps>().props;
  const [confirming, setConfirming] = useState(false);
  const Icon = SOURCE_ICON[reservation.source] ?? DoorOpen;
  const action = reservation.actions.find((item) => item.method === "post");

  const when = reservation.allDay
    ? "All day"
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "full",
        timeStyle: "short",
        timeZone: reservation.timezone,
      }).format(new Date(reservation.startsAt));

  return (
    <div className="grid gap-6">
      <Head title={`${reservation.title} · My reservations`} />
      <PageHeader
        title={reservation.title}
        description={reservation.subtitle}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              <Icon className="size-3" aria-hidden />
              {reservation.sourceLabel}
            </Badge>
            <StatusBadge
              status={{
                label: reservation.displayStatusLabel,
                tone: reservation.tone,
              }}
            />
            <span className="text-muted-foreground text-sm">
              {reservation.reference}
            </span>
          </div>
        }
        actions={
          <Button asChild variant="outline">
            <Link href={links.indexHref}>
              <ChevronLeft className="size-4" aria-hidden />
              All reservations
            </Link>
          </Button>
        }
      />

      <SurfaceCard>
        <PanelHeader title="Details" divided />
        <SurfaceCardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground text-xs font-semibold">When</dt>
              <dd className="text-foreground text-sm">
                <Clock3 className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />
                {when}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs font-semibold">Office</dt>
              <dd className="text-foreground text-sm">
                <MapPin className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />
                {reservation.officeName}
              </dd>
            </div>
            <div>
              {/* The owning domain's own wording, never replaced by the
                  normalized chip above it. */}
              <dt className="text-muted-foreground text-xs font-semibold">
                Status in {reservation.sourceLabel.toLowerCase()}
              </dt>
              <dd className="text-foreground text-sm">{reservation.statusLabel}</dd>
            </div>
            {reservation.quantity ? (
              <div>
                <dt className="text-muted-foreground text-xs font-semibold">
                  Quantity
                </dt>
                <dd className="text-foreground text-sm">{reservation.quantity}</dd>
              </div>
            ) : null}
            {reservation.purpose ? (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground text-xs font-semibold">Purpose</dt>
                <dd className="text-foreground text-sm">{reservation.purpose}</dd>
              </div>
            ) : null}
            {reservation.instructions ? (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground text-xs font-semibold">
                  Instructions
                </dt>
                <dd className="text-foreground text-sm">{reservation.instructions}</dd>
              </div>
            ) : null}
            {reservation.contact ? (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground text-xs font-semibold">
                  Where to collect
                </dt>
                <dd className="text-foreground text-sm">{reservation.contact}</dd>
              </div>
            ) : null}
          </dl>
        </SurfaceCardContent>
      </SurfaceCard>

      {action ? (
        <SurfaceCard>
          <PanelHeader
            title="Actions"
            description="Handled by the team that owns this booking, with their rules."
            divided
          />
          <SurfaceCardContent>
            {confirming ? (
              <div className="grid gap-3">
                <p className="text-sm">
                  This releases the booking for someone else and cannot be undone.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setConfirming(false)}
                  >
                    Keep it
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() =>
                      router.post(action.href, {
                        expectedStatus: action.expectedStatus,
                      })
                    }
                  >
                    {action.label}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                type="button"
                variant="outline"
                className={cn(action.destructive && "text-destructive")}
                onClick={() => setConfirming(true)}
              >
                {action.label}
              </Button>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

MyReservationDetail.layout = () =>
  [
    HubLayout,
    {
      variant: "focused",
      context: {
        title: "Reservation",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My reservations", href: routes.my_reservations() },
          { label: "Reservation" },
        ],
      },
    },
  ] as const;
