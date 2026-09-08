import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";

import { FormFieldError } from "@/components/design-system";
import { NativeSelect } from "@/components/design-system/native-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SpaceScheduleInterval } from "@/types";

const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** Server times arrive as `HH:MM:SS`; `<input type="time">` wants `HH:MM`. */
function toInputTime(value: string) {
  return value.slice(0, 5);
}

interface EditorRow extends SpaceScheduleInterval {
  id: string;
}

function overlapsWithin(intervals: SpaceScheduleInterval[]) {
  const byDay = new Map<number, SpaceScheduleInterval[]>();
  for (const item of intervals) {
    byDay.set(item.weekday, [...(byDay.get(item.weekday) ?? []), item]);
  }
  for (const spans of byDay.values()) {
    const ordered = [...spans].sort((a, b) => a.startsAt.localeCompare(b.startsAt));
    for (let index = 1; index < ordered.length; index += 1) {
      if (ordered[index - 1].endsAt > ordered[index].startsAt) return true;
    }
  }
  return false;
}

/**
 * Weekly opening hours as an editable set of rows.
 *
 * Rows, not a drag-to-paint grid: a scoped administrator has to be able to do
 * this from the keyboard, and a painted grid cannot express "08:00 to 12:00 and
 * 13:00 to 17:00" without a second control anyway. The client validation here
 * is a courtesy — `replace_weekly_schedule` re-checks ordering, overlap, and
 * booking impact on the server.
 */
export function RoomScheduleEditor({
  schedule,
  disabled = false,
  saving = false,
  error,
  onSave,
}: {
  schedule: SpaceScheduleInterval[];
  disabled?: boolean;
  saving?: boolean;
  error?: string;
  onSave: (intervals: SpaceScheduleInterval[]) => void;
}) {
  const listId = useId();
  // Rows are added and removed, so each carries an identity of its own; an
  // array index as key would let React reuse the wrong row's DOM after a
  // removal and move the focus ring somewhere the user did not put it.
  const [rows, setRows] = useState<EditorRow[]>(() =>
    schedule.map((item, index) => ({
      id: `row-${index}`,
      weekday: item.weekday,
      startsAt: toInputTime(item.startsAt),
      endsAt: toInputTime(item.endsAt),
    })),
  );
  const [nextId, setNextId] = useState(schedule.length);

  const invalidOrder = rows.some((row) => row.startsAt >= row.endsAt);
  const overlapping = overlapsWithin(rows);
  const localError = invalidOrder
    ? "Each interval must end after it starts."
    : overlapping
      ? "Two intervals on the same day overlap."
      : "";

  function update(id: string, patch: Partial<SpaceScheduleInterval>) {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
  }

  return (
    <div className="grid gap-4">
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          The room is closed every day. Add an interval to open it.
        </p>
      ) : (
        <ul className="grid gap-2" id={listId}>
          {rows.map((row) => (
            <li
              key={row.id}
              className="border-border bg-card flex flex-wrap items-end gap-2 rounded-md border p-3"
            >
              <div className="grid gap-1.5">
                <label
                  className="text-muted-foreground text-xs font-semibold"
                  htmlFor={`${listId}-day-${row.id}`}
                >
                  Day
                </label>
                <NativeSelect
                  id={`${listId}-day-${row.id}`}
                  value={String(row.weekday)}
                  disabled={disabled}
                  onChange={(event) =>
                    update(row.id, { weekday: Number(event.target.value) })
                  }
                >
                  {WEEKDAYS.map((label, value) => (
                    <option key={label} value={value}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <label
                  className="text-muted-foreground text-xs font-semibold"
                  htmlFor={`${listId}-from-${row.id}`}
                >
                  Opens
                </label>
                <Input
                  id={`${listId}-from-${row.id}`}
                  type="time"
                  className="w-32"
                  value={row.startsAt}
                  disabled={disabled}
                  onChange={(event) => update(row.id, { startsAt: event.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <label
                  className="text-muted-foreground text-xs font-semibold"
                  htmlFor={`${listId}-to-${row.id}`}
                >
                  Closes
                </label>
                <Input
                  id={`${listId}-to-${row.id}`}
                  type="time"
                  className="w-32"
                  value={row.endsAt}
                  disabled={disabled}
                  onChange={(event) => update(row.id, { endsAt: event.target.value })}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                aria-label={`Remove ${WEEKDAYS[row.weekday]} ${row.startsAt} to ${row.endsAt}`}
                onClick={() =>
                  setRows((current) => current.filter((item) => item.id !== row.id))
                }
              >
                <Trash2 className="size-4" aria-hidden />
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      <FormFieldError
        messages={localError ? [localError] : error ? [error] : undefined}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => {
            setRows((current) => [
              ...current,
              {
                id: `row-${nextId}`,
                weekday: 0,
                startsAt: "09:00",
                endsAt: "17:00",
              },
            ]);
            setNextId((value) => value + 1);
          }}
        >
          <Plus className="size-4" aria-hidden />
          Add interval
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={disabled || saving || Boolean(localError)}
          onClick={() =>
            onSave(
              rows.map(({ weekday, startsAt, endsAt }) => ({
                weekday,
                startsAt,
                endsAt,
              })),
            )
          }
        >
          {saving ? "Saving hours…" : "Save hours"}
        </Button>
      </div>
    </div>
  );
}
