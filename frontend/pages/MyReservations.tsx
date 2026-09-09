import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarClock,
  CalendarDays,
  Clock3,
  DoorOpen,
  MapPin,
  Package,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  Callout,
  EmptyState,
  FilterField,
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { NativeSelect } from "@/components/design-system/native-select";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  MyReservationSummary,
  MyReservationsPageProps,
  ReservationTab,
} from "@/types";

const TABS: { value: ReservationTab; label: string }[] = [
  { value: "upcoming", label: "Upcoming" },
  { value: "past", label: "Past" },
  { value: "cancelled", label: "Cancelled" },
  { value: "calendar", label: "Calendar" },
];

/**
 * Room and equipment must be told apart without relying on colour alone: an
 * icon, a word, and a different supporting line each carry the distinction.
 */
const SOURCE_ICON = { room: DoorOpen, inventory: Package } as const;

function dayLabel(row: MyReservationSummary) {
  const formatter = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: row.allDay ? "UTC" : row.timezone,
  });
  // An all-day window has no clock time to convert; read its own local date.
  const value = row.allDay
    ? new Date(`${row.localDate}T12:00:00Z`)
    : new Date(row.startsAt);
  return formatter.format(value);
}

function whenLabel(row: MyReservationSummary) {
  if (row.allDay) return "All day";
  const formatter = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: row.timezone,
  });
  return `${formatter.format(new Date(row.startsAt))}–${formatter.format(
    new Date(row.endsAt),
  )}`;
}

