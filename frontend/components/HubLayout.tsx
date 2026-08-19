import { Link, router, usePage } from "@inertiajs/react";
import {
  Bell,
  ChevronDown,
  CircleHelp,
  LogOut,
  Palette,
  Plus,
  Settings,
  UserRound,
} from "lucide-react";
import {
  type CSSProperties,
  type FormEvent,
  type ReactNode,
  useEffect,
  useState,
} from "react";

import { BrandMark } from "@/components/BrandMark";
import { SearchControl } from "@/components/design-system/search-control";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  HUB_NAV_EXPANSION_STORAGE_KEY,
  HUB_NAV_SECTIONS,
  type HubNavSectionKey,
  hubNavItemDescription,
  isHubNavItemActive,
  parseHubNavExpansion,
  type ResolvedHubNavGroup,
  type ResolvedHubNavItem,
  resolveHubNav,
  resolveHubNavSections,
} from "@/lib/hub-nav";
import { routes } from "@/lib/routes";
import type { PageProps, User } from "@/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function firstName(name: string): string {
  return name.split(/\s+/).filter(Boolean)[0] ?? name;
}

function roleSummary(
  roles: string[] | undefined,
  roleLabel: string | undefined,
): string {
  if (!roles || roles.length === 0) {
    return roleLabel ?? "Agent";
  }
  if (roles.length === 1) {
    return roleLabel ?? roles[0];
  }
  return `${roleLabel ?? roles[0]} +${roles.length - 1}`;
}

