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
import { BRAND_MARK_KEYS } from "@/components/BrandMarks";

/**
 * The approved marks a Quick Access link may draw.
 *
 * Keys are the values stored on the link record, and the backend allowlist in
 * `apps/web/quick_access/catalog.py` is pinned to this map by a test. An
 * administrator therefore chooses from marks the bundle already ships — there
 * is no path from a text field to a remote image.
 *
 * The vendors whose **real** artwork the app ships are deliberately absent
 * from this map — see `BrandMarks`. `QuickApps` draws those components instead
 * of a silhouette, and their keys join this allowlist at the bottom.
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

export const QUICK_ACCESS_ICON_KEYS: readonly string[] = [
  ...Object.keys(QUICK_ACCESS_ICONS),
  ...BRAND_MARK_KEYS,
];

export function quickAccessIcon(key: string): LucideIcon {
  return QUICK_ACCESS_ICONS[key] ?? AppWindow;
}