function ReservationCard({
  row,
  onCancel,
  headingLevel: Heading = "h2",
}: {
  row: MyReservationSummary;
  onCancel: (row: MyReservationSummary) => void;
  /**
   * The list has no intervening heading, so a card titles itself at h2. Under
   * the calendar's day heading it steps down to h3 — heading levels have to
   * increase by one, and a card cannot know which context it is in.
   */
  headingLevel?: "h2" | "h3";
}) {
  const Icon = SOURCE_ICON[row.source] ?? CalendarDays;
  return (
    <article className="border-border bg-card rounded-(--radius-card) border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              <Icon className="size-3" aria-hidden />
              {row.sourceLabel}
            </Badge>
            <StatusBadge status={{ label: row.displayStatusLabel, tone: row.tone }} />
          </div>
          <Heading className="text-foreground truncate font-semibold">
            <Link href={row.detailHref} className="hover:underline">
              {row.title}
            </Link>
          </Heading>
          <p className="text-muted-foreground truncate text-sm">
            {row.subtitle}
            {row.purpose ? ` · ${row.purpose}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-foreground text-sm font-semibold">{dayLabel(row)}</p>
          <p className="text-muted-foreground text-sm tabular-nums">{whenLabel(row)}</p>
        </div>
      </div>

      <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="inline-flex items-center gap-1">
          <MapPin className="size-3" aria-hidden />
          {row.officeName}
        </span>
        <span className="inline-flex items-center gap-1">
          <Clock3 className="size-3" aria-hidden />
          {row.reference}
        </span>
        {/* The domain's own wording, kept beside the normalized chip. */}
        <span>{row.statusLabel}</span>
      </div>

      {row.instructions ? (
        <p className="text-muted-foreground mt-2 text-sm">{row.instructions}</p>
      ) : null}

      {row.actions.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={row.detailHref}>Open</Link>
          </Button>
          {row.actions.map((action) =>
            action.method === "post" ? (
              <Button
                key={action.key}
                type="button"
                size="sm"
                variant={action.destructive ? "ghost" : "outline"}
                className={cn(action.destructive && "text-destructive")}
                onClick={() => onCancel(row)}
              >
                {action.label}
              </Button>
            ) : (
              <Button key={action.key} asChild size="sm" variant="outline">
                <Link href={action.href}>{action.label}</Link>
              </Button>
            ),
          )}
        </div>
      ) : null}
    </article>
  );
}

export default function MyReservations() {
  const { reservations, counts, filters, filterOptions, degraded } =
    usePage<MyReservationsPageProps>().props;
  const [loading, setLoading] = useState(false);
  const [pendingCancel, setPendingCancel] = useState<MyReservationSummary | null>(null);

  function visit(next: Partial<MyReservationsPageProps["filters"]>) {
    const merged = { ...filters, ...next };
    const params = new URLSearchParams();
    if (merged.tab) params.set("tab", merged.tab);
    if (merged.source) params.set("source", merged.source);
    if (merged.status) params.set("status", merged.status);
    router.get(
      `${routes.my_reservations()}?${params.toString()}`,
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

  /** The calendar groups the same rows by day rather than fetching again. */
  const byDay = useMemo(() => {
    const groups = new Map<string, MyReservationSummary[]>();
    for (const row of reservations) {
      const key = dayLabel(row);
      groups.set(key, [...(groups.get(key) ?? []), row]);
    }
    return [...groups.entries()];
  }, [reservations]);

  const isCalendar = filters.tab === "calendar";

  return (
    <div className="grid gap-6">
      <Head title="My reservations" />
      <PageHeader
        title="My reservations"
        description="Every room and equipment booking in your name, in one place."
      />

      {degraded ? (
        <Callout
          tone="warning"
          icon={TriangleAlert}
          title={`${degraded.failedSources.join(" and ")} could not be loaded`}
        >
          Everything below is complete for the sources that answered. Reload in a moment
          to see the rest.
        </Callout>
      ) : null}

      <SurfaceCard>
        <SurfaceCardContent className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 py-3">
          <fieldset className="bg-muted flex flex-wrap items-center gap-1 rounded-md border-0 p-1">
            <legend className="sr-only">Reservation list</legend>
            {TABS.map((tab) => (
              <Button
                key={tab.value}
                type="button"
                size="sm"
                variant={filters.tab === tab.value ? "secondary" : "ghost"}
                aria-pressed={filters.tab === tab.value}
                className={cn(filters.tab === tab.value && "shadow-card bg-card")}
                disabled={loading}
                onClick={() => visit({ tab: tab.value })}
              >
                {tab.label}
                {counts[tab.value] ? (
                  <span className="text-muted-foreground ml-1 tabular-nums">
                    {counts[tab.value]}
                  </span>
                ) : null}
              </Button>
            ))}
          </fieldset>

          <div className="flex flex-wrap items-end gap-3">
            <FilterField label="Type">
              <NativeSelect
                aria-label="Type"
                value={filters.source}
                disabled={loading}
                onChange={(event) => visit({ source: event.target.value })}
              >
                <option value="">All types</option>
                {filterOptions.sources.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FilterField>
            <FilterField label="Status">
              <NativeSelect
                aria-label="Status"
                value={filters.status}
                disabled={loading}
                onChange={(event) => visit({ status: event.target.value })}
              >
                <option value="">Any status</option>
                {filterOptions.statuses.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </NativeSelect>
            </FilterField>
          </div>
        </SurfaceCardContent>
      </SurfaceCard>

      <div className="sr-only" aria-live="polite">
        {loading ? "Loading reservations" : `${reservations.length} reservations shown`}
      </div>

      {reservations.length === 0 ? (
        <SurfaceCard>
          <EmptyState
            icon={CalendarClock}
            title={
              filters.source || filters.status
                ? "Nothing matches these filters"
                : filters.tab === "cancelled"
                  ? "No cancelled reservations"
                  : filters.tab === "past"
                    ? "Nothing here yet"
                    : "No upcoming reservations"
            }
            description={
              filters.source || filters.status
                ? "Clear a filter to widen the list."
                : "Book a room or reserve equipment and it will appear here."
            }
            actions={
              filters.source || filters.status ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => visit({ source: "", status: "" })}
                >
                  Clear filters
                </Button>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline">
                    <Link href={routes.room_availability()}>Book a room</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href={routes.office_inventory()}>Reserve equipment</Link>
                  </Button>
                </div>
              )
            }
          />
        </SurfaceCard>
      ) : isCalendar ? (
        // The calendar is an agenda: same rows, grouped by day. A grid would
        // add nothing here and would drop the keyboard parity the list has.
        <div className="grid gap-5">
          {byDay.map(([day, rows]) => (
            <section key={day} aria-labelledby={`day-${day}`}>
              <h2
                id={`day-${day}`}
                className="text-foreground mb-2 text-base font-semibold"
              >
                {day}
              </h2>
              <div className="grid gap-3">
                {rows.map((row) => (
                  <ReservationCard
                    key={row.sourceId}
                    row={row}
                    onCancel={setPendingCancel}
                    headingLevel="h3"
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="grid gap-3">
          {reservations.map((row) => (
            <ReservationCard key={row.sourceId} row={row} onCancel={setPendingCancel} />
          ))}
        </div>
      )}

      {pendingCancel ? (
        <CancelDialog row={pendingCancel} onDismiss={() => setPendingCancel(null)} />
      ) : null}
    </div>
  );
}

function CancelDialog({
  row,
  onDismiss,
}: {
  row: MyReservationSummary;
  onDismiss: () => void;
}) {
  const action = row.actions.find((item) => item.method === "post");
  if (!action) return null;
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="cancel-title"
      className="bg-background/80 fixed inset-0 z-50 grid place-items-center p-4"
    >
      <div className="bg-card border-border w-full max-w-md rounded-(--radius-card) border p-5 shadow-lg">
        <h2 id="cancel-title" className="text-foreground text-base font-semibold">
          Cancel {row.title}?
        </h2>
        <p className="text-muted-foreground mt-2 text-sm">
          {row.reference} · {dayLabel(row)} {whenLabel(row)}. This releases the booking
          for someone else and cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onDismiss}>
            Keep it
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() =>
              router.post(
                action.href,
                // The domain compares this and refuses if the record moved on.
                { expectedStatus: action.expectedStatus },
                { preserveScroll: true, onFinish: onDismiss },
              )
            }
          >
            {action.label}
          </Button>
        </div>
      </div>
    </div>
  );
}

MyReservations.layout = () =>
  [
    HubLayout,
    {
      variant: "standard",
      context: {
        title: "My reservations",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My reservations" },
        ],
      },
    },
  ] as const;
