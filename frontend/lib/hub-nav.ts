import type { LucideIcon } from "lucide-react";
import {
  ArrowLeftRight,
  BookOpen,
  Boxes,
  Briefcase,
  Building2,
  CalendarCheck,
  CalendarDays,
  ClipboardList,
  FileText,
  FileUser,
  FolderOpen,
  GraduationCap,
  Headphones,
  Landmark,
  LayoutDashboard,
  ListTodo,
  Megaphone,
  MessageSquareText,
  Shield,
  ShieldCheck,
  UserCog,
  UserPlus,
  UserRoundSearch,
  Users,
  Warehouse,
} from "lucide-react";

import { hasPermission, type PermissionCheck } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import type { HubFeatures, PrimaryOffice, User } from "@/types";

/**
 * Why an item cannot be used yet. `null` means it is live.
 *
 *   "feature"    — the module has no route yet (web.navigation.HUB_FEATURES)
 *   "no-office"  — the destination needs an office and the user has none
 */
export type HubNavUnavailable = "feature" | "no-office" | null;

export interface HubNavItem {
  /** Stable identity. Dedupe and tests key on this, never on the label. */
  key: string;
  title: string;
  href: string;
  icon: LucideIcon;
  /** Effective-permission requirement; omitted means every signed-in user. */
  permission?: PermissionCheck;
  /**
   * Hub section slug in `HUB_FEATURES`. Present while the module is unbuilt;
   * drop it in the commit that gives the item a real route.
   */
  feature?: string;
  /** Destination reads the user's own office, so it needs one to exist. */
  requiresOffice?: boolean;
  /** Base paths that keep this item active across list/detail/create routes. */
  activePrefixes?: string[];
  /** More specific sibling paths that must not activate this item. */
  activeExclusions?: string[];
  /** Optional label used to divide a large group without creating another nav. */
  subsection?: string;
}

export interface HubNavGroup {
  /** Section label above the group. */
  label: string;
  items: HubNavItem[];
}

/** A registry item resolved against the current user, features, and office. */
export interface ResolvedHubNavItem extends HubNavItem {
  unavailable: HubNavUnavailable;
}

export interface ResolvedHubNavGroup {
  label: string;
  items: ResolvedHubNavItem[];
}

export const HUB_PRIMARY_NAV: HubNavItem[] = [
  {
    key: "dashboard",
    title: "Dashboard",
    href: routes.dashboard(),
    icon: LayoutDashboard,
  },
  {
    key: "agent-profile",
    title: "Agent profile",
    href: routes.profile(),
    icon: Briefcase,
  },
  {
    key: "my-contract",
    title: "My contract",
    href: routes.coming_soon("my-contract"),
    icon: FileText,
    feature: "my-contract",
  },
  {
    key: "agent-transactions",
    title: "Agent transactions",
    href: routes.coming_soon("agent-transactions"),
    icon: ClipboardList,
    feature: "agent-transactions",
  },
  {
    key: "my-reservations",
    title: "My reservations",
    href: routes.coming_soon("my-reservations"),
    icon: CalendarDays,
    feature: "my-reservations",
  },
];

export const HUB_APP_NAV: HubNavItem[] = [
  {
    key: "training-learning",
    title: "Training & learning",
    href: routes.coming_soon("training-learning"),
    icon: BookOpen,
    feature: "training-learning",
  },
  {
    key: "documents-forms",
    title: "Documents & forms",
    href: routes.coming_soon("documents-forms"),
    icon: FolderOpen,
    feature: "documents-forms",
  },
  {
    key: "marketing-resources",
    title: "Marketing resources",
    href: routes.coming_soon("marketing-resources"),
    icon: Megaphone,
    feature: "marketing-resources",
  },
  {
    key: "policies-compliance",
    title: "Policies & compliance",
    href: routes.coming_soon("policies-compliance"),
    icon: Shield,
    feature: "policies-compliance",
  },
];

