import { Form, Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, CalendarDays, Package } from "lucide-react";

import {
  Callout,
  FormField,
  FormFieldError,
  FormLabel,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  Timeline,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { routes } from "@/lib/routes";
import type { InventoryReservationDetailPageProps } from "@/types";

function statusTone(status: string): "success" | "warning" | "neutral" | "destructive" {
  if (status === "confirmed" || status === "ready_for_pickup") return "success";
  if (status === "requested") return "warning";
  if (status === "cancelled" || status === "denied") return "neutral";
  if (status === "overdue" || status === "lost" || status === "damaged") {
    return "destructive";
  }
  return "neutral";
}

export default function InventoryReservationDetail() {
  const { reservation, errors, justCreated } =
    usePage<InventoryReservationDetailPageProps>().props;
  useValidationToasts(errors, { title: "Could not update reservation" });
  const formErrors = errors?.form ?? [];

  return (
    <div className="grid gap-8">
      <Head title={reservation.reference || "Reservation"} />
      <div>
        <Button type="button" variant="ghost" size="sm" asChild className="mb-2">
          <Link href={reservation.myReservationsHref}>
            <ArrowLeft className="size-4" aria-hidden />
            My reservations
          </Link>
        </Button>
        <PageHeader
          title={reservation.reference || "Reservation"}
          description={reservation.itemName}
          meta={
            <StatusBadge
              status={{
                label: reservation.statusLabel,
                tone: statusTone(reservation.status),
              }}
            />
          }
        />
      </div>

      {justCreated || reservation.status !== "cancelled" ? (
        <Callout title={justCreated ? "Reservation saved" : "Reservation details"}>
          {justCreated
            ? "Your hold is recorded. Use the instructions below for pickup and return."
            : "Later changes go through office lifecycle actions — dates cannot be edited freely."}
        </Callout>
      ) : null}

      {formErrors.length ? (
        <ul className="text-destructive grid gap-1 text-sm" role="alert">
          {formErrors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}

      <SurfaceCard>
        <PanelHeader title="Lifecycle timeline" headingLevel="h2" divided />
        <SurfaceCardContent>
          {reservation.timeline.length ? (
            <Timeline
              items={reservation.timeline.map((entry) => ({
                id: entry.id,
                title: entry.actionLabel,
                description: [entry.reason, entry.notes].filter(Boolean).join(" · "),
                meta: new Date(entry.occurredAt).toLocaleString(),
                current: entry.id === reservation.timeline.at(-1)?.id,
              }))}
            />
          ) : (
            <p className="text-muted-foreground text-sm">No activity recorded yet.</p>
          )}
        </SurfaceCardContent>
      </SurfaceCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SurfaceCard>
          <PanelHeader title="Schedule" headingLevel="h2" divided />
          <SurfaceCardContent className="grid gap-3 text-sm">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Pickup</dt>
                <dd className="text-foreground">{reservation.pickupLabel}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Return</dt>
                <dd className="text-foreground">{reservation.returnLabel}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Quantity</dt>
                <dd className="text-foreground">{reservation.quantity}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Office</dt>
                <dd className="text-foreground">{reservation.office.name}</dd>
              </div>
            </dl>
            {reservation.purpose ? (
              <div>
                <p className="text-muted-foreground">Purpose</p>
                <p className="text-foreground">{reservation.purpose}</p>
              </div>
            ) : null}
            <p className="text-muted-foreground">
              {reservation.terms.cancelPolicyLabel}
            </p>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader title="Pickup / return instructions" headingLevel="h2" divided />
          <SurfaceCardContent className="grid gap-3 text-sm">
            {reservation.instructions.storageLocation ? (
              <div>
                <p className="text-muted-foreground">Storage / pickup</p>
                <p className="text-foreground">
                  {reservation.instructions.storageLocation}
                </p>
              </div>
            ) : (
              <p className="text-muted-foreground">No storage location on file.</p>
            )}
            {reservation.instructions.notes ? (
              <p className="text-foreground whitespace-pre-line">
                {reservation.instructions.notes}
              </p>
            ) : (
              <p className="text-muted-foreground">No additional instructions.</p>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link href={reservation.myReservationsHref}>
            <CalendarDays className="size-4" aria-hidden />
            My reservations
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href={reservation.dashboardHref}>My Day / Dashboard</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href={reservation.itemHref}>
            <Package className="size-4" aria-hidden />
            Item details
          </Link>
        </Button>
      </div>

      {reservation.canCancel ? (
        <SurfaceCard>
          <PanelHeader title="Cancel reservation" headingLevel="h2" divided />
          <SurfaceCardContent className="grid gap-4">
            <p className="text-muted-foreground text-sm">
              You can cancel until{" "}
              {reservation.cancelCutoffAt
                ? new Date(reservation.cancelCutoffAt).toLocaleString()
                : "the policy cutoff"}
              . This releases capacity for other agents.
            </p>
            <Form
              action={routes.inventory_reservation_cancel(reservation.publicId)}
              method="post"
              className="grid max-w-md gap-3"
              disableWhileProcessing
            >
              {({ processing }) => (
                <>
                  <input
                    type="hidden"
                    name="expectedVersion"
                    value={reservation.expectedVersion}
                  />
                  <input
                    type="hidden"
                    name="expectedStatus"
                    value={reservation.status}
                  />
                  <FormField>
                    <FormLabel htmlFor="cancel-reason">Reason (optional)</FormLabel>
                    <Input id="cancel-reason" name="reason" maxLength={240} />
                    <FormFieldError message={errors?.fields?.reason?.[0]} />
                  </FormField>
                  <Button type="submit" variant="destructive" disabled={processing}>
                    {processing ? "Cancelling…" : "Cancel reservation"}
                  </Button>
                </>
              )}
            </Form>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

InventoryReservationDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reservation",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "My reservations",
            href: routes.inventory_reservations_mine(),
          },
          { label: "Detail" },
        ],
      },
    },
  ] as const;
