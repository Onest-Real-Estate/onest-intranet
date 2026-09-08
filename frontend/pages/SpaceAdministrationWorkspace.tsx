import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Archive,
  ArrowLeftRight,
  CalendarClock,
  CalendarOff,
  ChevronLeft,
  CircleSlash,
  Plus,
  Power,
  Trash2,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useState } from "react";

import { RoomScheduleEditor } from "@/components/administration/RoomScheduleEditor";
import {
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  PageHeader,
  PanelHeader,
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
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type {
  SpaceAdminBlock,
  SpaceAdminBooking,
  SpaceAdministrationWorkspacePageProps,
  SpaceScheduleInterval,
} from "@/types";

const VIEW = { all: ["reservations.view_spaces"] };

const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function fieldErrors(errors: { fields: Record<string, string[]> }, key: string) {
  return errors.fields[key];
}

function useDateTimeFormat(timeZone?: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
}

function SpaceAdministrationWorkspacePage() {
  const {
    space,
    schedule,
    blocks,
    upcomingBookings,
    moveTargets,
    options,
    capabilities,
    impact,
    errors,
    links,
  } = usePage<SpaceAdministrationWorkspacePageProps>().props;

  const [saving, setSaving] = useState(false);
  const [addingBlock, setAddingBlock] = useState(false);
  const [moving, setMoving] = useState<SpaceAdminBooking | null>(null);
  const [cancelling, setCancelling] = useState<SpaceAdminBooking | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [retiring, setRetiring] = useState(false);
  // Held so "Apply anyway" can replay the exact edit the server refused.
  const [pendingImpact, setPendingImpact] = useState<Record<
    string,
    string | number | boolean
  > | null>(null);
  const formatter = useDateTimeFormat();

  const isRetired = space.status === "retired";
  const readOnly = isRetired || !capabilities.canManageSpaces;

  /** Payload type borrowed from the router so it cannot drift from Inertia's. */
  type Payload = Parameters<typeof router.post>[1];

  function post(url: string, data: Payload, options_?: object) {
    router.post(url, data, {
      preserveScroll: true,
      onStart: () => setSaving(true),
      onFinish: () => setSaving(false),
      ...options_,
    });
  }

  function submitDetails(event: React.FormEvent<HTMLFormElement>, ack = false) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      name: String(data.get("name") ?? ""),
      spaceType: String(data.get("spaceType") ?? ""),
      capacity: Number(data.get("capacity") ?? 0),
      description: String(data.get("description") ?? ""),
      location: String(data.get("location") ?? ""),
      accessInstructions: String(data.get("accessInstructions") ?? ""),
      displayOrder: Number(data.get("displayOrder") ?? 0),
      minimumDurationMinutes: Number(data.get("minimumDurationMinutes") ?? 0),
      maximumDurationMinutes: Number(data.get("maximumDurationMinutes") ?? 0),
      bookingHorizonDays: Number(data.get("bookingHorizonDays") ?? 0),
      minimumNoticeMinutes: Number(data.get("minimumNoticeMinutes") ?? 0),
      bufferBeforeMinutes: Number(data.get("bufferBeforeMinutes") ?? 0),
      bufferAfterMinutes: Number(data.get("bufferAfterMinutes") ?? 0),
      cancellationCutoffMinutes: Number(data.get("cancellationCutoffMinutes") ?? 0),
      requiresApproval: data.get("requiresApproval") === "on",
      isReservable: data.get("isReservable") === "on",
      expectedUpdatedAt: space.updatedAt,
      acknowledgeImpact: ack,
    };
    setPendingImpact(payload);
    post(routes.space_administration_update(space.publicId), payload);
  }

  return (
    // `@container` is what makes every `@*:` variant below work: the panels
    // size themselves to this column, not to the window behind the sidebar.
    <div className="@container grid gap-6">
      <Head title={`${space.name} · Rooms`} />

      <PageHeader
        title={space.name}
        description={`${space.spaceTypeLabel} · ${space.officeName}`}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              status={{
                label: isRetired
                  ? "Retired"
                  : space.policy.isReservable
                    ? "Bookable"
                    : "Not bookable",
                tone: isRetired
                  ? "neutral"
                  : space.policy.isReservable
                    ? "success"
                    : "warning",
              }}
            />
            <Badge variant="outline">
              <Users className="size-3" aria-hidden />
              {space.capacity} seats
            </Badge>
            {space.location ? (
              <span className="text-muted-foreground text-sm">{space.location}</span>
            ) : null}
          </div>
        }
        actions={
          <Button asChild variant="outline">
            <Link href={links.indexHref}>
              <ChevronLeft className="size-4" aria-hidden />
              All rooms
            </Link>
          </Button>
        }
      />

      <FormErrorSummary errors={errors} />

      {isRetired ? (
        <Callout tone="neutral" icon={Archive} title="This room is retired">
          Its identity, schedule, and booking history are preserved for audit. Retired
          rooms cannot be edited or reactivated.
        </Callout>
      ) : null}

      {impact ? (
        <Callout
          tone="warning"
          icon={TriangleAlert}
          title={`${impact.total} future booking${impact.total === 1 ? "" : "s"} would be affected`}
        >
          <p className="mb-3">
            Nothing has been saved. Review the bookings below, then confirm to apply the
            change anyway — the people who own them are notified.
          </p>
          <ul className="mb-3 grid gap-1.5">
            {impact.bookings.map((booking) => (
              <li
                key={booking.publicId}
                className="border-border bg-card flex flex-wrap items-center justify-between gap-2 rounded-sm border px-2 py-1.5 text-sm"
              >
                <span className="font-medium">{booking.reference}</span>
                <span className="text-muted-foreground">{booking.ownerName}</span>
                <span className="text-muted-foreground tabular-nums">
                  {formatter.format(new Date(booking.startsAt))}
                </span>
                <span className="text-warning-ink">{booking.reason}</span>
              </li>
            ))}
          </ul>
          {pendingImpact ? (
            <Button
              type="button"
              disabled={saving}
              onClick={() =>
                post(routes.space_administration_update(space.publicId), {
                  ...pendingImpact,
                  acknowledgeImpact: true,
                })
              }
            >
              Apply anyway
            </Button>
          ) : null}
        </Callout>
      ) : null}

      <div className="grid items-start gap-6 @4xl:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
        <div className="@container grid min-w-0 gap-6">
          {/* Identity and policy save together: both are "what this room is". */}
          <SurfaceCard>
            <PanelHeader
              title="Identity and policy"
              description="Booking limits are re-checked against live bookings before they save."
              divided
            />
            <SurfaceCardContent>
              <form className="grid gap-5" onSubmit={(event) => submitDetails(event)}>
                <div className="grid gap-4 @lg:grid-cols-2">
                  <FormField>
                    <FormLabel htmlFor="room-name">Name</FormLabel>
                    <Input
                      id="room-name"
                      name="name"
                      defaultValue={space.name}
                      maxLength={200}
                      required
                      disabled={readOnly}
                    />
                    <FormFieldError messages={fieldErrors(errors, "name")} />
                  </FormField>
                  <FormField>
                    <FormLabel htmlFor="room-type">Room type</FormLabel>
                    <NativeSelect
                      id="room-type"
                      name="spaceType"
                      defaultValue={space.spaceType}
                      disabled={readOnly}
                    >
                      {options.spaceTypes.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </NativeSelect>
                  </FormField>
                  <FormField>
                    <FormLabel htmlFor="room-capacity">Seats</FormLabel>
                    <Input
                      id="room-capacity"
                      name="capacity"
                      type="number"
                      min={1}
                      defaultValue={space.capacity}
                      required
                      disabled={readOnly}
                    />
                    <FormFieldError messages={fieldErrors(errors, "capacity")} />
                  </FormField>
                  <FormField>
                    <FormLabel htmlFor="room-order">Sort order</FormLabel>
                    <Input
                      id="room-order"
                      name="displayOrder"
                      type="number"
                      min={0}
                      defaultValue={space.displayOrder}
                      disabled={readOnly}
                    />
                  </FormField>
                  <FormField className="@lg:col-span-2">
                    <FormLabel htmlFor="room-location">Location</FormLabel>
                    <Input
                      id="room-location"
                      name="location"
                      defaultValue={space.location}
                      maxLength={240}
                      disabled={readOnly}
                    />
                  </FormField>
                  <FormField className="@lg:col-span-2">
                    <FormLabel htmlFor="room-description">Description</FormLabel>
                    <Textarea
                      id="room-description"
                      name="description"
                      defaultValue={space.description}
                      rows={3}
                      disabled={readOnly}
                    />
                  </FormField>
                  {capabilities.canViewSensitive ? (
                    <FormField className="@lg:col-span-2">
                      <FormLabel htmlFor="room-access">Access instructions</FormLabel>
                      <Textarea
                        id="room-access"
                        name="accessInstructions"
                        defaultValue={space.accessInstructions}
                        rows={2}
                        disabled={readOnly}
                      />
                      <p className="text-muted-foreground text-xs">
                        Shown only to people who may see sensitive room details.
                      </p>
                    </FormField>
                  ) : null}
                </div>

                <div className="border-border border-t pt-5">
                  <h3 className="text-foreground mb-4 text-base font-semibold">
                    Booking limits
                  </h3>
                  <div className="grid gap-4 @md:grid-cols-2 @3xl:grid-cols-3">
                    {(
                      [
                        ["minimumDurationMinutes", "Minimum minutes"],
                        ["maximumDurationMinutes", "Maximum minutes"],
                        ["bookingHorizonDays", "Horizon (days)"],
                        ["minimumNoticeMinutes", "Notice (minutes)"],
                        ["bufferBeforeMinutes", "Buffer before"],
                        ["bufferAfterMinutes", "Buffer after"],
                        ["cancellationCutoffMinutes", "Cancel cutoff"],
                      ] as const
                    ).map(([key, label]) => (
                      <FormField key={key}>
                        <FormLabel htmlFor={`room-${key}`}>{label}</FormLabel>
                        <Input
                          id={`room-${key}`}
                          name={key}
                          type="number"
                          min={0}
                          defaultValue={space.policy[key]}
                          disabled={readOnly}
                        />
                        <FormFieldError messages={fieldErrors(errors, key)} />
                      </FormField>
                    ))}
                  </div>
                  <div className="border-border mt-5 grid gap-3 border-t pt-5">
                    <label
                      className="flex items-center gap-2 text-sm"
                      htmlFor="room-approval"
                    >
                      <Checkbox
                        id="room-approval"
                        name="requiresApproval"
                        defaultChecked={space.policy.requiresApproval}
                        disabled={readOnly}
                      />
                      Bookings need approval before they are confirmed
                    </label>
                    <label
                      className="flex items-center gap-2 text-sm"
                      htmlFor="room-bookable"
                    >
                      <Checkbox
                        id="room-bookable"
                        name="isReservable"
                        defaultChecked={space.policy.isReservable}
                        disabled={readOnly}
                      />
                      Accepting new bookings
                    </label>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button type="submit" disabled={readOnly || saving}>
                    {saving ? "Saving…" : "Save room"}
                  </Button>
                </div>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              title="Weekly hours"
              description={`Wall-clock hours in ${space.officeName}'s timezone.`}
              divided
            />
            <SurfaceCardContent>
              {capabilities.canManageSchedules && !isRetired ? (
                <RoomScheduleEditor
                  schedule={schedule}
                  saving={saving}
                  error={fieldErrors(errors, "schedule")?.[0]}
                  onSave={(intervals: SpaceScheduleInterval[]) =>
                    // Sent as one JSON string: a QueryDict holds strings, so an
                    // array of objects would arrive flattened. The view accepts
                    // either shape; this one keeps the payload readable.
                    post(routes.space_administration_schedule(space.publicId), {
                      intervals: JSON.stringify(intervals),
                    })
                  }
                />
              ) : (
                <ReadOnlySchedule schedule={schedule} />
              )}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              title="Maintenance and closures"
              description="Blocks hold the room's time the same way a booking does."
              divided
              action={
                capabilities.canManageSchedules && !isRetired ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setAddingBlock(true)}
                  >
                    <Plus className="size-4" aria-hidden />
                    Add block
                  </Button>
                ) : undefined
              }
            />
            <SurfaceCardContent>
              {blocks.length === 0 ? (
                <p className="text-muted-foreground text-sm">No upcoming blocks.</p>
              ) : (
                <ul className="grid gap-2">
                  {blocks.map((block) => (
                    <BlockRow
                      key={block.publicId}
                      block={block}
                      formatter={formatter}
                      canManage={capabilities.canManageSchedules && !isRetired}
                      disabled={saving}
                      onRemove={() =>
                        post(
                          routes.space_administration_block_delete(block.publicId),
                          {},
                        )
                      }
                    />
                  ))}
                </ul>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        </div>

        <div className="@container grid min-w-0 gap-6">
          <SurfaceCard>
            <PanelHeader
              title="Upcoming bookings"
              description="Purpose and attendees stay private to the booker."
            />
            <SurfaceCardContent>
              {upcomingBookings.length === 0 ? (
                <p className="text-muted-foreground text-sm">Nothing booked ahead.</p>
              ) : (
                <ul className="grid gap-2">
                  {upcomingBookings.map((booking) => (
                    <li
                      key={booking.publicId}
                      className="border-border rounded-md border p-3"
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="text-foreground text-sm font-semibold">
                          {booking.reference}
                        </span>
                        <StatusBadge
                          status={{
                            label: booking.statusLabel,
                            tone: booking.status === "confirmed" ? "success" : "info",
                          }}
                        />
                      </div>
                      <p className="text-muted-foreground mt-1 text-sm">
                        {booking.ownerName}
                      </p>
                      <p className="text-muted-foreground text-sm tabular-nums">
                        {formatter.format(new Date(booking.startsAt))}
                      </p>
                      {capabilities.canManageReservations && !isRetired ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {moveTargets.length ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => setMoving(booking)}
                            >
                              <ArrowLeftRight className="size-3.5" aria-hidden />
                              Move
                            </Button>
                          ) : null}
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => setCancelling(booking)}
                          >
                            <CircleSlash className="size-3.5" aria-hidden />
                            Cancel
                          </Button>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </SurfaceCardContent>
          </SurfaceCard>

          {capabilities.canManageSpaces && !isRetired ? (
            <SurfaceCard>
              <PanelHeader
                title="Lifecycle"
                description="Deactivating hides the room from booking; retiring is permanent."
              />
              <SurfaceCardContent className="grid gap-2">
                {space.policy.isReservable ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setDeactivating(true)}
                  >
                    <Power className="size-4" aria-hidden />
                    Deactivate room
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={saving}
                    onClick={() =>
                      post(routes.space_administration_activation(space.publicId), {
                        active: true,
                      })
                    }
                  >
                    <Power className="size-4" aria-hidden />
                    Reactivate room
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  className="text-destructive"
                  onClick={() => setRetiring(true)}
                >
                  <Archive className="size-4" aria-hidden />
                  Retire room
                </Button>
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
        </div>
      </div>

      <ReasonDialog
        open={deactivating}
        onOpenChange={setDeactivating}
        title="Deactivate this room"
        description="It stops accepting new bookings. Existing bookings are listed for review before the change applies."
        confirmLabel="Deactivate"
        saving={saving}
        onConfirm={(reason) =>
          post(routes.space_administration_activation(space.publicId), {
            active: false,
            reason,
          })
        }
      />

      <ReasonDialog
        open={retiring}
        onOpenChange={setRetiring}
        title="Retire this room"
        description="Retirement is permanent. History is preserved, but the room cannot be reactivated."
        confirmLabel="Retire room"
        destructive
        saving={saving}
        onConfirm={(reason) =>
          post(routes.space_administration_retire(space.publicId), { reason })
        }
      />

      <ReasonDialog
        open={Boolean(cancelling)}
        onOpenChange={(open) => !open && setCancelling(null)}
        title={`Cancel ${cancelling?.reference ?? "booking"}`}
        description={`${cancelling?.ownerName ?? "The booker"} is notified with your reason.`}
        confirmLabel="Cancel booking"
        destructive
        saving={saving}
        onConfirm={(reason) => {
          if (!cancelling) return;
          post(
            routes.space_administration_booking_cancel(cancelling.publicId),
            { reason },
            { onSuccess: () => setCancelling(null) },
          );
        }}
      />

      <MoveDialog
        booking={moving}
        targets={moveTargets}
        saving={saving}
        errors={errors}
        onOpenChange={(open) => !open && setMoving(null)}
        onConfirm={(destination, reason) => {
          if (!moving) return;
          post(routes.space_administration_booking_move(moving.publicId), {
            destination,
            reason,
          });
        }}
      />

      <BlockDialog
        open={addingBlock}
        onOpenChange={setAddingBlock}
        options={options}
        saving={saving}
        errors={errors}
        onConfirm={(payload) =>
          post(routes.space_administration_block_create(space.publicId), payload)
        }
      />
    </div>
  );
}

function ReadOnlySchedule({ schedule }: { schedule: SpaceScheduleInterval[] }) {
  if (schedule.length === 0) {
    return <p className="text-muted-foreground text-sm">Closed every day.</p>;
  }
  return (
    <dl className="grid gap-1.5">
      {schedule.map((item) => (
        <div
          key={`${item.weekday}-${item.startsAt}`}
          className="flex items-baseline justify-between gap-4 text-sm"
        >
          <dt className="text-foreground font-medium">{WEEKDAYS[item.weekday]}</dt>
          <dd className="text-muted-foreground tabular-nums">
            {item.startsAt.slice(0, 5)}–{item.endsAt.slice(0, 5)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function BlockRow({
  block,
  formatter,
  canManage,
  disabled,
  onRemove,
}: {
  block: SpaceAdminBlock;
  formatter: Intl.DateTimeFormat;
  canManage: boolean;
  disabled: boolean;
  onRemove: () => void;
}) {
  return (
    <li className="border-border flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
      <div className="grid gap-0.5">
        <div className="flex items-center gap-2">
          <CalendarOff className="text-muted-foreground size-3.5" aria-hidden />
          <span className="text-foreground text-sm font-medium">{block.reason}</span>
          <Badge variant="secondary">{block.kindLabel}</Badge>
        </div>
        <span className="text-muted-foreground text-sm tabular-nums">
          {formatter.format(new Date(block.startsAt))} –{" "}
          {formatter.format(new Date(block.endsAt))}
        </span>
      </div>
      {canManage ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={onRemove}
          aria-label={`Remove block: ${block.reason}`}
        >
          <Trash2 className="size-4" aria-hidden />
          Remove
        </Button>
      ) : null}
    </li>
  );
}

function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  saving,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  saving: boolean;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <FormField>
          <FormLabel htmlFor="reason-field">Reason</FormLabel>
          <Textarea
            id="reason-field"
            rows={3}
            value={reason}
            required
            onChange={(event) => setReason(event.target.value)}
            placeholder="Recorded in the audit trail and sent to anyone affected."
          />
        </FormField>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Keep as is
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            disabled={saving || reason.trim().length === 0}
            onClick={() => onConfirm(reason)}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MoveDialog({
  booking,
  targets,
  saving,
  errors,
  onOpenChange,
  onConfirm,
}: {
  booking: SpaceAdminBooking | null;
  targets: { value: string; label: string; capacity: number }[];
  saving: boolean;
  errors: { fields: Record<string, string[]> };
  onOpenChange: (open: boolean) => void;
  onConfirm: (destination: string, reason: string) => void;
}) {
  const [destination, setDestination] = useState("");
  const [reason, setReason] = useState("");
  return (
    <Dialog open={Boolean(booking)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move {booking?.reference}</DialogTitle>
          <DialogDescription>
            The destination is re-checked for the same time, its own opening hours, and
            capacity before the move applies.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormField>
            <FormLabel htmlFor="move-destination">Destination room</FormLabel>
            <NativeSelect
              id="move-destination"
              value={destination}
              onChange={(event) => setDestination(event.target.value)}
            >
              <option value="">Choose a room</option>
              {targets.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label} · {item.capacity} seats
                </option>
              ))}
            </NativeSelect>
            <FormFieldError messages={errors.fields.destination} />
          </FormField>
          <FormField>
            <FormLabel htmlFor="move-reason">Reason</FormLabel>
            <Textarea
              id="move-reason"
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </FormField>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Keep as is
          </Button>
          <Button
            type="button"
            disabled={saving || !destination || reason.trim().length === 0}
            onClick={() => onConfirm(destination, reason)}
          >
            Move booking
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BlockDialog({
  open,
  onOpenChange,
  options,
  saving,
  errors,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  options: SpaceAdministrationWorkspacePageProps["options"];
  saving: boolean;
  errors: { fields: Record<string, string[]> };
  onConfirm: (payload: Record<string, string>) => void;
}) {
  const [kind, setKind] = useState(options.blockKinds[0]?.value ?? "maintenance");
  const [visibility, setVisibility] = useState(
    options.visibilities[0]?.value ?? "internal",
  );
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [reason, setReason] = useState("");

  const complete = startsAt && endsAt && reason.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a block</DialogTitle>
          <DialogDescription>
            A block holds the room's time like a booking does, so it cannot land on one
            that already exists.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField>
              <FormLabel htmlFor="block-kind">Kind</FormLabel>
              <NativeSelect
                id="block-kind"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                {options.blockKinds.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField>
              <FormLabel htmlFor="block-visibility">Visibility</FormLabel>
              <NativeSelect
                id="block-visibility"
                value={visibility}
                onChange={(event) => setVisibility(event.target.value)}
              >
                {options.visibilities.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField>
              <FormLabel htmlFor="block-start">Starts</FormLabel>
              <Input
                id="block-start"
                type="datetime-local"
                value={startsAt}
                onChange={(event) => setStartsAt(event.target.value)}
              />
              <FormFieldError messages={errors.fields.startsAt} />
            </FormField>
            <FormField>
              <FormLabel htmlFor="block-end">Ends</FormLabel>
              <Input
                id="block-end"
                type="datetime-local"
                value={endsAt}
                onChange={(event) => setEndsAt(event.target.value)}
              />
              <FormFieldError messages={errors.fields.endsAt} />
            </FormField>
          </div>
          <FormField>
            <FormLabel htmlFor="block-reason">Reason</FormLabel>
            <Input
              id="block-reason"
              value={reason}
              maxLength={240}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Alarm panel service"
            />
          </FormField>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={saving || !complete}
            onClick={() => onConfirm({ kind, visibility, startsAt, endsAt, reason })}
          >
            <CalendarClock className="size-4" aria-hidden />
            Add block
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function SpaceAdministrationWorkspace() {
  return (
    <PermissionRequired permission={VIEW}>
      <SpaceAdministrationWorkspacePage />
    </PermissionRequired>
  );
}

SpaceAdministrationWorkspace.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Room",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Rooms", href: routes.space_administration() },
          { label: "Room" },
        ],
      },
    },
  ] as const;
