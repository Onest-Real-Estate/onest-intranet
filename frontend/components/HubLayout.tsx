import { Link, router, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  ChevronDown,
  CircleHelp,
  LogOut,
  Palette,
  Plus,
  RefreshCw,
  Settings,
  UserRound,
  WifiOff,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/BrandMark";
import { SearchControl } from "@/components/design-system/search-control";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
  useSidebar,
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
import { cn } from "@/lib/utils";
import type { PageProps, User } from "@/types";

export type HubLayoutVariant = "standard" | "wide" | "focused";

export interface HubBreadcrumb {
  label: string;
  href?: string;
}

export interface HubPageContext {
  title: string;
  breadcrumbs?: HubBreadcrumb[];
  back?: {
    label: string;
    href: string;
  };
}

export interface HubLayoutProps {
  children: ReactNode;
  context?: HubPageContext;
  variant?: HubLayoutVariant;
}

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

function UserAvatar({ user, className }: { user: User; className?: string }) {
  return (
    <Avatar className={className}>
      {user.headshotUrl ? (
        <AvatarImage key={user.headshotUrl} src={user.headshotUrl} alt="" />
      ) : null}
      <AvatarFallback className="brand-surface text-xs font-semibold">
        {initials(user.name)}
      </AvatarFallback>
    </Avatar>
  );
}

function roleSummary(
  roles: string[] | undefined,
  roleLabel: string | undefined,
): string {
  if (!roles || roles.length === 0) {
    return roleLabel ?? "Realtor";
  }
  if (roles.length === 1) {
    return roleLabel ?? roles[0];
  }
  return `${roleLabel ?? roles[0]} +${roles.length - 1}`;
}

function safeInternalHref(href: string): string {
  return href.startsWith("/") && !href.startsWith("//") ? href : routes.dashboard();
}

const contentVariants: Record<HubLayoutVariant, string> = {
  standard: "page-shell",
  wide: "mx-auto w-full max-w-[1600px] px-4 sm:px-6 lg:px-8",
  focused: "mx-auto w-full max-w-2xl px-4 sm:px-6",
};

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
        <UserAvatar user={user} className="size-8 shrink-0" />
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

type ShellFailure = "network" | "server" | "session" | null;

function ShellFeedback({
  failure,
  onRetry,
}: {
  failure: ShellFailure;
  onRetry: () => void;
}) {
  if (!failure) {
    return null;
  }
  const sessionExpired = failure === "session";
  const networkFailure = failure === "network";
  const Icon = networkFailure ? WifiOff : AlertTriangle;
  const title = sessionExpired
    ? "Your session has expired"
    : networkFailure
      ? "You’re offline"
      : "ONEST couldn’t load that page";
  const description = sessionExpired
    ? "Sign in again to continue. Your current page will stay here until you do."
    : networkFailure
      ? "Check your connection, then try the request again."
      : "The service returned an unexpected response. Your current page is still available.";

  return (
    <div role="alert" className="bg-card border-b px-4 py-3 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1600px] items-start gap-3">
        <Icon aria-hidden className="text-destructive mt-0.5 size-4" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-muted-foreground mt-0.5 text-xs leading-5">
            {description}
          </p>
        </div>
        {sessionExpired ? (
          <Button asChild size="sm" className="shrink-0">
            <a href={routes.login()}>Sign in again</a>
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={onRetry}
          >
            <RefreshCw aria-hidden className="size-4" />
            <span>Try again</span>
          </Button>
        )}
      </div>
    </div>
  );
}

function PageContext({ context }: { context: HubPageContext }) {
  const breadcrumbs = context.breadcrumbs ?? [];
  return (
    <div className="min-w-0 flex-1">
      {breadcrumbs.length ? (
        <nav
          aria-label="Breadcrumb"
          className="text-muted-foreground hidden min-w-0 text-[0.6875rem] sm:block"
        >
          <ol className="flex min-w-0 items-center gap-1.5 overflow-hidden">
            {breadcrumbs.map((item, index) => {
              const current = index === breadcrumbs.length - 1;
              return (
                <li
                  key={`${item.href ?? "current"}:${item.label}`}
                  className="flex min-w-0 items-center gap-1.5"
                >
                  {index > 0 ? <span aria-hidden>/</span> : null}
                  {item.href && !current ? (
                    <Link
                      href={safeInternalHref(item.href)}
                      className="hover:text-foreground focus-visible:ring-ring truncate rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                    >
                      {item.label}
                    </Link>
                  ) : (
                    <span
                      aria-current={current ? "page" : undefined}
                      className="truncate"
                    >
                      {item.label}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      ) : null}
      <p className="truncate text-sm font-semibold tracking-[-0.01em]">
        {context.title}
      </p>
    </div>
  );
}

function ShellWorkspace({
  authorizationVersion,
  children,
  context,
  helpUrl,
  notifications,
  primaryOffice,
  role,
  user,
  variant,
  onSignOut,
}: {
  authorizationVersion: string;
  children: ReactNode;
  context: HubPageContext;
  helpUrl: string | null;
  notifications: PageProps["notifications"];
  primaryOffice: PageProps["primaryOffice"];
  role: string;
  user: User | null;
  variant: HubLayoutVariant;
  onSignOut: () => void;
}) {
  const { isMobile, openMobile, setOpenMobile } = useSidebar();
  const [navigating, setNavigating] = useState(false);
  const [failure, setFailure] = useState<ShellFailure>(null);
  const previousAuthorizationVersion = useRef(authorizationVersion);
  const previousMobileOpen = useRef(openMobile);
  const navigationFocusPending = useRef(false);

  useEffect(() => {
    if (previousAuthorizationVersion.current !== authorizationVersion) {
      setOpenMobile(false);
      previousAuthorizationVersion.current = authorizationVersion;
    }
  }, [authorizationVersion, setOpenMobile]);

  useEffect(() => {
    const drawerClosed = previousMobileOpen.current && !openMobile;
    previousMobileOpen.current = openMobile;
    if (drawerClosed && isMobile && !navigationFocusPending.current) {
      window.requestAnimationFrame(() => {
        document
          .querySelector<HTMLElement>('header [data-sidebar="trigger"]')
          ?.focus({ preventScroll: true });
      });
    }
  }, [isMobile, openMobile]);

  useEffect(() => {
    const removeStart = router.on("start", () => {
      setFailure(null);
      setNavigating(true);
      setOpenMobile(false);
    });
    const removeFinish = router.on("finish", () => setNavigating(false));
    const removeNavigate = router.on("navigate", () => {
      navigationFocusPending.current = true;
      setFailure(null);
      setNavigating(false);
      setOpenMobile(false);
      window.requestAnimationFrame(() => {
        document.getElementById("hub-content")?.focus({ preventScroll: true });
        navigationFocusPending.current = false;
      });
    });
    const removeNetworkError = router.on("networkError", (event) => {
      const error = event.detail.error;
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
      setNavigating(false);
      setFailure("network");
      return false;
    });
    const removeHttpException = router.on("httpException", (event) => {
      const status = event.detail.response.status;
      if (status === 401 || status === 419) {
        setFailure("session");
      } else if (status >= 500) {
        setFailure("server");
      } else {
        return;
      }
      setNavigating(false);
      return false;
    });
    return () => {
      removeStart();
      removeFinish();
      removeNavigate();
      removeNetworkError();
      removeHttpException();
    };
  }, [setOpenMobile]);

  function retry() {
    setFailure(null);
    router.reload({ fresh: true });
  }

  return (
    <SidebarInset>
      <header className="bg-background/92 sticky top-0 z-10 flex h-16 items-center gap-1.5 border-b px-3 backdrop-blur-xl sm:gap-2 sm:px-4 lg:px-6">
        <SidebarTrigger className="md:hidden" />
        {context.back ? (
          <Button variant="ghost" size="icon" asChild className="size-9 shrink-0">
            <Link
              href={safeInternalHref(context.back.href)}
              aria-label={context.back.label}
            >
              <ArrowLeft aria-hidden className="size-4" />
            </Link>
          </Button>
        ) : null}
        <PageContext context={context} />
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="hidden w-full max-w-sm min-w-0 xl:block">
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
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          {helpUrl ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button asChild variant="ghost" size="icon" className="size-9">
                  <a
                    href={helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Open help centre in a new tab"
                  >
                    <CircleHelp aria-hidden className="size-5" />
                  </a>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Help centre</TooltipContent>
            </Tooltip>
          ) : (
            <PendingAction label="Help" note="Help centre is not wired up yet">
              <CircleHelp className="size-5" strokeWidth={1.5} />
            </PendingAction>
          )}
          <NotificationBell summary={notifications} />
          <PendingAction label="Create new" note="Quick create is not wired up yet">
            <Plus className="size-5" strokeWidth={1.5} />
          </PendingAction>
          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="ml-1 h-10 max-w-52 gap-2 rounded-full px-1 lg:pr-3"
                  aria-label={`${firstName(user.name)} account menu`}
                >
                  <UserAvatar user={user} className="size-8" />
                  <span className="hidden min-w-0 text-left leading-tight lg:block">
                    <span className="block truncate text-sm font-medium">
                      {user.name}
                    </span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {role}
                    </span>
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuLabel className="min-w-0 font-normal">
                  <p className="truncate text-sm font-medium">{user.name}</p>
                  <p className="text-muted-foreground truncate text-xs">{user.email}</p>
                </DropdownMenuLabel>
                {primaryOffice ? (
                  <div className="text-muted-foreground flex min-w-0 items-start gap-2 px-2 py-2 text-xs">
                    <Building2 aria-hidden className="mt-0.5 size-4" />
                    <span className="min-w-0">
                      <span className="text-foreground block truncate font-medium">
                        {primaryOffice.name}
                      </span>
                      <span className="block truncate">{primaryOffice.regionName}</span>
                    </span>
                  </div>
                ) : null}
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
                <DropdownMenuItem variant="destructive" onSelect={onSignOut}>
                  <LogOut className="size-4" strokeWidth={1.5} />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </header>
      <ShellFeedback failure={failure} onRetry={retry} />
      <p role="status" aria-live="polite" className="sr-only">
        {navigating ? "Loading page" : ""}
      </p>
      <div
        id="hub-content"
        tabIndex={-1}
        aria-busy={navigating}
        className={cn(
          "flex flex-1 flex-col py-6 outline-none lg:py-8",
          contentVariants[variant],
        )}
      >
        {children}
      </div>
    </SidebarInset>
  );
}

export function HubLayout({ children, context, variant = "standard" }: HubLayoutProps) {
  const page = usePage<PageProps>();
  const { user, features, primaryOffice, notifications } = page.props;
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
  const role = roleSummary(user?.roles, user?.roleLabel);
  const activeItem = navGroups
    .flatMap((group) => group.items)
    .find((item) => isHubNavItemActive(item, current));
  const resolvedContext = context ?? {
    title: activeItem?.label ?? "ONEST HUB",
  };

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
      <ShellWorkspace
        authorizationVersion={page.props.shell?.authorizationVersion ?? ""}
        context={resolvedContext}
        helpUrl={page.props.shell?.help.url ?? null}
        notifications={notifications}
        primaryOffice={primaryOffice}
        role={role}
        user={user}
        variant={variant}
        onSignOut={signOut}
      >
        {children}
      </ShellWorkspace>
    </SidebarProvider>
  );
}
