import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  FileText,
  FolderOpen,
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
    title: "Office inventory",
    href: routes.coming_soon("office-inventory"),
    icon: Building2,
  },
  {
    title: "My reservations",
    href: routes.coming_soon("my-reservations"),
    icon: CalendarDays,
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
