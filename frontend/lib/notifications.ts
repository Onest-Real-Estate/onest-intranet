import { AlertTriangle, Archive, BellRing, Clock, Info } from "lucide-react";
import type { NotificationPriority, NotificationRow } from "@/types";
import type { StatusPresentation } from "@/types/design-system";

/**
 * Presentation for one notification's priority.
 *
 * Colour never carries the meaning on its own: every badge pairs its tone with
 * the server's own label, so the row still reads correctly in monochrome and
 * to a screen reader.
 */
export function priorityPresentation(row: {
  priority: NotificationPriority;
  priorityLabel: string;
}): StatusPresentation {
  switch (row.priority) {
    case "critical":
      return { label: row.priorityLabel, tone: "destructive", icon: AlertTriangle };
    case "high":
      return { label: row.priorityLabel, tone: "warning", icon: BellRing };
    case "low":
      return { label: row.priorityLabel, tone: "neutral", icon: Info };
    default:
      return { label: row.priorityLabel, tone: "info", icon: Info };
  }
}

/**
 * The single sentence explaining why a row is inert, or "".
 *
 * Expiry, archival, and a withdrawn source all end in the same place for the
 * reader: nothing to do here. They are worth distinguishing in the copy, and
 * not worth distinguishing anywhere else.
 */
export function notificationStateNote(row: NotificationRow): string {
  if (row.expired) {
    return row.unavailableReason || "This notification has expired.";
  }
  if (row.archived) {
    return "Archived.";
  }
  if (row.unavailableReason) {
    return row.unavailableReason;
  }
  if (row.staleAction) {
    return row.staleActionNote;
  }
  return "";
}

export function notificationStateIcon(row: NotificationRow) {
  if (row.expired) {
    return Clock;
  }
  if (row.archived) {
    return Archive;
  }
  return AlertTriangle;
}

/** What the badge shows. Above the cap the exact figure stops being useful. */
export const UNREAD_BADGE_CAP = 99;

export function unreadBadgeLabel(count: number): string {
  if (count <= 0) {
    return "";
  }
  return count > UNREAD_BADGE_CAP ? `${UNREAD_BADGE_CAP}+` : String(count);
}

export function unreadAnnouncement(count: number, mandatory: number): string {
  if (count <= 0) {
    return "No unread notifications";
  }
  const base = count === 1 ? "1 unread notification" : `${count} unread notifications`;
  return mandatory > 0 ? `${base}, ${mandatory} requiring acknowledgement` : base;
}
