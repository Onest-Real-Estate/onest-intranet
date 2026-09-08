import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Keyed by full name because the initials repeat (S/T twice). */
const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

const MONTH_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

const FULL_DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

/** Parse an ISO date as a UTC noon instant, immune to local-timezone drift. */
function fromIso(value: string) {
  return new Date(`${value}T12:00:00Z`);
}

function toIso(date: Date) {
  return date.toISOString().slice(0, 10);
}

function startOfMonth(date: Date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1, 12));
}

function addMonths(date: Date, amount: number) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + amount, 1, 12));
}

/**
 * The month grid: six weeks starting on the Sunday on or before the first.
 * Days outside the month are still rendered so the grid never reflows height.
 */
function monthGrid(month: Date) {
  const first = startOfMonth(month);
  const cursor = new Date(first);
  cursor.setUTCDate(1 - first.getUTCDay());
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(cursor);
    day.setUTCDate(cursor.getUTCDate() + index);
    return day;
  });
}

/**
 * Date picker for the calendar rail.
 *
 * Every day is a real button with a full accessible name, so choosing a date
 * never needs a pointer. Dates before today are disabled because the server
 * refuses them — showing them as choosable would be a lie the page tells.
 */
export function MiniMonthCalendar({
  selected,
  today,
  onSelect,
  disabled = false,
}: {
  selected: string;
  today: string;
  onSelect: (date: string) => void;
  disabled?: boolean;
}) {
  const [month, setMonth] = useState(() => startOfMonth(fromIso(selected)));
  const days = monthGrid(month);
  const monthIndex = month.getUTCMonth();

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground text-base font-bold tracking-[-0.01em]">
          {MONTH_FORMAT.format(month)}
        </h2>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Previous month"
            disabled={disabled}
            onClick={() => setMonth((current) => addMonths(current, -1))}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Next month"
            disabled={disabled}
            onClick={() => setMonth((current) => addMonths(current, 1))}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-y-1">
        {WEEKDAYS.map((name) => (
          <div
            key={name}
            className="text-muted-foreground text-center text-[0.6875rem] font-semibold"
            aria-hidden
          >
            {name.charAt(0)}
          </div>
        ))}
        {days.map((day) => {
          const iso = toIso(day);
          const isSelected = iso === selected;
          const isToday = iso === today;
          const isOutside = day.getUTCMonth() !== monthIndex;
          const isPast = iso < today;
          return (
            <button
              key={iso}
              type="button"
              disabled={disabled || isPast}
              aria-current={isSelected ? "date" : undefined}
              aria-label={FULL_DATE_FORMAT.format(day)}
              onClick={() => onSelect(iso)}
              className={cn(
                "focus-visible:ring-ring mx-auto flex size-8 items-center justify-center rounded-full text-xs font-semibold tabular-nums transition-colors focus-visible:ring-[3px] focus-visible:outline-none",
                // Selection is a neutral fill, not gold: the page already spends
                // gold on the one action worth pressing, and two golds side by
                // side leave neither of them meaning "press this".
                isSelected
                  ? "bg-foreground text-background"
                  : isToday
                    ? "border-chip-primary-edge bg-chip-primary text-primary border"
                    : "hover:bg-muted text-foreground",
                isOutside && !isSelected && "text-muted-foreground/60",
                isPast && "cursor-not-allowed opacity-40 hover:bg-transparent",
              )}
            >
              {day.getUTCDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}
