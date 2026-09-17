import { Link, router, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Building2,
  ChevronDown,
  CircleHelp,
  ExternalLink,
  Inbox,
  LifeBuoy,
  LogOut,
  Monitor,
  Moon,
  Palette,
  RefreshCw,
  Settings,
  Sun,
  UserRound,
  WifiOff,
  Wrench,
} from "lucide-react";
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { FlashToasts } from "@/components/FlashToasts";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { QuickCreateMenu } from "@/components/QuickCreateMenu";
import { GlobalSearch } from "@/components/search/GlobalSearch";
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
import { useTheme } from "@/hooks/use-theme";
import onestLogo from "@/images/onest-logo.png";
import {
  HUB_NAV_EXPANSION_STORAGE_KEY,
  HUB_NAV_SECTIONS,
  type HubNavSectionKey,
  hubNavItemDescription,
  isHubNavItemActive,
  parseHubNavExpansion,
  partitionByAvailability,
  type ResolvedHubNavGroup,
  type ResolvedHubNavItem,
  resolveHubNav,
  resolveHubNavSections,
} from "@/lib/hub-nav";
import { routes } from "@/lib/routes";
import type { ThemePreference } from "@/lib/theme";
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
              className="h-9 rounded-lg px-2.5 font-normal transition-[background-color,color] duration-(--motion-fast) data-[active=true]:font-medium group-data-[collapsible=icon]:rounded-lg"
            >
              <Link
                href={item.route.href}
                aria-current={active ? "page" : undefined}
                aria-describedby={noteId}
              >
                <item.icon
                  className={
                    active
                      ? "text-primary size-4 transition-colors"
                      : "text-muted-foreground group-hover/menu-item:text-foreground size-4 transition-colors"
                  }
                  strokeWidth={1.5}
                />
                <span className="min-w-0 truncate">{item.label}</span>
                {item.availability === "coming-soon" ? (
                  <span
                    aria-hidden
                    className="text-muted-foreground ml-auto shrink-0 text-micro group-data-[collapsible=icon]:hidden"
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
              className="text-muted-foreground hover:bg-sidebar-accent/55 hover:text-foreground focus-visible:ring-sidebar-ring flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-left text-sm transition-[background-color,color] duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:hidden"
            >
              <span className="min-w-0 flex-1 truncate">{section.label}</span>
              <ChevronDown
                aria-hidden
                className={`size-4 shrink-0 transition-transform duration-(--motion-fast) motion-reduce:transition-none ${
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
              {/* A subsection is a branch of the rail, not a second list that
                  happens to sit lower. The trunk plus a tick per destination
                  says "these belong to the heading above" without a second
                  divider, and both fold away on the icon rail where an indent
                  would only push the icons off-center. */}
              <div className="border-sidebar-border ms-3.5 border-s ps-2.5 group-data-[collapsible=icon]:ms-0 group-data-[collapsible=icon]:border-s-0 group-data-[collapsible=icon]:ps-0 [&_li]:before:absolute [&_li]:before:top-1/2 [&_li]:before:-left-2.5 [&_li]:before:w-2.5 [&_li]:before:border-t [&_li]:before:border-sidebar-border [&_li]:before:content-[''] group-data-[collapsible=icon]:[&_li]:before:hidden">
                <NavList items={section.items} current={current} />
              </div>
            </div>
          </section>
        );
      })}
    </div>
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
const THEME_LABEL: Record<ThemePreference, string> = {
  system: "Match system",
  light: "Light",
  dark: "Dark",
};

const THEME_ICON: Record<ThemePreference, typeof Monitor> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

/**
 * The one control that reaches the dark token set. It cycles rather than opens
 * a menu: three options, each one click away, in a footer that has room for an
 * icon and not for a popover.
 */
function ThemeToggle() {
  const { preference, cycle } = useTheme();
  const Icon = THEME_ICON[preference];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Theme: ${THEME_LABEL[preference].toLowerCase()}. Change theme.`}
          onClick={cycle}
          className="text-muted-foreground hover:text-foreground size-9 shrink-0 group-data-[collapsible=icon]:hidden"
        >
          <Icon className="size-4" strokeWidth={1.5} />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Theme: {THEME_LABEL[preference]}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The pinned help row.
 *
 * Built to the nav rows' own metrics so the rail still reads as one column,
 * and it answers the pointer the same way. Collapsed to the icon rail it keeps
 * a tooltip, because an unlabelled lifebuoy is a guess.
 */
/**
 * What is registered but not built yet, in one row instead of eight.
 *
 * Kept visible because seeing what is coming is the point of registering it,
 * and collapsed because an agent should be able to read their rail as a list
 * of things that work first. The rows keep everything they had — the link to
 * their Coming Soon page, the Soon marker, the spoken description — so this
 * takes nothing away from a reader who goes looking.
 */
function SidebarComingSoon({
  items,
  current,
}: {
  items: ResolvedHubNavItem[];
  current: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="px-2.5 pt-4 group-data-[collapsible=icon]:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-sidebar-ring flex w-full items-center gap-2 rounded-md px-2.5 py-1 text-left text-micro font-semibold tracking-[0.09em] uppercase transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none"
      >
        <span className="min-w-0 flex-1 truncate">Coming soon</span>
        <span className="text-muted-foreground/80 tabular-nums">{items.length}</span>
        <ChevronDown
          aria-hidden
          className={cn(
            "size-3.5 shrink-0 transition-transform duration-(--motion-fast) motion-reduce:transition-none",
            open ? "rotate-0" : "-rotate-90",
          )}
          strokeWidth={1.5}
        />
      </button>
      {/* Still real links: each resolves to its own protected Coming Soon page
          that explains the module, and each keeps its Soon marker and spoken
          description. The simplification here is the *grouping* — nothing is
          taken away. */}
      <div id={panelId} className={open ? undefined : "hidden"}>
        <NavList items={items} current={current} />
      </div>
    </div>
  );
}

function SidebarSupportLink({
  current,
  fullUrl,
}: {
  current: string;
  fullUrl: string;
}) {
  const active =
    current === routes.feedback_submit() ||
    current.startsWith(`${routes.feedback_submit()}/`) ||
    current === routes.feedback_mine();

  // The page the reader is on travels with the click. `document.referrer` is
  // empty for an Inertia visit, which is every visit here, so capturing it at
  // the source is the only way the report knows where it came from.
  //
  // The *full* url, not the path: `current` has its query stripped for
  // active-matching, and the query is often the whole story — "page 3 of the
  // filtered list" is where the thing broke. The redaction layer keeps an
  // allowlist of exactly those filter parameters and drops the rest, so
  // sending them is safe and dropping them here would waste that work.
  const href = `${routes.feedback_submit()}?from=${encodeURIComponent(fullUrl)}`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={href}
          aria-current={active ? "page" : undefined}
          className={cn(
            // An *outlined* row, not a nav row. Every destination above it is
            // a place in the product; this is a utility, and giving it the
            // same treatment made it read as an orphaned twelfth link rather
            // than the thing you reach for when something breaks.
            "focus-visible:ring-sidebar-ring group/help flex items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-[background-color,border-color,color] duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none",
            "group-data-[collapsible=icon]:size-9 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:gap-0 group-data-[collapsible=icon]:border-transparent group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:py-0",
            active
              ? "border-chip-primary-edge bg-chip-primary"
              : "border-sidebar-border/70 hover:border-border-strong hover:bg-sidebar-accent/45 bg-transparent",
          )}
        >
          <span
            aria-hidden
            className={cn(
              "grid size-7 shrink-0 place-items-center rounded-md transition-colors",
              active
                ? "bg-brand-gold/25 text-primary"
                : "brand-well text-primary group-hover/help:bg-brand-gold/25",
            )}
          >
            <LifeBuoy className="size-4" strokeWidth={1.5} />
          </span>
          <span className="grid min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <span className="text-sidebar-foreground truncate text-sm font-medium">
              Get help
            </span>
            <span className="text-muted-foreground truncate text-xs">
              Report a problem
            </span>
          </span>
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right">Report a problem or ask for help</TooltipContent>
    </Tooltip>
  );
}

function SidebarAccount({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  return (
    <div className="flex items-center gap-1">
      <Link
        href={routes.profile()}
        className="hover:bg-sidebar-accent/55 focus-visible:ring-sidebar-ring flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-1.5 py-1.5 transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
      >
        <UserAvatar user={user} className="size-8 shrink-0" />
        <span className="min-w-0 flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
          <span className="block truncate text-sm font-medium">{user.name}</span>
          <span className="text-muted-foreground block truncate text-xs">
            {user.email}
          </span>
        </span>
      </Link>
      <ThemeToggle />
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

/**
 * Where the reader is, on one line.
 *
 * The trail already ends in the page's own name, so the stacked title that
 * used to sit under it restated — inside a 56px band — what the crumb above it
 * and the page's `<h1>` below it both said. One line reads as a location and
 * leaves the bar room to breathe; the ancestors fold away on a narrow screen
 * and the current page always survives.
 */
function PageContext({ context }: { context: HubPageContext }) {
  const breadcrumbs = context.breadcrumbs ?? [];

  if (!breadcrumbs.length) {
    return (
      <p className="min-w-0 flex-1 truncate text-sm font-medium tracking-[-0.01em]">
        {context.title}
      </p>
    );
  }

  return (
    <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
      <ol className="flex min-w-0 items-center gap-1.5 overflow-hidden text-sm">
        {breadcrumbs.map((item, index) => {
          const current = index === breadcrumbs.length - 1;
          return (
            <li
              key={`${item.href ?? "current"}:${item.label}`}
              className={cn(
                "flex min-w-0 items-center gap-1.5",
                !current && "hidden sm:flex",
              )}
            >
              {index > 0 ? (
                <span
                  aria-hidden
                  className={cn(
                    "text-muted-foreground/60",
                    current && "hidden sm:inline",
                  )}
                >
                  /
                </span>
              ) : null}
              {item.href && !current ? (
                <Link
                  href={safeInternalHref(item.href)}
                  // `py-0.5` is hit area, not spacing: the text's own line box
                  // is 20px, which is under the 24px target minimum. The row is
                  // centred inside a much taller bar, so the padding grows the
                  // target without moving a pixel of the label.
                  className="text-muted-foreground hover:text-foreground focus-visible:ring-ring truncate rounded-sm py-0.5 transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  aria-current={current ? "page" : undefined}
                  className="truncate font-medium tracking-[-0.01em]"
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function ShellWorkspace({
  authorizationVersion,
  children,
  context,
  helpUrl,
  notifications,
  quickCreate,
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
  quickCreate: PageProps["quickCreate"];
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
      <header className="bg-background/92 sticky top-0 z-10 flex h-16 items-center gap-1.5 border-b px-3 backdrop-blur-sm sm:gap-2 sm:px-4 lg:px-6 print:hidden">
        {/* An Inertia visit swaps the page without a browser navigation, so
            none of the usual chrome moves and a slow request reads as a dead
            click. This is the only sighted feedback that one is in flight; the
            polite status below carries the same fact to a screen reader. It
            rides the header's own border, so nothing on the page shifts when
            it appears. */}
        {navigating ? (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-x-0 -bottom-px h-0.5 overflow-hidden"
          >
            <span className="bg-brand-gold animate-route-progress block h-full w-full" />
          </span>
        ) : null}
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
        {/* Live global search. Results are authorized and scoped server-side
            before serialization — see apps/web/search. */}
        <GlobalSearch />
        <div className="border-border/70 ml-auto flex shrink-0 items-center gap-0.5 border-l pl-1.5 sm:pl-2">
          {/* Help always does something now. The in-app support surface is the
              destination that always exists; an external help centre, when one
              is configured, is offered beside it rather than instead of it —
              the two answer different questions ("how does this work" versus
              "this is broken"). */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-foreground size-9"
                aria-label="Help and support"
              >
                <CircleHelp aria-hidden className="size-5" strokeWidth={1.5} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel className="font-normal">
                <p className="text-sm font-medium">Need a hand?</p>
                <p className="text-muted-foreground text-xs">
                  Report a problem or check something you already sent.
                </p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link
                  href={`${routes.feedback_submit()}?from=${encodeURIComponent(
                    typeof window === "undefined"
                      ? ""
                      : window.location.pathname + window.location.search,
                  )}`}
                >
                  <LifeBuoy className="size-4" strokeWidth={1.5} />
                  Get help
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href={routes.feedback_mine()}>
                  <Inbox className="size-4" strokeWidth={1.5} />
                  My reports
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href={routes.it_support()}>
                  <Wrench className="size-4" strokeWidth={1.5} />
                  IT support
                </Link>
              </DropdownMenuItem>
              {helpUrl ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <a href={helpUrl} target="_blank" rel="noopener noreferrer">
                      <BookOpen className="size-4" strokeWidth={1.5} />
                      Help centre
                      <ExternalLink
                        className="text-muted-foreground ml-auto size-3.5"
                        aria-hidden
                      />
                      <span className="sr-only">(opens in a new tab)</span>
                    </a>
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
          <NotificationBell summary={notifications} />
          {/* One registry, both entry points: this header is the mobile header
              too, so desktop and mobile can never offer different actions. */}
          <QuickCreateMenu quickCreate={quickCreate} />
          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="ml-1 h-9 max-w-52 gap-2 rounded-md px-1 lg:pr-3"
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
          "flex min-w-0 flex-1 flex-col overflow-x-hidden py-6 outline-none lg:py-8",
          "print:px-0 print:py-0",
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
  const { user, features, primaryOffice, notifications, quickCreate } = page.props;
  const current = page.url.split("?")[0];
  // The rail lists what works; what is registered but unbuilt is gathered into
  // one disclosure at the bottom rather than scattered through the groups.
  const { live: navGroups, pending } = partitionByAvailability(
    resolveHubNav(user, features, primaryOffice),
  );
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
        className="bg-card text-foreground focus-visible:ring-ring sr-only rounded-md px-4 py-2 text-sm font-medium shadow-card focus-visible:fixed focus-visible:top-3 focus-visible:left-3 focus-visible:z-50 focus-visible:not-sr-only focus-visible:ring-2"
      >
        Skip to content
      </a>
      <Sidebar collapsible="icon" className="border-sidebar-border/70 print:hidden">
        {/* Collapsed, the rail keeps only the expand control — the lockup has
            no room and the mark alone would read as a dead button beside it.

            The band is 64px rather than the 56px it used to share with the top
            bar: this is a stacked lockup (mark over wordmark over tagline) and
            at 56px the tagline collapsed into a smudge. The workspace header
            matches, so the two hairlines still meet across the window. */}
        <SidebarHeader className="border-sidebar-border/70 h-16 flex-row items-center justify-between gap-1 border-b px-3.5 py-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2">
          <Link
            href={routes.dashboard()}
            className="focus-visible:ring-sidebar-ring flex min-w-0 items-center rounded-md py-1 focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:hidden"
            aria-label="oNEST Real Estate — go to dashboard"
          >
            {/* The gold artwork carries its own contrast on both the near-white
                rail and the dark one, so it needs no theme variant. Width and
                height are stated to reserve the box before the file decodes —
                a logo that pops in is the first thing a reader sees shift. */}
            <img
              src={onestLogo}
              width={397}
              height={251}
              alt=""
              className="h-11 w-auto max-w-full object-contain"
            />
          </Link>
          {/* Cmd-B collapses the rail and nothing said so; a shortcut nobody
              can find is a feature that does not exist. The hint is a `title`
              and `aria-keyshortcuts` rather than a Radix tooltip on purpose:
              this header also renders inside the mobile drawer, and a tooltip
              there takes the Escape key that should be closing the drawer. */}
          <SidebarTrigger
            title="Collapse sidebar (⌘B)"
            aria-keyshortcuts="Meta+B Control+B"
            className="text-muted-foreground hover:text-foreground hidden size-8 md:flex"
          />
        </SidebarHeader>
        <SidebarContent className="gap-0 overflow-x-hidden [mask-image:linear-gradient(to_bottom,#000_calc(100%-1.5rem),transparent)]">
          {/* Group labels carry the separation. Rules between them would add a
              second divider to a rail that is already one column of type. */}
          <nav aria-label="Hub sections" className="flex min-h-0 flex-col">
            {navGroups.map((group) => (
              <SidebarGroup
                key={group.label}
                className="px-2.5 pt-4 pb-0 first:pt-3 group-data-[collapsible=icon]:px-1.5"
              >
                <SidebarGroupLabel className="text-muted-foreground mb-1 h-5 px-2.5 text-micro font-semibold tracking-[0.09em] uppercase">
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
            <SidebarComingSoon items={pending} current={current} />
          </nav>
        </SidebarContent>
        {/* The wordmark in the header already names the company; under a real
            account row a second "oNEST Real Estate" line was just filler.
            This rule is the one divider in the rail — group labels carry the
            separation above it, but the account is a different kind of thing
            from a destination and earns the seam. */}
        {/* Help is pinned rather than listed. It is the one destination whose
            value is being findable the moment something goes wrong — putting
            it in the scrolling list means the reader who needs it most has to
            scroll past everything that just failed them. It sits above the
            account card because both are about the person rather than the
            work, and the footer is already the rail's one seam. */}
        <SidebarFooter className="border-sidebar-border/70 mt-2 gap-1 border-t px-2.5 py-2.5 group-data-[collapsible=icon]:px-1.5">
          <SidebarSupportLink current={current} fullUrl={page.url} />
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
        quickCreate={quickCreate}
        primaryOffice={primaryOffice}
        role={role}
        user={user}
        variant={variant}
        onSignOut={signOut}
      >
        <FlashToasts />
        {children}
      </ShellWorkspace>
    </SidebarProvider>
  );
}
