import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Building2,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Clock3,
  DoorClosed,
  DoorOpen,
  List,
  Rows3,
  Users,
} from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
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
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  RoomAvailabilityPageProps,
  RoomCalendarDay,
  RoomCalendarSlot,
  RoomCalendarSpace,
  RoomCalendarView,
} from "@/types";

const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function dateLabel(value: string) {
  return DATE_FORMAT.format(new Date(`${value}T12:00:00Z`));
}

function addDays(value: string, amount: number) {
  const next = new Date(`${value}T12:00:00Z`);
  next.setUTCDate(next.getUTCDate() + amount);
  return next.toISOString().slice(0, 10);
}

function timeLabel(value: string, timeZone: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(value));
}

function intervalLabel(
  interval: { startsAt: string; endsAt: string },
  timeZone: string,
) {
  return `${timeLabel(interval.startsAt, timeZone)}–${timeLabel(
    interval.endsAt,
    timeZone,
  )}`;
}

function SlotLink({ slot, timeZone }: { slot: RoomCalendarSlot; timeZone: string }) {
  return (
    <Button asChild variant="outline" size="sm" className="justify-start">
      <Link href={slot.bookingHref}>
        <Clock3 className="size-3.5" aria-hidden />
        {intervalLabel(slot, timeZone)}
      </Link>
    </Button>
  );
}