function storedExpansionState(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(HUB_NAV_EXPANSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function NavList({ items, current }: { items: ResolvedHubNavItem[]; current: string }) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const active = isHubNavItemActive(item, current);
        const description = hubNavItemDescription(item);
        const noteId = description ? `hub-nav-${item.key}-note` : undefined;
        return (
          <SidebarMenuItem key={item.key}>
            <SidebarMenuButton
              asChild
              isActive={active}
              tooltip={description ?? item.label}
              className="h-9 rounded-lg px-2.5 font-normal transition-[background-color,color] duration-(--motion-fast) data-[active=true]:font-semibold group-data-[collapsible=icon]:rounded-lg"
            >
              <Link
                href={item.route.href}
                aria-current={active ? "page" : undefined}
                aria-describedby={noteId}
              >
                <item.icon
                  className={
                    active
                      ? "text-primary size-[1.125rem] transition-colors"
                      : "text-muted-foreground group-hover/menu-item:text-foreground size-[1.125rem] transition-colors"
                  }
                  strokeWidth={1.5}
                />
                <span className="min-w-0 truncate">{item.label}</span>
                {item.availability === "coming-soon" ? (
                  <span
                    aria-hidden
                    className="text-muted-foreground ml-auto shrink-0 text-[0.6875rem] group-data-[collapsible=icon]:hidden"
                  >
                    Soon
                  </span>
                ) : null}
                {description ? (
                  <span id={noteId} className="sr-only">
                    {description}
                  </span>
                ) : null}
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}

function NavGroupItems({
  group,
  current,
  expandedSections,
  onSectionToggle,
}: {
  group: ResolvedHubNavGroup;
  current: string;
  expandedSections: Set<HubNavSectionKey>;
  onSectionToggle: (section: HubNavSectionKey, active: boolean) => void;
}) {
  const sections = resolveHubNavSections(group);
  if (sections.length === 0) {
    return <NavList items={group.items} current={current} />;
  }

  const rootItems = group.items.filter((item) => !item.section);

  return (
    <div className="grid gap-2">
      {rootItems.length > 0 ? <NavList items={rootItems} current={current} /> : null}
      {sections.map((section) => {
        const active = section.items.some((item) => isHubNavItemActive(item, current));
        const open = expandedSections.has(section.key) || active;
        const panelId = `hub-nav-section-${section.key}`;
        return (
          <section key={section.key} aria-label={section.label}>
            <button
              type="button"
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => onSectionToggle(section.key, active)}
              className="text-muted-foreground hover:text-foreground focus-visible:ring-sidebar-ring flex w-full items-center gap-2 rounded-md px-2.5 pt-1 pb-1 text-left text-[0.6875rem] font-medium tracking-[0.02em] focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:hidden"
            >
              <span className="min-w-0 flex-1 truncate">{section.label}</span>
              <ChevronDown
                aria-hidden
                className={`size-3.5 shrink-0 transition-transform motion-reduce:transition-none ${
                  open ? "rotate-0" : "-rotate-90"
                }`}
                strokeWidth={1.5}
              />
            </button>
            <div
              id={panelId}
              className={
                open ? undefined : "hidden group-data-[collapsible=icon]:block"
              }
            >
              <NavList items={section.items} current={current} />
            </div>
          </section>
        );
      })}
    </div>
  );
}

/**
 * Header affordances whose backend does not exist yet. `aria-disabled` rather
 * than `disabled` so the control keeps focus and can still explain itself —
 * a dead control that looks live is worse than one that says it is not ready.
 */
function PendingAction({
  label,
  note,
  children,
}: {
  label: string;
  note: string;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`${label} — ${note}`}
          aria-disabled
          className="text-muted-foreground size-9"
          onClick={(event) => event.preventDefault()}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{note}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Signed-in identity at the foot of the rail: who you are, and the one action
 * that ends the session. The name block is a link to the profile rather than a
 * menu — a second dropdown holding the same items as the header one would make
 * the reader choose between two identical doors.
 *
 * No card. The rule above it is the whole separation, matching the flush,
 * border-driven seam the workspace uses everywhere else; a filled, rounded
 * panel at the foot of a rail that is otherwise one column of type would be
 * the only floating object on the screen. Radius survives on the hover target
 * alone, because a square hover wash reads as a rendering bug next to the
 * rounded nav rows directly above it.
 *
 * Collapsed, it degrades to the avatar alone; sign-out stays reachable from the
 * header menu, which is the only copy that survives at that width.
 */
function SidebarAccount({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  return (
    <div className="flex items-center gap-1">
      <Link
        href={routes.profile()}
        className="hover:bg-sidebar-accent/50 focus-visible:ring-sidebar-ring flex min-w-0 flex-1 items-center gap-2.5 rounded-md px-1.5 py-1.5 transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
      >
        <Avatar className="size-8 shrink-0">
          <AvatarFallback className="brand-surface text-xs font-semibold">
            {initials(user.name)}
          </AvatarFallback>
        </Avatar>
        <span className="min-w-0 flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
          <span className="block truncate text-sm font-medium">{user.name}</span>
          <span className="text-muted-foreground block truncate text-xs">
            {user.email}
          </span>
        </span>
      </Link>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Sign out ${firstName(user.name)}`}
            onClick={onSignOut}
            className="text-muted-foreground hover:text-foreground size-9 shrink-0 group-data-[collapsible=icon]:hidden"
          >
            <LogOut className="size-4" strokeWidth={1.5} />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Sign out</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function HubLayout({ children }: { children: ReactNode }) {
  const page = usePage<PageProps>();
  const { user, features, primaryOffice } = page.props;
  const current = page.url.split("?")[0];
  const navGroups = resolveHubNav(user, features, primaryOffice);
  const [expandedSections, setExpandedSections] = useState<Set<HubNavSectionKey>>(() =>
    parseHubNavExpansion(storedExpansionState()),
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(
        HUB_NAV_EXPANSION_STORAGE_KEY,
        JSON.stringify([...expandedSections].sort()),
      );
    } catch {
      // Storage can be disabled by browser policy; navigation stays usable.
    }
  }, [expandedSections]);

  function toggleSection(section: HubNavSectionKey, containsActiveItem: boolean) {
    if (containsActiveItem) {
      return;
    }
    setExpandedSections((currentSections) => {
      const next = new Set(currentSections);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      const known = new Set(HUB_NAV_SECTIONS.map((item) => item.key));
      return new Set([...next].filter((item) => known.has(item)));
    });
  }

  function signOut() {
    router.post(routes.logout());
  }

  function handleLogout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    signOut();
  }

  const name = user?.name ?? "Agent";
  const role = roleSummary(user?.roles, user?.roleLabel);

  return (
    // Long operational labels and their quiet Soon marker remain readable at
    // supported widths without crowding their icons.
    <SidebarProvider style={{ "--sidebar-width": "17.5rem" } as CSSProperties}>
      {/* First focusable element on the page — before the whole nav list. */}
      <a
        href="#hub-content"
        className="bg-card text-foreground focus-visible:ring-ring sr-only rounded-md px-4 py-2 text-sm font-medium shadow-sm focus-visible:fixed focus-visible:top-3 focus-visible:left-3 focus-visible:z-50 focus-visible:not-sr-only focus-visible:ring-2"
      >
        Skip to content
      </a>
      <Sidebar collapsible="icon" className="border-sidebar-border/70">
        {/* Collapsed, the rail keeps only the expand control — the wordmark has
            no room and the mark alone would read as a dead button beside it. */}
        <SidebarHeader className="h-16 flex-row items-center justify-between gap-1 px-3.5 py-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2">
          <Link
            href={routes.dashboard()}
            className="focus-visible:ring-sidebar-ring flex min-w-0 items-center gap-2.5 rounded-md py-1 focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:hidden"
            aria-label="ONEST HUB home"
          >
            <span className="brand-surface shadow-xs grid size-8 shrink-0 place-items-center rounded-lg">
              <BrandMark className="size-5" />
            </span>
            <span className="truncate text-sm font-bold tracking-[-0.025em]">
              ONEST HUB
            </span>
          </Link>
          <SidebarTrigger className="text-muted-foreground hidden size-8 md:flex" />
        </SidebarHeader>
        <SidebarContent className="gap-0 overflow-x-hidden">
          {/* Group labels carry the separation. Rules between them would add a
              second divider to a rail that is already one column of type. */}
          <nav aria-label="Hub sections" className="flex min-h-0 flex-col">
            {navGroups.map((group) => (
              <SidebarGroup
                key={group.label}
                className="px-2.5 pt-4 pb-0 group-data-[collapsible=icon]:px-1.5"
              >
                <SidebarGroupLabel className="text-muted-foreground h-6 px-2.5 text-[0.6875rem] font-semibold tracking-[0.09em] uppercase">
                  {group.label}
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <NavGroupItems
                    group={group}
                    current={current}
                    expandedSections={expandedSections}
                    onSectionToggle={toggleSection}
                  />
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </nav>
        </SidebarContent>
        {/* The wordmark in the header already names the company; under a real
            account row a second "oNEST Real Estate" line was just filler.
            This rule is the one divider in the rail — group labels carry the
            separation above it, but the account is a different kind of thing
            from a destination and earns the seam. */}
        <SidebarFooter className="border-sidebar-border/70 mt-2 border-t px-2.5 py-2.5 group-data-[collapsible=icon]:px-1.5">
          {user ? <SidebarAccount user={user} onSignOut={signOut} /> : null}
        </SidebarFooter>
      </Sidebar>
      {/* Flush, not a floating card: the workspace runs to the top and right
          edges of the window, and the sidebar's own border is the only seam. */}
      <SidebarInset>
        <header className="bg-background/92 sticky top-0 z-10 flex h-16 items-center gap-2 border-b px-4 backdrop-blur-xl lg:px-6">
          <SidebarTrigger className="md:hidden" />
          <Tooltip>
            {/* The wrapper carries the tooltip: a disabled input fires no
                pointer events of its own. */}
            <TooltipTrigger asChild>
              <div className="hidden w-full max-w-sm min-w-0 md:block">
                <SearchControl
                  label="Search across ONEST"
                  placeholder="Search clients, properties, and documents"
                  disabled
                  tone="subtle"
                  size="sm"
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>Search arrives with the next release</TooltipContent>
          </Tooltip>
          <div className="ml-auto flex items-center gap-0.5">
            <PendingAction label="Help" note="Help centre is not wired up yet">
              <CircleHelp className="size-5" strokeWidth={1.5} />
            </PendingAction>
            <PendingAction
              label="Notifications"
              note="Notifications are not wired up yet"
            >
              <Bell className="size-5" strokeWidth={1.5} />
            </PendingAction>
            <PendingAction label="Create new" note="Quick create is not wired up yet">
              <Plus className="size-5" strokeWidth={1.5} />
            </PendingAction>
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="ml-1.5 h-10 gap-2 rounded-full px-1 lg:pr-3"
                  >
                    <Avatar className="size-8">
                      <AvatarFallback className="brand-surface text-xs font-semibold">
                        {initials(name)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden min-w-0 text-left leading-tight lg:block">
                      <span className="block truncate text-sm font-medium">{name}</span>
                      <span className="text-muted-foreground block truncate text-xs">
                        {role}
                      </span>
                    </span>
                    <span className="sr-only">{firstName(name)} account menu</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuLabel className="font-normal">
                    <p className="text-sm font-medium">{name}</p>
                    <p className="text-muted-foreground truncate text-xs">
                      {user.email}
                    </p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link href={routes.profile()}>
                      <UserRound className="size-4" strokeWidth={1.5} />
                      Profile
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href={routes.design_system()}>
                      <Palette className="size-4" strokeWidth={1.5} />
                      Design system
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem disabled>
                    <Settings className="size-4" strokeWidth={1.5} />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => {
                      const form = document.getElementById(
                        "hub-logout",
                      ) as HTMLFormElement;
                      form?.requestSubmit();
                    }}
                  >
                    <LogOut className="size-4" strokeWidth={1.5} />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            <form id="hub-logout" className="hidden" onSubmit={handleLogout} />
          </div>
        </header>
        <div id="hub-content" className="flex flex-1 flex-col">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
