import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Building2,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  DoorClosed,
  DoorOpen,
  List,
  Sparkles,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  EmptyState,
  FilterField,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { NativeSelect } from "@/components/design-system/native-select";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { MiniMonthCalendar } from "@/components/reservations/MiniMonthCalendar";
import {
  type CalendarColumn,
  type CalendarEvent,
  RoomCalendarGrid,
} from "@/components/reservations/RoomCalendarGrid";
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

const WEEKDAY_FORMAT = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  timeZone: "UTC",
});

const RANGE_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "long",
  day: "numeric",
  year: "numeric",
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

/**
 * Minutes past local midnight for an instant, read in the office's timezone.
 *
 * The grid is drawn in office wall time, so positions must come from the
 * office's clock rather than the viewer's. `h23` keeps midnight at 0 instead of
 * the 24 that `hour12: false` produces in some engines.
 */
function minutesInZone(iso: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(new Date(iso));
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? "0");
  return hour * 60 + minute;
}

/** An interval that ends exactly at local midnight reads as 0; treat it as 24:00. */
function endMinutesInZone(iso: string, timeZone: string, startMinute: number) {
  const value = minutesInZone(iso, timeZone);
  return value <= startMinute ? 24 * 60 : value;
}

interface GridBounds {
  startHour: number;
  endHour: number;
}

/** Frame the axis on the hours the rooms are actually open, padded by one. */
function gridBounds(spaces: RoomCalendarSpace[], timeZone: string): GridBounds {
  let earliest = Number.POSITIVE_INFINITY;
  let latest = Number.NEGATIVE_INFINITY;
  for (const space of spaces) {
    for (const day of space.days) {
      for (const open of day.openIntervals) {
        const start = minutesInZone(open.startsAt, timeZone);
        earliest = Math.min(earliest, start);
        latest = Math.max(latest, endMinutesInZone(open.endsAt, timeZone, start));
      }
    }
  }
  if (!Number.isFinite(earliest) || !Number.isFinite(latest)) {
    return { startHour: 8, endHour: 18 };
  }
  return {
    startHour: Math.max(Math.floor(earliest / 60) - 1, 0),
    endHour: Math.min(Math.ceil(latest / 60) + 1, 24),
  };
}

function toSlots(day: RoomCalendarDay, timeZone: string) {
  return day.candidateSlots.map((slot: RoomCalendarSlot) => ({
    startsAt: slot.startsAt,
    label: timeLabel(slot.startsAt, timeZone),
    ariaLabel: intervalLabel(slot, timeZone),
    bookingHref: slot.bookingHref,
  }));
}

/**
 * Turn one room-day into positioned blocks.
 *
 * Busy periods come first so an available range drawn beside them never
 * suggests a slot the server would refuse; the candidate starts inside the
 * available block are the authority on what is bookable.
 */
function dayEvents(
  space: RoomCalendarSpace,
  day: RoomCalendarDay,
  timeZone: string,
  startHour: number,
  titlePrefix?: string,
): CalendarEvent[] {
  const offset = startHour * 60;
  const events: CalendarEvent[] = [];

  for (const busy of day.busyIntervals) {
    const start = minutesInZone(busy.startsAt, timeZone);
    events.push({
      id: `${space.publicId}-busy-${busy.startsAt}`,
      kind: busy.isMine ? "mine" : busy.kind === "busy" ? "busy" : "blocked",
      startMinute: start - offset,
      endMinute: endMinutesInZone(busy.endsAt, timeZone, start) - offset,
      title: titlePrefix ? `${titlePrefix} · ${busy.label}` : busy.label,
      timeLabel: intervalLabel(busy, timeZone),
    });
  }

  const slots = toSlots(day, timeZone);
  for (const open of day.availableIntervals) {
    const start = minutesInZone(open.startsAt, timeZone);
    const end = endMinutesInZone(open.endsAt, timeZone, start);
    const inside = slots.filter((slot) => {
      const at = minutesInZone(slot.startsAt, timeZone);
      return at >= start && at < end;
    });
    events.push({
      id: `${space.publicId}-open-${open.startsAt}`,
      kind: "available",
      startMinute: start - offset,
      endMinute: end - offset,
      title: titlePrefix ? `${titlePrefix} · Available` : "Available",
      timeLabel: intervalLabel(open, timeZone),
      slots: inside,
    });
  }
  return events;
}