export const HUB_OFFICE_NAV: HubNavItem[] = [
  {
    key: "office-info",
    title: "Office info",
    href: routes.coming_soon("office-info"),
    icon: Landmark,
    feature: "office-info",
    requiresOffice: true,
  },
  {
    key: "office-resources",
    title: "Office resources",
    href: routes.coming_soon("office-resources"),
    icon: Boxes,
    feature: "office-resources",
    requiresOffice: true,
  },
  {
    key: "office-inventory",
    title: "Office inventory",
    href: routes.coming_soon("office-inventory"),
    icon: Building2,
    feature: "office-inventory",
    requiresOffice: true,
  },
];

export const HUB_DIRECTORY_NAV: HubNavItem[] = [
  {
    key: "agent-directory",
    title: "Agent directory",
    href: routes.coming_soon("agent-directory"),
    icon: Users,
    feature: "agent-directory",
  },
];

export const HUB_ADMIN_NAV: HubNavItem[] = [
  {
    key: "admin-users",
    title: "Users",
    href: routes.admin_users(),
    icon: Users,
    permission: { all: ["web.view_users"] },
    feature: "admin-users",
    activePrefixes: [routes.admin_users()],
    activeExclusions: [routes.admin_add_user()],
    subsection: "People",
  },
  {
    key: "admin-new-agents",
    title: "New Agent List",
    href: routes.admin_new_agents(),
    icon: UserRoundSearch,
    permission: { all: ["web.view_new_agents"] },
    feature: "admin-new-agents",
    subsection: "People",
  },
  {
    key: "admin-add-user",
    title: "Add New User",
    href: routes.admin_add_user(),
    icon: UserPlus,
    permission: { all: ["web.add_users"] },
    feature: "admin-add-user",
    subsection: "People",
  },
  {
    key: "admin-assign-roles",
    title: "Assign User Roles",
    href: routes.admin_assign_roles(),
    icon: UserCog,
    permission: { all: ["web.assign_user_roles"] },
    feature: "admin-assign-roles",
    subsection: "People",
  },
  {
    key: "admin-agent-contracts",
    title: "Agent Contracts",
    href: routes.admin_agent_contracts(),
    icon: FileUser,
    permission: { all: ["web.view_agent_contracts"] },
    feature: "admin-agent-contracts",
    subsection: "People",
  },
  {
    key: "admin-transactions",
    title: "Transactions",
    href: routes.admin_transactions(),
    icon: ArrowLeftRight,
    permission: { all: ["web.view_transactions"] },
    feature: "admin-transactions",
    subsection: "Operations",
  },
  {
    key: "admin-inventory",
    title: "Inventory",
    href: routes.admin_inventory(),
    icon: Warehouse,
    permission: { all: ["web.view_inventory"] },
    feature: "admin-inventory",
    subsection: "Operations",
  },
  {
    key: "admin-reservations",
    title: "Reservations",
    href: routes.admin_reservations(),
    icon: CalendarCheck,
    permission: { all: ["web.view_reservations"] },
    feature: "admin-reservations",
    subsection: "Operations",
  },
  {
    key: "admin-announcements",
    title: "Announcements",
    href: routes.admin_announcements(),
    icon: Megaphone,
    permission: { all: ["web.manage_announcements"] },
    feature: "admin-announcements",
    subsection: "Content",
  },
  {
    key: "admin-training",
    title: "Training",
    href: routes.admin_training(),
    icon: GraduationCap,
    permission: { all: ["web.manage_training"] },
    feature: "admin-training",
    subsection: "Content",
  },
  {
    key: "admin-documents",
    title: "Documents",
    href: routes.admin_documents(),
    icon: FolderOpen,
    permission: { all: ["web.manage_documents"] },
    feature: "admin-documents",
    subsection: "Content",
  },
  {
    key: "admin-compliance",
    title: "Compliance",
    href: routes.admin_compliance(),
    icon: ShieldCheck,
    permission: { all: ["web.view_compliance"] },
    feature: "admin-compliance",
    subsection: "Governance & support",
  },
  {
    key: "admin-feedback",
    title: "Feedback",
    href: routes.admin_feedback(),
    icon: MessageSquareText,
    permission: { all: ["web.view_feedback"] },
    feature: "admin-feedback",
    subsection: "Governance & support",
  },
  {
    key: "admin-platform-tasks",
    title: "Platform Tasks",
    href: routes.admin_platform_tasks(),
    icon: ListTodo,
    permission: { all: ["web.view_platform_tasks"] },
    feature: "admin-platform-tasks",
    subsection: "Governance & support",
  },
  {
    key: "admin-offices",
    title: "Offices",
    href: routes.admin_offices(),
    icon: Building2,
    permission: { all: ["web.manage_offices"] },
    feature: "admin-offices",
    subsection: "Governance & support",
  },
  {
    key: "admin-it-support",
    title: "IT Support",
    href: routes.admin_it_support(),
    icon: Headphones,
    permission: { all: ["web.view_it_support"] },
    feature: "admin-it-support",
    subsection: "Governance & support",
  },
];

