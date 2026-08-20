import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  Building2,
  Calendar,
  ChartLine,
  Contact,
  FileText,
  GraduationCap,
  LifeBuoy,
  ShieldCheck,
  Signature,
  Wallet,
} from "lucide-react";

/**
 * The approved marks a Quick Access link may draw.
 *
 * Keys are the values stored on the link record, and the backend allowlist in
 * `apps/web/quick_access/catalog.py` is pinned to this map by a test. An
 * administrator therefore chooses from marks the bundle already ships — there
 * is no path from a text field to a remote image.
 *
 * `microsoft` is deliberately absent: it is the one vendor whose real mark the
 * app ships, and `QuickApps` renders that component instead of a silhouette.
 */
export const QUICK_ACCESS_ICONS: Record<string, LucideIcon> = {
  "app-window": AppWindow,
  building: Building2,
  calendar: Calendar,
  "chart-line": ChartLine,
  contact: Contact,
  "file-text": FileText,
  "graduation-cap": GraduationCap,
  "life-buoy": LifeBuoy,
  "shield-check": ShieldCheck,
  signature: Signature,
  wallet: Wallet,
};

/** Rendered by its own component rather than a Lucide glyph. */
export const MICROSOFT_ICON_KEY = "microsoft";

export const QUICK_ACCESS_ICON_KEYS: readonly string[] = [
  ...Object.keys(QUICK_ACCESS_ICONS),
  MICROSOFT_ICON_KEY,
];

export function quickAccessIcon(key: string): LucideIcon {
  return QUICK_ACCESS_ICONS[key] ?? AppWindow;
}