function DayAvailability({
  day,
  timeZone,
}: {
  day: RoomCalendarDay;
  timeZone: string;
}) {
  return (
    <div className="grid gap-3">
      {day.isClosed ? (
        <p className="text-foreground flex items-center gap-2 text-sm font-semibold">
          <DoorClosed className="size-4" aria-hidden />
          Closed
        </p>
      ) : (
        <div>
          <p className="text-foreground flex items-center gap-1.5 text-sm font-semibold">
            <DoorOpen className="size-3.5" aria-hidden />
            Open
          </p>
          <p className="text-muted-foreground text-sm tabular-nums">
            {day.openIntervals.map((item) => intervalLabel(item, timeZone)).join(", ")}
          </p>
        </div>
      )}
      {day.busyIntervals.length ? (
        <div>
          <p className="text-muted-foreground mb-1 text-xs font-semibold">
            Unavailable
          </p>
          <ul className="grid gap-1">
            {day.busyIntervals.map((item) => (
              <li
                key={`${item.startsAt}-${item.endsAt}`}
                className="bg-muted border-border flex items-center justify-between gap-2 rounded-sm border px-2 py-1 text-xs"
              >
                <span>{item.label}</span>
                <span className="text-muted-foreground tabular-nums">
                  {intervalLabel(item, timeZone)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {!day.isClosed ? (
        <div>
          <p className="text-muted-foreground mb-1.5 text-xs font-semibold">
            Select a start time
          </p>
          {day.candidateSlots.length ? (
            <div className="flex max-h-44 flex-col gap-1.5 overflow-y-auto pr-1">
              {day.candidateSlots.map((slot) => (
                <SlotLink
                  key={`${slot.startsAt}-${slot.endsAt}`}
                  slot={slot}
                  timeZone={timeZone}
                />
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">No valid starts</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function SpaceIdentity({ space }: { space: RoomCalendarSpace }) {
  return (
    <div className="grid gap-2">
      <div>
        <h2 className="text-foreground font-semibold">{space.name}</h2>
        <p className="text-muted-foreground text-sm">
          {space.typeLabel}
          {space.location ? ` · ${space.location}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">
          <Users className="size-3" aria-hidden />
          {space.capacity}
        </Badge>
        {space.amenities.slice(0, 3).map((amenity) => (
          <Badge key={amenity.code} variant="secondary">
            {amenity.name}
          </Badge>
        ))}
      </div>
      <p className="text-muted-foreground text-xs">
        {space.rules.minimumDurationMinutes} min minimum
        {space.rules.bufferAfterMinutes
          ? ` · ${space.rules.bufferAfterMinutes} min cleanup`
          : ""}
        {space.rules.requiresApproval ? " · Approval required" : ""}
      </p>
    </div>
  );
}

function CalendarTable({
  spaces,
  dates,
  timeZone,
}: {
  spaces: RoomCalendarSpace[];
  dates: string[];
  timeZone: string;
}) {
  return (
    <section
      className="border-border @container w-full min-w-0 max-w-full overflow-x-auto rounded-lg border"
      aria-label="Room availability calendar"
    >
      <table className="w-full min-w-max border-collapse text-left">
        <thead className="bg-muted">
          <tr>
            <th className="border-border sticky left-0 z-10 w-36 min-w-36 border-r px-3 py-3 text-xs font-semibold tracking-[0.06em] uppercase @sm:w-48 @sm:min-w-48 @3xl:w-64 @3xl:min-w-64 @sm:px-4">
              Room
            </th>
            {dates.map((item) => (
              <th
                key={item}
                scope="col"
                className="border-border min-w-44 border-r px-3 py-3 text-xs font-semibold tracking-[0.06em] uppercase last:border-r-0 @sm:min-w-48 @3xl:min-w-52"
              >
                {dateLabel(item)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spaces.map((space) => (
            <tr key={space.publicId} className="border-border border-t align-top">
              <th
                scope="row"
                className="bg-card border-border sticky left-0 z-10 w-36 min-w-36 border-r px-3 py-4 @sm:w-48 @sm:min-w-48 @3xl:w-64 @3xl:min-w-64 @sm:px-4"
              >
                <SpaceIdentity space={space} />
              </th>
              {space.days.map((day) => (
                <td
                  key={day.date}
                  className="border-border min-w-44 border-r p-3 last:border-r-0 @sm:min-w-48 @3xl:min-w-52"
                >
                  <DayAvailability day={day} timeZone={timeZone} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AgendaList({
  spaces,
  dates,
  timeZone,
}: {
  spaces: RoomCalendarSpace[];
  dates: string[];
  timeZone: string;
}) {
  return (
    <div className="divide-border border-border divide-y rounded-lg border">
      {dates.map((date) => (
        <section key={date} aria-labelledby={`agenda-${date}`} className="p-4">
          <h2 id={`agenda-${date}`} className="mb-4 text-base font-semibold">
            {dateLabel(date)}
          </h2>
          <div className="grid gap-5">
            {spaces.map((space) => {
              const day = space.days.find((item) => item.date === date);
              if (!day) return null;
              return (
                <article
                  key={space.publicId}
                  className="grid gap-3 sm:grid-cols-[minmax(12rem,18rem)_minmax(0,1fr)]"
                >
                  <SpaceIdentity space={space} />
                  <DayAvailability day={day} timeZone={timeZone} />
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function RoomAvailability() {
  const {
    calendar,
    office,
    officeOptions,
    filterOptions,
    filters,
    capabilities,
    empty,
    errors,
  } = usePage<RoomAvailabilityPageProps>().props;
  const [loading, setLoading] = useState(false);

  function visit(next: Partial<RoomAvailabilityPageProps["filters"]>) {
    const merged = { ...filters, ...next };
    const params = new URLSearchParams();
    if (merged.date) params.set("date", merged.date);
    if (merged.view) params.set("view", merged.view);
    if (merged.office) params.set("office", merged.office);
    if (merged.type) params.set("type", merged.type);
    if (merged.capacity) params.set("capacity", merged.capacity);
    if (merged.amenities.length) params.set("amenities", merged.amenities.join(","));
    if (merged.space) params.set("space", merged.space);
    router.get(
      `${routes.room_availability()}?${params.toString()}`,
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

  const activeFilterCount = [
    filters.office,
    filters.type,
    filters.capacity,
    filters.space,
    ...filters.amenities,
  ].filter(Boolean).length;
  const step = filters.view === "day" ? 1 : 7;
  const dates = calendar?.days.map((item) => item.date) ?? [];

  return (
    <PermissionRequired permission={{ all: ["reservations.book_spaces"] }}>
      <div className="grid w-full min-w-0 max-w-[calc(100vw-2.5rem)] gap-6 overflow-x-hidden sm:max-w-full">
        <Head title="Room availability" />
        <PageHeader
          title="Room availability"
          description="Choose a valid office-local start time. Every reservation is checked again when submitted."
          meta={
            office ? (
              <span className="text-muted-foreground text-sm">
                {office.name} · {office.timezone}
              </span>
            ) : undefined
          }
        />

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label={`Previous ${step === 1 ? "day" : "week"}`}
                  onClick={() => visit({ date: addDays(filters.date, -step) })}
                  disabled={loading}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <FilterField label="Starting date">
                  <Input
                    type="date"
                    aria-label="Starting date"
                    value={filters.date}
                    onChange={(event) => visit({ date: event.target.value })}
                    disabled={loading}
                  />
                </FilterField>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label={`Next ${step === 1 ? "day" : "week"}`}
                  onClick={() => visit({ date: addDays(filters.date, step) })}
                  disabled={loading}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
              <fieldset className="flex items-center gap-1 border-0 p-0">
                <legend className="sr-only">Calendar view</legend>
                {(["day", "week", "list"] as RoomCalendarView[]).map((view) => (
                  <Button
                    key={view}
                    type="button"
                    size="sm"
                    variant={filters.view === view ? "secondary" : "ghost"}
                    aria-pressed={filters.view === view}
                    onClick={() => visit({ view })}
                    disabled={loading}
                  >
                    {view === "list" ? (
                      <List className="size-4" aria-hidden />
                    ) : (
                      <Rows3 className="size-4" aria-hidden />
                    )}
                    {view[0].toUpperCase() + view.slice(1)}
                  </Button>
                ))}
              </fieldset>
              <FilterControls
                activeCount={activeFilterCount}
                disabled={loading}
                className="basis-full lg:basis-auto lg:has-[button[aria-expanded=true]]:basis-full"
                onReset={() =>
                  visit({
                    office: "",
                    type: "",
                    capacity: "",
                    amenities: [],
                    space: "",
                  })
                }
              >
                {capabilities.canChangeOffice ? (
                  <FilterField label="Office">
                    <NativeSelect
                      aria-label="Office"
                      value={office?.key ?? ""}
                      onChange={(event) => visit({ office: event.target.value })}
                    >
                      {officeOptions.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.name} · {item.regionName}
                        </option>
                      ))}
                    </NativeSelect>
                  </FilterField>
                ) : null}
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
                <FilterField label="Minimum capacity">
                  <Input
                    type="number"
                    aria-label="Minimum capacity"
                    min={1}
                    value={filters.capacity}
                    onChange={(event) => visit({ capacity: event.target.value })}
                    className="w-28"
                  />
                </FilterField>
                <FilterField label="Specific room">
                  <NativeSelect
                    aria-label="Specific room"
                    value={filters.space}
                    onChange={(event) => visit({ space: event.target.value })}
                  >
                    <option value="">Any room</option>
                    {filterOptions.rooms.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </NativeSelect>
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
                                  ? filters.amenities.filter(
                                      (value) => value !== item.value,
                                    )
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
            </div>
          </SurfaceCardContent>
        </SurfaceCard>

        {errors.form.length || Object.keys(errors.fields).length ? (
          <div
            role="alert"
            className="border-destructive text-destructive rounded-md border px-4 py-3 text-sm"
          >
            Check the date or filters and try again.
          </div>
        ) : null}

        <div className="sr-only" aria-live="polite">
          {loading ? "Loading room availability" : "Room availability loaded"}
        </div>

        {empty?.kind === "no-office" ? (
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
        ) : empty ? (
          <SurfaceCard>
            <EmptyState
              icon={CalendarClock}
              title={empty.title}
              description={empty.description}
              actions={
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    visit({ type: "", capacity: "", amenities: [], space: "" })
                  }
                >
                  Clear filters
                </Button>
              }
            />
          </SurfaceCard>
        ) : calendar ? (
          <section
            aria-busy={loading}
            className={cn("min-w-0", loading && "opacity-60")}
          >
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-muted-foreground text-sm">{calendar.advisory}</p>
              <StatusBadge
                status={{
                  label: `Times shown in ${calendar.timezone}`,
                  tone: "neutral",
                }}
              />
            </div>
            {calendar.isTruncated ? (
              <p className="text-muted-foreground mb-3 text-sm">
                Showing the first 50 rooms. Narrow the filters to see a specific room.
              </p>
            ) : null}
            {filters.view === "list" ? (
              <AgendaList
                spaces={calendar.spaces}
                dates={dates}
                timeZone={calendar.timezone}
              />
            ) : (
              <CalendarTable
                spaces={calendar.spaces}
                dates={dates}
                timeZone={calendar.timezone}
              />
            )}
          </section>
        ) : null}
      </div>
    </PermissionRequired>
  );
}

RoomAvailability.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Room availability",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Room availability" },
        ],
      },
    },
  ] as const;
