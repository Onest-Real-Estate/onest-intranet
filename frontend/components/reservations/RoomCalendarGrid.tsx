import { Link } from "@inertiajs/react";
import { Clock3, DoorClosed, Lock } from "lucide-react";

import { cn } from "@/lib/utils";

/** One hour of the time axis, in pixels. Drives every block's height. */
const HOUR_PX = 68;
/**
 * Start-time chips shown inside one block before deferring to the list.
 *
 * A full working day at 15-minute granularity is thirty-odd chips per room. At
 * that density the tint stops reading as "this range is free" and becomes the
 * loudest mass on the page, and the blocks themselves stop being scannable. The
 * list view still carries every start, so nothing is lost — only deferred.
 */
const MAX_VISIBLE_SLOTS = 6;
const MINUTE_PX = HOUR_PX / 60;
/** Leaves room for the first hour label, which is centred on its own line. */
const GRID_TOP_PAD = 10;

export type CalendarEventKind = "available" | "busy" | "mine" | "blocked";

export interface CalendarEvent {
  id: string;
  kind: CalendarEventKind;
  /** Minutes from the grid's first hour. */
  startMinute: number;
  endMinute: number;
  title: string;
  timeLabel: string;
  /** Selectable start times inside an available range. */
  /** ``label`` is what the chip shows; ``ariaLabel`` names the whole range. */
  slots?: {
    startsAt: string;
    label: string;
    ariaLabel: string;
    bookingHref: string;
  }[];
}

export interface CalendarColumn {
  id: string;
  label: string;
  sublabel?: string;
  emphasis?: string;
  /** Spoken name when the visible heading is a bare numeral. */
  accessibleName?: string;
  isToday?: boolean;
  isClosed?: boolean;
  events: CalendarEvent[];
}

/**
 * Tone per event kind. These are the project's chip pairs — tinted surface,
 * matching hairline, own ink — not new colours: a booking calendar wants
 * distinguishable blocks, and the token set already solves that in both themes.
 */
const kindClasses: Record<CalendarEventKind, string> = {
  available: "border-chip-success-edge bg-chip-success text-success",
  mine: "border-chip-primary-edge bg-chip-primary text-primary",
  busy: "border-chip-neutral-edge bg-chip-neutral text-muted-foreground",
  blocked: "border-chip-warning-edge bg-chip-warning text-warning-ink",
};

/**
 * Greedy lane packing so overlapping events sit side by side.
 *
 * A calendar that stacks concurrent events on top of each other hides one of
 * them; this walks the column in start order and drops each event into the
 * first lane whose last event has already ended.
 */
function assignLanes(events: CalendarEvent[]) {
  const ordered = [...events].sort(
    (a, b) => a.startMinute - b.startMinute || a.endMinute - b.endMinute,
  );
  const laneEnds: number[] = [];
  const placed = ordered.map((event) => {
    let lane = laneEnds.findIndex((end) => end <= event.startMinute);
    if (lane === -1) {
      laneEnds.push(event.endMinute);
      lane = laneEnds.length - 1;
    } else {
      laneEnds[lane] = event.endMinute;
    }
    return { event, lane };
  });
  return { placed, laneCount: Math.max(laneEnds.length, 1) };
}

