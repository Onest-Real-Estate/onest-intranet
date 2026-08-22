import {
  AlertTriangle,
  ArrowUp,
  Building2,
  Landmark,
  type LucideIcon,
  Map as MapIcon,
  UserRound,
  Users,
} from "lucide-react";

import type {
  AnnouncementAudienceEntry,
  AnnouncementBadge,
  AnnouncementFilters,
} from "@/types";
import type { StatusPresentation } from "@/types/design-system";

/**
 * Presentation helpers for the announcement feed.
 *
 * The taxonomy itself lives on the server (`apps/announcements/taxonomy.py`)
 * and reaches this file already resolved — code, label, tone, and a spoken
 * sentence. Nothing here classifies anything; it only decides how a resolved
 * classification is drawn.
 */

/**
 * Priority is never carried by color alone. The badge already says "Urgent"
 * in words; the icon adds a second non-color channel for readers scanning
 * shapes, and the `srLabel` sentence carries the whole thing to a screen
 * reader. Normal has no icon deliberately — routine news should not compete
 * for attention with the two levels above it.
 */
const PRIORITY_ICONS: Record<string, LucideIcon> = {
  urgent: AlertTriangle,
  important: ArrowUp,
};

export function priorityPresentation(badge: AnnouncementBadge): StatusPresentation {
  return {
    label: badge.label,
    tone: badge.tone,
    icon: PRIORITY_ICONS[badge.code],
  };
}

export function categoryPresentation(badge: AnnouncementBadge): StatusPresentation {
  return { label: badge.label, tone: badge.tone };
}

/** Filter keys the reader can set. `rejected` is a report, not a filter. */
export const FILTER_KEYS = ["category", "priority"] as const;

export function activeFilterCount(filters: AnnouncementFilters): number {
  return FILTER_KEYS.filter((key) => Boolean(filters[key])).length;
}

/**
 * A dropped filter is stated rather than swallowed: a stale bookmark that no
 * longer matches a live code would otherwise silently show more news than the
 * reader asked for.
 */
export function rejectedFilterMessage(filters: AnnouncementFilters): string | null {
  const names = filters.rejected.filter((key) =>
    (FILTER_KEYS as readonly string[]).includes(key),
  );
  if (names.length === 0) {
    return null;
  }
  const listed = names.join(" and ");
  return `We could not read the ${listed} filter from this link, so it was not applied.`;
}

/** Announcements shown with a fallback because their stored code is unknown. */
export function hasUnknownClassification(badges: AnnouncementBadge[]): boolean {
  return badges.some((badge) => !badge.known);
}

/**
 * Icon per audience selector kind. The label always carries the meaning; the
 * icon is a second channel, the same bargain the priority badge makes.
 */
const AUDIENCE_ICONS: Record<AnnouncementAudienceEntry["kind"], LucideIcon> = {
  company: Building2,
  role: Users,
  region: MapIcon,
  office: Landmark,
  user: UserRound,
};

export function audienceIcon(kind: AnnouncementAudienceEntry["kind"]): LucideIcon {
  return AUDIENCE_ICONS[kind] ?? Users;
}

/**
 * Union semantics, said out loud.
 *
 * The same sentence the backend documents in `docs/announcements.md`: any one
 * selector is enough. Reading "Fairfax, VA" beside "Compliance" and inferring
 * "compliance officers *in* Fairfax" would be exactly backwards, so the page
 * states the rule rather than leaving the list to imply it.
 */
export function audienceSummary(entries: AnnouncementAudienceEntry[]): string {
  if (entries.length === 0) {
    return "No audience selected yet.";
  }
  if (entries.length === 1) {
    return `Sent to ${entries[0].label}.`;
  }
  return `Sent to anyone matching any of these ${entries.length} audiences.`;
}
