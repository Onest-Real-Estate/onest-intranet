import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Boxes,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  FileText,
  FolderOpen,
  Landmark,
  LayoutDashboard,
  Megaphone,
  Shield,
  Users,
} from "lucide-react";

import { routes } from "@/lib/routes";

export interface HubNavItem {
  title: string;
  href: string;
  icon: LucideIcon;
}

export interface HubNavGroup {
  /** Section label above the group; omit for an unlabelled lead group. */
  label: string;
  items: HubNavItem[];
}

/**
 * Every `coming_soon` destination lives under /hub/, so the "Soon" marker in
 * the sidebar is derived rather than maintained by hand — a section that gains
 * a real route stops advertising itself as unbuilt automatically.
 */
export function isComingSoon(href: string): boolean {
  return href.startsWith("/hub/");
}

export const HUB_PRIMARY_NAV: HubNavItem[] = [
  { title: "Dashboard", href: routes.dashboard(), icon: LayoutDashboard },
  { title: "Agent profile", href: routes.profile(), icon: Briefcase },
  { title: "My contract", href: routes.coming_soon("my-contract"), icon: FileText },
  {
    title: "Agent transactions",
    href: routes.coming_soon("agent-transactions"),
    icon: ClipboardList,
  },
  {
    title: "My reservations",
    href: routes.coming_soon("my-reservations"),
    icon: CalendarDays,
  },
];

export const HUB_OFFICE_NAV: HubNavItem[] = [
  { title: "Office info", href: routes.coming_soon("office-info"), icon: Landmark },
  {
    title: "Office resources",
    href: routes.coming_soon("office-resources"),
    icon: Boxes,
  },
  {
    title: "Office inventory",
    href: routes.coming_soon("office-inventory"),
    icon: Building2,
  },
];

export const HUB_APP_NAV: HubNavItem[] = [
  {
    title: "Training & learning",
    href: routes.coming_soon("training-learning"),
    icon: BookOpen,
  },
  {
    title: "Documents & forms",
    href: routes.coming_soon("documents-forms"),
    icon: FolderOpen,
  },
  {
    title: "Marketing resources",
    href: routes.coming_soon("marketing-resources"),
    icon: Megaphone,
  },
  {
    title: "Policies & compliance",
    href: routes.coming_soon("policies-compliance"),
    icon: Shield,
  },
];

export const HUB_DIRECTORY_NAV: HubNavItem[] = [
  {
    title: "Agent directory",
    href: routes.coming_soon("agent-directory"),
    icon: Users,
  },
];

export const HUB_NAV_GROUPS: HubNavGroup[] = [
  { label: "General", items: HUB_PRIMARY_NAV },
  { label: "Tools", items: HUB_APP_NAV },
  { label: "My office", items: HUB_OFFICE_NAV },
  { label: "Directory", items: HUB_DIRECTORY_NAV },
];