/** The soonest bookable start across everything on screen. */
function nextOpening(spaces: RoomCalendarSpace[]) {
  let best: { space: RoomCalendarSpace; slot: RoomCalendarSlot } | null = null;
  for (const space of spaces) {
    for (const day of space.days) {
      for (const slot of day.candidateSlots) {
        if (!best || slot.startsAt < best.slot.startsAt) best = { space, slot };
      }
    }
  }
  return best;
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
                <Button
                  key={`${slot.startsAt}-${slot.endsAt}`}
                  asChild
                  variant="outline"
                  size="sm"
                  className="justify-start"
                >
                  <Link href={slot.bookingHref}>
                    <Clock3 className="size-3.5" aria-hidden />
                    {intervalLabel(slot, timeZone)}
                  </Link>
                </Button>
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
  const timeZone = calendar?.timezone ?? "UTC";
  const spaces = calendar?.spaces ?? [];

  const bounds = useMemo(() => gridBounds(spaces, timeZone), [spaces, timeZone]);

  /** Office-local today, from the instant the server generated this payload. */
  const today = useMemo(() => {
    if (!calendar) return filters.date;
    return new Intl.DateTimeFormat("en-CA", { timeZone }).format(
      new Date(calendar.generatedAt),
    );
  }, [calendar, timeZone, filters.date]);

  /**
   * Week view follows one room across the week; day view compares rooms within
   * one day. Laning eight rooms across seven days produces columns too narrow
   * to read, and the two views answer different questions anyway.
   */
  const focused = useMemo(() => {
    if (spaces.length === 0) return null;
    return spaces.find((item) => item.publicId === filters.space) ?? spaces[0];
  }, [spaces, filters.space]);

  /**
   * Day view puts rooms side by side — the question is "which room is free
   * now". Week view puts days side by side and names the room on each block —
   * the question is "when is anything free".
   */
  const columns = useMemo<CalendarColumn[]>(() => {
    if (filters.view === "day") {
      const date = dates[0];
      return spaces.map((space) => {
        const day = space.days.find((item) => item.date === date);
        return {
          id: space.publicId,
          label: space.typeLabel,
          sublabel: space.name,
          isClosed: day?.isClosed,
          events: day ? dayEvents(space, day, timeZone, bounds.startHour) : [],
        };
      });
    }
    return dates.map((date) => {
      const day = focused?.days.find((item) => item.date === date);
      return {
        id: date,
        label: WEEKDAY_FORMAT.format(new Date(`${date}T12:00:00Z`)),
        emphasis: String(Number(date.slice(8, 10))),
        accessibleName: dateLabel(date),
        isToday: date === today,
        isClosed: day?.isClosed,
        events:
          focused && day ? dayEvents(focused, day, timeZone, bounds.startHour) : [],
      };
    });
  }, [filters.view, dates, spaces, focused, today, timeZone, bounds.startHour]);

  const upcoming = useMemo(() => nextOpening(spaces), [spaces]);

  return (
    <PermissionRequired permission={{ all: ["reservations.book_spaces"] }}>
      <div className="@container grid w-full min-w-0 max-w-[calc(100vw-2.5rem)] gap-6 overflow-x-hidden sm:max-w-full">
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
        ) : (
          <div className="grid items-start gap-6 @5xl:grid-cols-[19rem_minmax(0,1fr)]">
            {/* Rail: pick a date, see the next opening, narrow the rooms. */}
            <aside className="@container grid min-w-0 gap-4 @5xl:sticky @5xl:top-4">
              <SurfaceCard>
                <SurfaceCardContent>
                  <MiniMonthCalendar
                    selected={filters.date}
                    today={today}
                    disabled={loading}
                    onSelect={(date) => visit({ date })}
                  />
                </SurfaceCardContent>
              </SurfaceCard>

              {upcoming ? (
                <div className="border-chip-primary-edge bg-chip-primary rounded-[0.625rem] border p-4">
                  <p className="text-primary flex items-center gap-1.5 text-xs font-semibold">
                    <Sparkles className="size-3.5" aria-hidden />
                    Next opening
                  </p>
                  <p
                    className="text-foreground mt-1 truncate text-lg font-bold tracking-[-0.01em]"
                    title={upcoming.space.name}
                  >
                    {upcoming.space.name}
                  </p>
                  <p className="text-muted-foreground mt-1 flex items-center gap-1.5 text-sm tabular-nums">
                    <Clock3 className="size-3.5" aria-hidden />
                    {intervalLabel(upcoming.slot, timeZone)}
                  </p>
                  <Button asChild size="sm" className="mt-4">
                    <Link href={upcoming.slot.bookingHref}>Reserve this slot</Link>
                  </Button>
                </div>
              ) : null}

              <SurfaceCard>
                <SurfaceCardContent className="grid gap-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-foreground text-base font-semibold">Filters</h2>
                    {activeFilterCount ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={loading}
                        onClick={() =>
                          visit({
                            office: "",
                            type: "",
                            capacity: "",
                            amenities: [],
                            space: "",
                          })
                        }
                      >
                        Clear ({activeFilterCount})
                      </Button>
                    ) : null}
                  </div>

                  {capabilities.canChangeOffice ? (
                    <FilterField label="Office">
                      <NativeSelect
                        aria-label="Office"
                        value={office?.key ?? ""}
                        disabled={loading}
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
                      disabled={loading}
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
                  <FilterField label="Specific room">
                    <NativeSelect
                      aria-label="Specific room"
                      value={filters.space}
                      disabled={loading}
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
                  <FilterField label="Minimum capacity">
                    <Input
                      type="number"
                      aria-label="Minimum capacity"
                      min={1}
                      disabled={loading}
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
                </SurfaceCardContent>
              </SurfaceCard>
            </aside>

            <div className="@container grid min-w-0 gap-4">
              <SurfaceCard>
                <SurfaceCardContent className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 py-3">
                  <div className="flex items-center gap-2">
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
                    <p className="text-foreground text-base font-bold tracking-[-0.01em]">
                      {RANGE_FORMAT.format(new Date(`${filters.date}T12:00:00Z`))}
                    </p>
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

                  <div className="ml-auto flex items-center gap-3">
                    <span className="text-muted-foreground hidden text-xs font-semibold @2xl:inline">
                      {calendar?.timezone ?? office?.timezone}
                    </span>
                    <fieldset className="bg-muted flex items-center gap-1 rounded-md border-0 p-1">
                      <legend className="sr-only">Calendar view</legend>
                      {(["day", "week", "list"] as RoomCalendarView[]).map((view) => (
                        <Button
                          key={view}
                          type="button"
                          size="sm"
                          variant={filters.view === view ? "secondary" : "ghost"}
                          aria-pressed={filters.view === view}
                          className={cn(filters.view === view && "shadow-card bg-card")}
                          onClick={() => visit({ view })}
                          disabled={loading}
                        >
                          {view === "list" ? (
                            <List className="size-4" aria-hidden />
                          ) : (
                            <CalendarDays className="size-4" aria-hidden />
                          )}
                          {view[0].toUpperCase() + view.slice(1)}
                        </Button>
                      ))}
                    </fieldset>
                  </div>
                </SurfaceCardContent>
              </SurfaceCard>

              {empty ? (
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
                  className={cn("grid min-w-0 gap-3", loading && "opacity-60")}
                >
                  {calendar.isTruncated ? (
                    <p className="text-muted-foreground text-sm">
                      Showing the first 50 rooms. Narrow the filters to see a specific
                      room.
                    </p>
                  ) : null}
                  {filters.view === "list" ? (
                    <AgendaList
                      spaces={spaces}
                      dates={dates}
                      timeZone={calendar.timezone}
                    />
                  ) : (
                    <>
                      {filters.view === "week" && spaces.length > 1 ? (
                        <fieldset className="flex flex-wrap items-center gap-1.5 border-0 p-0">
                          <legend className="sr-only">Room shown this week</legend>
                          {spaces.map((item) => (
                            <Button
                              key={item.publicId}
                              type="button"
                              size="sm"
                              variant={
                                item.publicId === focused?.publicId
                                  ? "secondary"
                                  : "ghost"
                              }
                              aria-pressed={item.publicId === focused?.publicId}
                              disabled={loading}
                              onClick={() => visit({ space: item.publicId })}
                            >
                              {item.name}
                            </Button>
                          ))}
                        </fieldset>
                      ) : null}
                      <RoomCalendarGrid
                        columns={columns}
                        startHour={bounds.startHour}
                        endHour={bounds.endHour}
                        timeZone={calendar.timezone}
                        caption={
                          filters.view === "week" && focused
                            ? `${focused.name} availability this week`
                            : "Room availability calendar"
                        }
                        onShowAllSlots={() => visit({ view: "list" })}
                      />
                    </>
                  )}
                  <p className="text-muted-foreground text-xs">{calendar.advisory}</p>
                </section>
              ) : null}
            </div>
          </div>
        )}
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