/**
 * The approved combined information architecture. Group and item order here is
 * the order everywhere — desktop, collapsed rail, and mobile drawer all render
 * this one array, so agent and administrative navigation cannot drift apart.
 */
export const HUB_NAV_GROUPS: HubNavGroup[] = [
  { label: "General", items: HUB_PRIMARY_NAV },
  { label: "Tools", items: HUB_APP_NAV },
  { label: "My office", items: HUB_OFFICE_NAV },
  { label: "Directory", items: HUB_DIRECTORY_NAV },
  { label: "Administration", items: HUB_ADMIN_NAV },
];

export function isHubNavItemActive(item: HubNavItem, current: string): boolean {
  const path = current.split("?")[0];
  const matches = (prefix: string) => path === prefix || path.startsWith(`${prefix}/`);
  if (item.activeExclusions?.some(matches)) {
    return false;
  }
  return (item.activePrefixes ?? [item.href]).some(matches);
}

function unavailableReason(
  item: HubNavItem,
  features: HubFeatures,
  primaryOffice: PrimaryOffice | null,
): HubNavUnavailable {
  // A missing feature key means the item is built; an unknown key is treated
  // as unbuilt so a typo hides a link rather than shipping a 404.
  if (item.feature !== undefined && features[item.feature] !== true) {
    return "feature";
  }
  if (item.requiresOffice && primaryOffice === null) {
    return "no-office";
  }
  return null;
}

/**
 * Resolve the registry for one user.
 *
 * Permission-filtered, deduplicated by `key` (a user holding both manager and
 * agent roles gets one list, not two), annotated with why an item is not usable
 * yet, and stripped of groups that ended up empty. Visibility is presentation
 * only — every destination is enforced again server-side by
 * `apps/web/authorization.py`.
 *
 * `registry` defaults to the approved structure; it is a parameter so the
 * filtering rules can be tested against a stand-in that declares permissions
 * the shipped registry does not need yet.
 */
export function resolveHubNav(
  user: User | null,
  features: HubFeatures = {},
  primaryOffice: PrimaryOffice | null = null,
  registry: HubNavGroup[] = HUB_NAV_GROUPS,
): ResolvedHubNavGroup[] {
  const seen = new Set<string>();
  const groups: ResolvedHubNavGroup[] = [];
  for (const group of registry) {
    const items: ResolvedHubNavItem[] = [];
    for (const item of group.items) {
      if (seen.has(item.key) || !hasPermission(user, item.permission)) {
        continue;
      }
      seen.add(item.key);
      items.push({
        ...item,
        unavailable: unavailableReason(item, features, primaryOffice),
      });
    }
    // An empty group would leave a heading with nothing under it.
    if (items.length > 0) {
      groups.push({ label: group.label, items });
    }
  }
  return groups;
}

/** Short marker shown beside an item that cannot be opened yet. */
export function unavailableLabel(reason: HubNavUnavailable): string | null {
  switch (reason) {
    case "feature":
      return "Soon";
    case "no-office":
      return "No office";
    default:
      return null;
  }
}

/** Sentence read by assistive tech in place of the bare marker. */
export function unavailableDescription(item: ResolvedHubNavItem): string | null {
  switch (item.unavailable) {
    case "feature":
      return `${item.title} is not available yet`;
    case "no-office":
      return `${item.title} needs an office on your profile`;
    default:
      return null;
  }
}
