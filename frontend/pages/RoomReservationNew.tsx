import { Form, Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, CalendarCheck, Clock3, MapPin, Users } from "lucide-react";
import { useMemo } from "react";

import {
  Callout,
  EmptyState,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { RoomReservationNewPageProps } from "@/types";

function dateTimeLabel(value: string, timeZone: string) {
  if (!value) return "Not selected";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(value));
}

export default function RoomReservationNew() {
  const { space, draft, office, errors, links } =
    usePage<RoomReservationNewPageProps>().props;
  const submissionKey = useMemo(
    () =>
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    [],
  );
  const fieldErrors = errors.fields ?? {};

  return (
    <PermissionRequired permission={{ all: ["reservations.book_spaces"] }}>
      <div className="grid gap-6">
        <Head title="Reserve room" />
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-2">
            <Link href={links.calendarHref}>
              <ArrowLeft className="size-4" aria-hidden />
              Back to availability
            </Link>
          </Button>
          <PageHeader
            title="Reserve room"
            description="Review the office-local time, add a business purpose, and submit for a final availability check."
            meta={
              office ? (
                <span className="text-muted-foreground text-sm">
                  {office.name} · {office.timezone}
                </span>
              ) : undefined
            }
          />
        </div>

        {!space || !office || !draft.startsAt || !draft.endsAt ? (
          <SurfaceCard>
            <EmptyState
              icon={CalendarCheck}
              title="Choose an available time first"
              description="Open Room availability and select one of the offered start times."
              actions={
                <Button asChild>
                  <Link href={links.calendarHref}>View room availability</Link>
                </Button>
              }
            />
          </SurfaceCard>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <SurfaceCard>
              <SurfaceCardContent className="grid gap-5">
                {errors.form.length ? (
                  <ul className="text-destructive grid gap-1 text-sm" role="alert">
                    {errors.form.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                ) : null}
                <Form
                  action={routes.room_reservation_create()}
                  method="post"
                  disableWhileProcessing
                  className="grid gap-5"
                >
                  {({ processing }) => (
                    <>
                      <input type="hidden" name="space" value={space.publicId} />
                      <input type="hidden" name="startsAt" value={draft.startsAt} />
                      <input type="hidden" name="endsAt" value={draft.endsAt} />
                      <input type="hidden" name="submissionKey" value={submissionKey} />
                      <FormField>
                        <FormLabel htmlFor="purpose">Business purpose</FormLabel>
                        <Textarea
                          id="purpose"
                          name="purpose"
                          defaultValue={draft.purpose}
                          maxLength={240}
                          rows={4}
                          required
                          aria-invalid={Boolean(fieldErrors.purpose)}
                          aria-describedby="purpose-help purpose-error"
                        />
                        <FormDescription id="purpose-help">
                          Visible to you and authorized reservation administrators.
                        </FormDescription>
                        <FormFieldError
                          id="purpose-error"
                          message={fieldErrors.purpose?.[0]}
                        />
                      </FormField>
                      <FormField>
                        <FormLabel htmlFor="attendeeCount">Attendees</FormLabel>
                        <Input
                          id="attendeeCount"
                          name="attendeeCount"
                          type="number"
                          min={1}
                          max={space.capacity}
                          defaultValue={draft.attendeeCount}
                          aria-invalid={Boolean(fieldErrors.attendeeCount)}
                          aria-describedby="attendee-help attendee-error"
                        />
                        <FormDescription id="attendee-help">
                          Optional. Capacity is {space.capacity} people.
                        </FormDescription>
                        <FormFieldError
                          id="attendee-error"
                          message={fieldErrors.attendeeCount?.[0]}
                        />
                      </FormField>
                      <Button type="submit" disabled={processing}>
                        {processing
                          ? "Checking availability…"
                          : space.requiresApproval
                            ? "Request reservation"
                            : "Reserve room"}
                      </Button>
                    </>
                  )}
                </Form>
              </SurfaceCardContent>
            </SurfaceCard>

            <aside
              className="grid content-start gap-4"
              aria-label="Reservation summary"
            >
              <SurfaceCard>
                <SurfaceCardContent className="grid gap-4 text-sm">
                  <div>
                    <h2 className="text-base font-semibold">{space.name}</h2>
                    <p className="text-muted-foreground">{space.typeLabel}</p>
                  </div>
                  <div className="grid gap-3">
                    <div className="flex gap-3">
                      <Clock3
                        className="text-muted-foreground mt-0.5 size-4"
                        aria-hidden
                      />
                      <dl>
                        <dt className="text-muted-foreground">Starts</dt>
                        <dd>{dateTimeLabel(draft.startsAt, office.timezone)}</dd>
                      </dl>
                    </div>
                    <div className="flex gap-3">
                      <Clock3
                        className="text-muted-foreground mt-0.5 size-4"
                        aria-hidden
                      />
                      <dl>
                        <dt className="text-muted-foreground">Ends</dt>
                        <dd>{dateTimeLabel(draft.endsAt, office.timezone)}</dd>
                      </dl>
                    </div>
                    <div className="flex gap-3">
                      <Users
                        className="text-muted-foreground mt-0.5 size-4"
                        aria-hidden
                      />
                      <dl>
                        <dt className="text-muted-foreground">Capacity</dt>
                        <dd>{space.capacity} people</dd>
                      </dl>
                    </div>
                    {space.location ? (
                      <div className="flex gap-3">
                        <MapPin
                          className="text-muted-foreground mt-0.5 size-4"
                          aria-hidden
                        />
                        <dl>
                          <dt className="text-muted-foreground">Location</dt>
                          <dd>{space.location}</dd>
                        </dl>
                      </div>
                    ) : null}
                  </div>
                </SurfaceCardContent>
              </SurfaceCard>
              <Callout title="Final availability check">
                The calendar is advisory. Submitting checks office hours, notice,
                duration, buffers, maintenance blocks, and competing reservations in one
                transaction.
              </Callout>
            </aside>
          </div>
        )}
      </div>
    </PermissionRequired>
  );
}

RoomReservationNew.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reserve room",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Room availability", href: routes.room_availability() },
          { label: "Reserve" },
        ],
      },
    },
  ] as const;
