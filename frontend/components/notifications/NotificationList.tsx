import { Link } from "@inertiajs/react";
import { Archive, ArrowRight, Check, Undo2 } from "lucide-react";

import { StatusBadge } from "@/components/design-system/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  notificationStateIcon,
  notificationStateNote,
  priorityPresentation,
} from "@/lib/notifications";
import { cn } from "@/lib/utils";
import type { NotificationRow } from "@/types";

export type NotificationAction = "read" | "unread" | "archive";

export interface NotificationListProps {
  rows: NotificationRow[];
  onAction: (row: NotificationRow, action: NotificationAction) => void;
  /** Id of the row whose mutation is in flight, if any. */
  pendingId?: string | null;
  busy?: boolean;
}

/**
 * One notification.
 *
 * Unread is carried by a filled marker *and* the word "Unread", never by
 * weight alone. A row that can no longer be acted on says why in the same
 * place its destination would have been, so a stale shortcut is explained
 * rather than silently missing.
 */
function NotificationItem({
  row,
  onAction,
  pending,
  busy,
}: {
  row: NotificationRow;
  onAction: NotificationListProps["onAction"];
  pending: boolean;
  busy: boolean;
}) {
  const note = notificationStateNote(row);
  const NoteIcon = notificationStateIcon(row);
  const inert = row.expired || row.archived;
  const disabled = busy || pending;

  return (
    <li
      className={cn("grid gap-2 px-5 py-4", !row.read && !inert && "bg-primary/[0.04]")}
      aria-busy={pending || undefined}
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <span
          aria-hidden
          className={cn(
            "mt-1.5 size-2 shrink-0 rounded-full",
            row.read || inert ? "bg-border" : "bg-primary",
          )}
        />
        <div className="min-w-0 flex-1">
          {/* The page title is the only h1; each notification is a section
              of it, so the row heading is an h2 regardless of its size. */}
          <h2 className="text-sm font-semibold tracking-[-0.01em]">{row.title}</h2>
          {row.detail ? (
            <p className="text-muted-foreground mt-0.5 text-sm leading-5">
              {row.detail}
            </p>
          ) : null}
          {note ? (
            <p className="text-muted-foreground mt-1 flex items-start gap-1.5 text-xs leading-5">
              <NoteIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>{note}</span>
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {row.mandatory ? (
            <Badge variant="outline" className="border-warning/40 text-warning-ink">
              Required
            </Badge>
          ) : null}
          <StatusBadge status={priorityPresentation(row)} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 pl-5">
        <p className="text-muted-foreground text-xs">
          <span className="font-medium">{row.typeLabel}</span>
          <span aria-hidden> · </span>
          <time dateTime={row.availableAt}>{row.receivedLabel}</time>
          <span aria-hidden> · </span>
          <span>{row.read ? "Read" : "Unread"}</span>
        </p>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {row.action ? (
            <Button asChild size="sm" variant="outline">
              <Link href={row.action.href}>
                {row.action.label}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </Button>
          ) : null}
          {row.read ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={disabled || row.archived}
              onClick={() => onAction(row, "unread")}
            >
              <Undo2 className="size-4" aria-hidden />
              <span>
                Mark unread
                <span className="sr-only">: {row.title}</span>
              </span>
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={disabled}
              onClick={() => onAction(row, "read")}
            >
              <Check className="size-4" aria-hidden />
              <span>
                Mark read
                <span className="sr-only">: {row.title}</span>
              </span>
            </Button>
          )}
          {row.archived ? null : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={disabled}
              onClick={() => onAction(row, "archive")}
            >
              <Archive className="size-4" aria-hidden />
              <span>
                Archive
                <span className="sr-only">: {row.title}</span>
              </span>
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

export function NotificationList({
  rows,
  onAction,
  pendingId = null,
  busy = false,
}: NotificationListProps) {
  return (
    <ul aria-busy={busy || undefined} className="divide-y">
      {rows.map((row) => (
        <NotificationItem
          key={row.id}
          row={row}
          onAction={onAction}
          pending={pendingId === row.id}
          busy={busy}
        />
      ))}
    </ul>
  );
}