function hourLabel(hour: number) {
  const period = hour < 12 ? "AM" : "PM";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display} ${period}`;
}

function EventBlock({
  event,
  laneCount,
  lane,
  onShowAllSlots,
}: {
  event: CalendarEvent;
  laneCount: number;
  lane: number;
  onShowAllSlots?: () => void;
}) {
  const top = event.startMinute * MINUTE_PX + GRID_TOP_PAD;
  const height = Math.max((event.endMinute - event.startMinute) * MINUTE_PX, 26);
  const width = `calc(${100 / laneCount}% - 4px)`;
  const left = `calc(${(lane * 100) / laneCount}% + 2px)`;
  const compact = height < 56;
  const slots = event.slots ?? [];
  // An open range every candidate start has been filtered out of — minimum
  // notice, buffers, a booking horizon — is not bookable, and painting it as
  // available would promise a slot the server would refuse.
  const unbookable = event.kind === "available" && slots.length === 0;
  const visible = slots.slice(0, MAX_VISIBLE_SLOTS);
  const overflow = slots.length - visible.length;
  // A block only has room for start-time chips once it is about an hour tall.
  // Below that the whole block becomes the link, so a short opening is never a
  // block the reader can see but not act on.
  // Two rows of 24px chips plus the title and time need about this much.
  const showsChips = slots.length > 0 && height >= 96;
  const wholeBlockLinks = slots.length > 0 && !showsChips;

  // When the block *is* the link, it must show the slot it books rather than
  // the whole opening: a visible "9:00-10:00" on a control that books 9:00-9:30
  // is a label that disagrees with its own action.
  const shownTime = wholeBlockLinks ? slots[0].ariaLabel : event.timeLabel;

  const body = (
    <>
      <p
        className={cn(
          "text-foreground truncate font-semibold",
          compact ? "text-[0.6875rem] leading-4" : "text-xs leading-4",
        )}
        title={event.title}
      >
        {event.kind === "busy" || event.kind === "blocked" ? (
          <Lock className="mr-1 inline size-3 align-[-2px]" aria-hidden />
        ) : null}
        {event.title}
      </p>
      {!compact || wholeBlockLinks ? (
        <p className="mt-0.5 flex items-center gap-1 text-[0.6875rem] tabular-nums">
          <Clock3 className="size-3 shrink-0" aria-hidden />
          {shownTime}
        </p>
      ) : null}
      {unbookable && !compact ? (
        <p className="mt-1 text-[0.6875rem] font-medium">No valid starts</p>
      ) : null}
      {showsChips ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {visible.map((slot) => (
            <Link
              key={slot.startsAt}
              href={slot.bookingHref}
              aria-label={slot.ariaLabel}
              className="border-border bg-card text-foreground hover:border-ring focus-visible:ring-ring inline-flex h-6 items-center rounded-sm border px-2 text-xs font-semibold tabular-nums transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
            >
              {slot.label}
            </Link>
          ))}
          {overflow > 0 ? (
            <button
              type="button"
              onClick={onShowAllSlots}
              className="border-border bg-card text-muted-foreground hover:text-foreground hover:border-ring focus-visible:ring-ring inline-flex h-6 items-center rounded-sm border px-2 text-xs font-semibold transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
            >
              +{overflow} more
            </button>
          ) : null}
        </div>
      ) : null}
    </>
  );

  const shell = cn(
    "absolute overflow-hidden rounded-md border p-2",
    unbookable ? kindClasses.busy : kindClasses[event.kind],
  );

  if (wholeBlockLinks) {
    const first = slots[0];

    return (
      <Link
        href={first.bookingHref}
        className={cn(
          shell,
          "hover:border-ring focus-visible:ring-ring block transition-colors focus-visible:ring-[3px] focus-visible:outline-none",
        )}
        style={{ top, height, width, left }}
      >
        {body}
      </Link>
    );
  }

  return (
    <div className={shell} style={{ top, height, width, left }}>
      {body}
    </div>
  );
}

/**
 * A time-axis calendar: hours down the side, one column per resource or day.
 *
 * The grid is the *scannable* form. It is not the only way to reach a slot —
 * the page's list view renders the same candidate starts as ordinary links, so
 * nothing here is the sole route to an action, and no interaction needs a
 * pointer.
 */
export function RoomCalendarGrid({
  columns,
  startHour,
  endHour,
  timeZone,
  caption,
  onShowAllSlots,
}: {
  columns: CalendarColumn[];
  startHour: number;
  endHour: number;
  timeZone: string;
  caption: string;
  /** Hands the reader the complete list when a block cannot show every start. */
  onShowAllSlots?: () => void;
}) {
  const hours = Array.from(
    { length: Math.max(endHour - startHour, 1) },
    (_, index) => startHour + index,
  );
  const bodyHeight = hours.length * HOUR_PX + GRID_TOP_PAD * 2;

  return (
    <section
      aria-label={caption}
      className="border-border bg-card @container overflow-hidden rounded-lg border"
    >
      {/* No tabIndex here on purpose. Tabbing to a slot link inside an
          off-screen column scrolls it into view on its own, so the bookable
          content already reaches the keyboard. A column carrying only
          read-only blocks has no focus stop, and the list view — which renders
          every room, day, and interval — is its equivalent path. Giving a plain
          scroller a tab stop would add a focus position that announces nothing
          and does nothing. */}
      <div className="overflow-x-auto">
        <div className="min-w-[42rem]">
          <div
            className="border-border grid border-b"
            style={{
              gridTemplateColumns: `4.5rem repeat(${columns.length}, minmax(9rem, 1fr))`,
            }}
          >
            <div className="text-muted-foreground flex items-end justify-end p-2 text-[0.6875rem] font-semibold">
              {timeZone.split("/").pop()?.replace("_", " ")}
            </div>
            {columns.map((column) => (
              <div key={column.id} className="p-2">
                <div
                  className={cn(
                    "rounded-md border px-3 py-2 text-center",
                    column.isToday
                      ? "border-chip-primary-edge bg-chip-primary"
                      : "border-transparent bg-muted",
                  )}
                >
                  <p className="text-muted-foreground truncate text-[0.6875rem] font-semibold tracking-[0.02em]">
                    {column.label}
                  </p>
                  {/* A heading per column, so a screen reader can jump between
                      rooms or days instead of walking every block. */}
                  <h2
                    className={cn(
                      "text-foreground truncate font-bold",
                      column.emphasis ? "text-2xl leading-8" : "text-sm leading-6",
                    )}
                    title={column.sublabel ?? column.accessibleName}
                  >
                    {column.accessibleName ? (
                      <span className="sr-only">{column.accessibleName}</span>
                    ) : null}
                    <span aria-hidden={Boolean(column.accessibleName)}>
                      {column.emphasis ?? column.sublabel}
                    </span>
                  </h2>
                  {column.emphasis && column.sublabel ? (
                    <p className="text-muted-foreground truncate text-[0.6875rem]">
                      {column.sublabel}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>

          <div
            className="grid"
            style={{
              gridTemplateColumns: `4.5rem repeat(${columns.length}, minmax(9rem, 1fr))`,
            }}
          >
            <div className="relative" style={{ height: bodyHeight }} aria-hidden>
              {hours.map((hour, index) => (
                <div
                  key={hour}
                  className="text-muted-foreground absolute right-2 -translate-y-1/2 text-[0.6875rem] font-semibold tabular-nums"
                  style={{ top: index * HOUR_PX + GRID_TOP_PAD }}
                >
                  {hourLabel(hour)}
                </div>
              ))}
            </div>

            {columns.map((column) => {
              const { placed, laneCount } = assignLanes(column.events);
              return (
                <div
                  key={column.id}
                  className="border-border relative border-l"
                  style={{ height: bodyHeight }}
                >
                  {hours.map((hour, index) => (
                    <div
                      key={hour}
                      className="border-border/70 absolute inset-x-0 border-t"
                      style={{ top: index * HOUR_PX + GRID_TOP_PAD }}
                      aria-hidden
                    />
                  ))}
                  {column.isClosed ? (
                    <p className="text-muted-foreground absolute inset-x-2 top-6 flex items-center justify-center gap-1.5 text-xs font-medium">
                      <DoorClosed className="size-3.5" aria-hidden />
                      Closed
                    </p>
                  ) : null}
                  {placed.map(({ event, lane }) => (
                    <EventBlock
                      key={event.id}
                      event={event}
                      lane={lane}
                      laneCount={laneCount}
                      onShowAllSlots={onShowAllSlots}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
