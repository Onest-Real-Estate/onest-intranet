import {
  AlertTriangle,
  ArrowUp,
  Building2,
  CalendarDays,
  GraduationCap,
  Landmark,
  Laptop,
  type LucideIcon,
  Map as MapIcon,
  Megaphone,
  Newspaper,
  ShieldCheck,
  Siren,
  TrendingUp,
  UserRound,
  Users,
} from "lucide-react";

import type {
  AnnouncementAudienceEntry,
  AnnouncementBadge,
  AnnouncementFilters,
  AnnouncementMedia,
  AnnouncementMediaAdmin,
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

/**
 * A mark per category, keyed by the taxonomy's stable code.
 *
 * The feed is otherwise a column of identically-shaped rows, and a reader
 * looking for "the training one" should not have to read eight titles to find
 * it. The icon is a second, non-colour channel for the classification the
 * badge already states in words, so it adds a way to scan without becoming the
 * only way to know.
 *
 * An unknown or retired code falls back to the generic mark rather than
 * failing — the taxonomy is editable, and a row stored against a code this
 * build has never seen still has to render.
 */
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  company_announcement: Megaphone,
  market_update: TrendingUp,
  event: CalendarDays,
  training_notice: GraduationCap,
  compliance_update: ShieldCheck,
  office_notice: Building2,
  technology_notice: Laptop,
  urgent_operational_notice: Siren,
};

export function categoryIcon(badge: AnnouncementBadge): LucideIcon {
  return CATEGORY_ICONS[badge.code] ?? Newspaper;
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

/**
 * Hero rendering.
 *
 * The hero is decoration wrapped around a headline that already carries the
 * meaning, so its `alt` is empty and every failure mode — no hero, no variants,
 * a broken response — has to land on the same text-first layout rather than a
 * broken-image icon. `heroSources` returns null whenever there is nothing safe
 * to render, and the caller treats that identically to an image that failed to
 * load at runtime.
 */
export interface HeroSources {
  src: string;
  srcSet?: string;
  width: number | null;
  height: number | null;
}

/** Widths the server generates, mirrored here only to build `srcset`. */
const VARIANT_WIDTHS: Record<string, number> = {
  thumb: 320,
  card: 768,
  hero: 1600,
};

export function heroSources(
  hero: AnnouncementMedia | null | undefined,
): HeroSources | null {
  if (!hero?.isImage || !hero.url) {
    return null;
  }
  const entries = Object.entries(hero.variants ?? {}).filter(
    ([label]) => label in VARIANT_WIDTHS,
  );
  const srcSet = entries
    .map(([label, url]) => `${url} ${VARIANT_WIDTHS[label]}w`)
    .join(", ");
  return {
    // The largest variant is the best default, but the original always works,
    // so a processing pass that produced nothing still renders.
    src: hero.variants?.hero ?? hero.url,
    srcSet: srcSet || undefined,
    width: hero.width,
    height: hero.height,
  };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const PROCESSING_LABELS: Record<
  AnnouncementMediaAdmin["processingState"],
  StatusPresentation
> = {
  pending: { label: "Processing", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  quarantined: { label: "Quarantined", tone: "destructive" },
  failed: { label: "Check failed", tone: "destructive" },
};

/** Administrator-facing only; a recipient is never told a file was rejected. */
export function processingPresentation(
  state: AnnouncementMediaAdmin["processingState"],
): StatusPresentation {
  return PROCESSING_LABELS[state] ?? PROCESSING_LABELS.pending;
}

/** True while anything on the announcement still blocks publication. */
export function hasBlockingMedia(items: AnnouncementMediaAdmin[]): boolean {
  return items.some((item) => item.processingState !== "ready");
}

/**
 * Client-side pre-check. Cheap feedback only — the server validates the bytes
 * and is the decision that matters, so this never has to be exhaustive.
 */
export function fileRejectionReason(
  file: { name: string; size: number },
  limits: { extensions: string[]; maxBytes: number },
): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot === -1 ? "" : file.name.slice(dot).toLowerCase();
  if (!limits.extensions.includes(extension)) {
    return `${extension || "That file type"} is not an allowed file type.`;
  }
  if (file.size > limits.maxBytes) {
    return `Files must be ${formatBytes(limits.maxBytes)} or smaller.`;
  }
  return null;
}
