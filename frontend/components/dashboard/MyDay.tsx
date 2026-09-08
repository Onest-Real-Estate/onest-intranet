import { Link } from "@inertiajs/react";
import { ArrowRight, MapPin, TriangleAlert } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardFooter,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { AgendaEvent, DashboardSchedule } from "@/types";

/**
 * One row of the agenda.
 *
 * The time sits in its own column so the whole card scans as a chronology —
 * a reader looking for "what is next" reads down one edge rather than parsing
 * every title. Overdue is said in words as well as colour, because the reader
 * most likely to miss the tint is the one who most needs the row.
 */
function AgendaRow({ event }: { event: AgendaEvent }) {
  const body = (
    <>
      <span className="grid w-[5.5rem] shrink-0 gap-0.5 pt-0.5">
        {/* The day is named whenever it is not today. Without it, a 6pm row
            tomorrow sitting above a 5pm row the day after reads as a sorting
            bug rather than as two different days. */}
        {event.isToday ? null : (
          <span className="text-muted-foreground text-[0.6875rem] font-medium">
            {event.dayLabel}
          </span>
        )}
        <span
          className={cn(
            "text-xs font-medium tabular-nums",
            event.overdue ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {event.timeLabel}
        </span>
      </span>
      <span className="grid min-w-0 flex-1 gap-1">
        <span className="flex min-w-0 items-start gap-2">
          {/* Clamped rather than truncated: in a rail this narrow a hard
              ellipsis eats most of a real title, and two lines still bound
              the row height. `min-w-0` is what lets it shrink at all —
              without it the flex item sizes to its text and overflows the
              card instead of wrapping. */}
          <span className="line-clamp-2 min-w-0 flex-1 text-sm font-medium">
            {event.title}
          </span>
          {event.statusLabel ? (
            <span className="text-warning-ink bg-chip-warning border-chip-warning-edge shrink-0 rounded-full border px-1.5 py-px text-[0.6875rem] font-medium">
              {event.statusLabel}
            </span>
          ) : null}
        </span>
        <span className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
          <span>{event.sourceLabel}</span>
          {event.context ? (
            <>
              <span aria-hidden>·</span>
              <span className="truncate">{event.context}</span>
            </>
          ) : null}
          {event.location ? (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex min-w-0 items-center gap-1">
                <MapPin className="size-3 shrink-0" aria-hidden />
                <span className="truncate">{event.location}</span>
              </span>
            </>
          ) : null}
        </span>
      </span>
    </>
  );

  return (
    <li>
      {event.ctaHref ? (
        // The destination re-authorizes this reader on arrival; the row is a
        // convenience, never the grant.
        <Link
          href={event.ctaHref}
          className="hover:bg-muted/50 focus-visible:ring-ring flex gap-3 rounded-lg px-2 py-2 -mx-2 transition-colors focus-visible:ring-2 focus-visible:outline-none"
        >
          {body}
          <span className="sr-only">
            {" — "}
            {event.ctaLabel}
          </span>
        </Link>
      ) : (
        <div className="flex gap-3 px-2 py-2 -mx-2">{body}</div>
      )}
    </li>
  );
}

function Section({
  label,
  events,
  tone = "neutral",
}: {
  label: string;
  events: AgendaEvent[];
  tone?: "neutral" | "destructive";
}) {
  if (events.length === 0) {
    return null;
  }
  return (
    <section className="grid gap-1" aria-label={label}>
      <h3
        className={cn(
          "flex items-center gap-1.5 px-2 -mx-2 text-[0.6875rem] font-semibold tracking-[0.06em] uppercase",
          tone === "destructive" ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {tone === "destructive" ? (
          <TriangleAlert className="size-3.5" aria-hidden />
        ) : null}
        {label}
      </h3>
      <ul className="grid">
        {events.map((event) => (
          <AgendaRow key={event.id} event={event} />
        ))}
      </ul>
    </section>
  );
}

/**
 * Every time-bound obligation this reader has, in one chronology.
 *
 * The three lists arrive already bucketed and ordered by the server, in the
 * reader's own timezone. The component deliberately does no sorting, grouping,
 * or time formatting of its own: re-deriving any of it from the browser clock
 * is how a laptop on last week's timezone ends up disagreeing with the day
 * boundaries the buckets were built from.
 *
 * `partialFailure` renders alongside the rows rather than replacing them — a
 * source being down is a reason to caveat the list, not to hide what did load.
 */
export function MyDay({
  schedule,
  partialFailure = false,
  truncated = false,
}: {
  schedule: DashboardSchedule;
  partialFailure?: boolean;
  truncated?: boolean;
}) {
  const shown =
    schedule.overdue.length + schedule.today.length + schedule.upcoming.length;
  const capped = truncated || schedule.total > shown;

  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title="My day"
        meta={
          <SurfaceCardMeta>
            {capped ? `${shown} of ${schedule.total}` : schedule.dateLabel}
          </SurfaceCardMeta>
        }
      />
      <SurfaceCardContent className="grid gap-4">
        {partialFailure ? (
          // Deliberately unspecific about which source: naming it would tell
          // the reader which calendars they are subject to.
          <p
            role="status"
            className="text-warning-ink bg-chip-warning border-chip-warning-edge rounded-lg border px-3 py-2 text-xs"
          >
            Some sources are unavailable, so this list may be incomplete.
          </p>
        ) : null}
        <Section label="Overdue" events={schedule.overdue} tone="destructive" />
        <Section label="Today" events={schedule.today} />
        <Section label="Upcoming" events={schedule.upcoming} />
      </SurfaceCardContent>
      <SurfaceCardFooter>
        <Button asChild variant="outline" size="sm" className="w-full">
          <Link href={schedule.viewAllHref}>
            {schedule.viewAllLabel}
            <ArrowRight className="size-4" strokeWidth={1.5} aria-hidden />
          </Link>
        </Button>
      </SurfaceCardFooter>
    </SurfaceCard>
  );
}

export function MyDaySkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="My day" />
      <SurfaceCardContent className="grid gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
