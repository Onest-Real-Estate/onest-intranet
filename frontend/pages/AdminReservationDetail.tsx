import { Head, Link, useForm, usePage } from "@inertiajs/react";
import { ArrowLeft } from "lucide-react";

import {
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
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { routes } from "@/lib/routes";
import type { AdminReservationDetailPageProps } from "@/types";

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

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
}

export default function AdminReservationDetail() {
  const { reservation, can, errors } = usePage<AdminReservationDetailPageProps>().props;
  useValidationToasts(errors, { title: "Could not update reservation" });

  const transitionForm = useForm({
    action: "",
    expectedVersion: reservation.expectedVersion,
    expectedStatus: reservation.status,
    reason: "",
    notes: "",
    override: false,
    checkoutQuantity: String(reservation.quantity),
    returnQuantity: String(reservation.quantity),
  });

  function submitAction(action: string, override = false) {
    transitionForm.transform((data) => ({
      ...data,
      action,
      override: override ? "true" : "",
    }));
    transitionForm.post(routes.admin_reservation_transition(reservation.publicId), {
      preserveScroll: true,
      onSuccess: () => transitionForm.reset("reason", "notes"),
    });
  }

  const needsReason = reservation.actions.some((option) => option.requiresReason);

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title={reservation.reference} />
        <div>
          <Button type="button" variant="ghost" size="sm" asChild className="mb-2">
            <Link href={routes.admin_reservations()}>
              <ArrowLeft className="size-4" aria-hidden />
              Reservations
            </Link>
          </Button>
          <PageHeader
            title={reservation.reference}
            description={`${reservation.itemName} · ${reservation.owner?.name ?? "Agent"}`}
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

        <div className="grid gap-6 lg:grid-cols-2">
          <SurfaceCard>
            <PanelHeader title="Schedule" headingLevel="h2" divided />
            <SurfaceCardContent className="grid gap-3 text-sm">
              <dl className="grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">Pickup</dt>
                  <dd>{reservation.pickupLabel}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Return</dt>
                  <dd>{reservation.returnLabel}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Quantity</dt>
                  <dd>{reservation.quantity}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Office</dt>
                  <dd>{reservation.office.name}</dd>
                </div>
              </dl>
              {reservation.checkedOutAt ? (
                <p className="text-muted-foreground">
                  Checked out {formatMoment(reservation.checkedOutAt)}
                  {reservation.checkoutQuantity
                    ? ` · qty ${reservation.checkoutQuantity}`
                    : ""}
                </p>
              ) : null}
              {reservation.returnedAt ? (
                <p className="text-muted-foreground">
                  Returned {formatMoment(reservation.returnedAt)}
                  {reservation.returnConditionNotes
                    ? ` · ${reservation.returnConditionNotes}`
                    : ""}
                </p>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader title="Lifecycle timeline" headingLevel="h2" divided />
            <SurfaceCardContent>
              {reservation.timeline.length ? (
                <Timeline
                  items={reservation.timeline.map((entry) => ({
                    id: entry.id,
                    title: entry.actionLabel,
                    description: [
                      entry.reason,
                      entry.notes,
                      entry.actor?.name ? `By ${entry.actor.name}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · "),
                    meta: formatMoment(entry.occurredAt),
                    tone:
                      entry.toStatus === "cancelled" ||
                      entry.toStatus === "denied" ||
                      entry.toStatus === "lost" ||
                      entry.toStatus === "damaged"
                        ? "destructive"
                        : entry.toStatus === "completed"
                          ? "success"
                          : "neutral",
                    current: entry.id === reservation.timeline.at(-1)?.id,
                  }))}
                />
              ) : (
                <p className="text-muted-foreground text-sm">
                  No transitions recorded yet.
                </p>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        </div>

        {can.approve && reservation.actions.length ? (
          <SurfaceCard>
            <PanelHeader title="Office actions" headingLevel="h2" divided />
            <SurfaceCardContent className="grid gap-4">
              {needsReason ? (
                <FormField>
                  <FormLabel htmlFor="transition-reason">Reason</FormLabel>
                  <Textarea
                    id="transition-reason"
                    value={transitionForm.data.reason}
                    onChange={(event) =>
                      transitionForm.setData("reason", event.target.value)
                    }
                    maxLength={240}
                  />
                  <FormFieldError message={errors?.fields?.reason?.[0]} />
                </FormField>
              ) : null}
              <FormField>
                <FormLabel htmlFor="transition-notes" optional>
                  Notes / condition
                </FormLabel>
                <Input
                  id="transition-notes"
                  value={transitionForm.data.notes}
                  onChange={(event) =>
                    transitionForm.setData("notes", event.target.value)
                  }
                  maxLength={240}
                />
              </FormField>
              <div className="flex flex-wrap gap-2">
                {reservation.actions.map((option) => (
                  <Button
                    key={option.action}
                    type="button"
                    variant={option.overrideOnly ? "outline" : "default"}
                    disabled={transitionForm.processing}
                    onClick={() => submitAction(option.action, option.overrideOnly)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
              {(errors?.form ?? []).map((message) => (
                <p key={message} className="text-destructive text-sm" role="alert">
                  {message}
                </p>
              ))}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>
    </PermissionRequired>
  );
}

AdminReservationDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reservation",
        breadcrumbs: [
          { label: "Operations", href: routes.admin_reservations() },
          { label: "Reservations", href: routes.admin_reservations() },
          { label: "Detail" },
        ],
      },
    },
  ] as const;
