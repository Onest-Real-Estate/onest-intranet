import { Link, router, usePage } from "@inertiajs/react";
import {
  Bell,
  CircleHelp,
  LogOut,
  Plus,
  Search,
  Settings,
  UserRound,
} from "lucide-react";
import type { CSSProperties, FormEvent, ReactNode } from "react";

import { BrandMark } from "@/components/BrandMark";
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
import { Input } from "@/components/ui/input";
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
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HUB_NAV_GROUPS, type HubNavItem, isComingSoon } from "@/lib/hub-nav";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

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

function isActivePath(current: string, href: string): boolean {
  return current === href || current.startsWith(`${href}/`);
}

function NavList({ items, current }: { items: HubNavItem[]; current: string }) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const active = isActivePath(current, item.href);
        const soon = isComingSoon(item.href);
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              asChild
              isActive={active}
              tooltip={item.title}
              className="transition-colors duration-150"
            >
              <Link href={item.href} aria-current={active ? "page" : undefined}>
                <item.icon
                  className={
                    active
                      ? "size-5 transition-colors"
                      : "text-muted-foreground group-hover/menu-item:text-foreground size-5 transition-colors"
                  }
                  strokeWidth={1.5}
                />
                <span>{item.title}</span>
                {soon ? (
                  <span
                    className="bg-sidebar-accent/70 text-muted-foreground ml-auto shrink-0 rounded-full px-1.5 py-px text-xs font-medium tracking-[0.04em] group-data-[collapsible=icon]:hidden"
                    aria-hidden
                  >
                    Soon
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
          className="opacity-55"
          onClick={(event) => event.preventDefault()}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{note}</TooltipContent>
    </Tooltip>
  );
}

export function HubLayout({ children }: { children: ReactNode }) {
  const page = usePage<PageProps>();
  const { user } = page.props;
  const current = page.url.split("?")[0];

  function handleLogout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.post(routes.logout());
  }

  const name = user?.name ?? "Agent";
  const role = user?.roleLabel ?? "Agent";

  return (
    // A little wider than the 16rem default: the section labels carry "Soon"
    // markers, and "Policies & compliance" needs the room.
    <SidebarProvider style={{ "--sidebar-width": "17rem" } as CSSProperties}>
      {/* First focusable element on the page — before the whole nav list. */}
      <a
        href="#hub-content"
        className="bg-card text-foreground focus-visible:ring-ring sr-only rounded-md px-4 py-2 text-sm font-medium shadow-sm focus-visible:fixed focus-visible:top-3 focus-visible:left-3 focus-visible:z-50 focus-visible:not-sr-only focus-visible:ring-2"
      >
        Skip to content
      </a>
      <Sidebar collapsible="icon">
        <SidebarHeader className="flex-row items-center justify-between gap-1 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:gap-2">
          <Link
            href={routes.dashboard()}
            className="focus-visible:ring-sidebar-ring flex items-center gap-2 rounded-md px-1 py-1 focus-visible:ring-2 focus-visible:outline-none group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
            aria-label="ONEST HUB home"
          >
            <span className="brand-surface grid size-8 shrink-0 place-items-center rounded-lg">
              <BrandMark className="size-6" />
            </span>
            <span className="text-sm font-bold tracking-[-0.03em] group-data-[collapsible=icon]:hidden">
              ONEST HUB
            </span>
          </Link>
          <SidebarTrigger className="text-muted-foreground hidden md:flex" />
        </SidebarHeader>
        <SidebarContent>
          <nav aria-label="Hub sections" className="flex min-h-0 flex-col">
            {HUB_NAV_GROUPS.map((group, index) => (
              <div key={group.label}>
                {index > 0 ? (
                  <SidebarSeparator className="group-data-[collapsible=icon]:mx-1" />
                ) : null}
                <SidebarGroup>
                  <SidebarGroupLabel className="text-muted-foreground text-xs font-semibold tracking-[0.08em] uppercase">
                    {group.label}
                  </SidebarGroupLabel>
                  <SidebarGroupContent>
                    <NavList items={group.items} current={current} />
                  </SidebarGroupContent>
                </SidebarGroup>
              </div>
            ))}
          </nav>
        </SidebarContent>
        <SidebarFooter>
          {user ? (
            <div className="bg-sidebar-accent/60 flex items-center gap-2 rounded-lg p-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:p-0">
              <Avatar className="border-primary/20 size-9 shrink-0 border">
                <AvatarFallback className="brand-surface text-xs font-semibold">
                  {initials(name)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 group-data-[collapsible=icon]:hidden">
                <p className="truncate text-sm font-medium">{name}</p>
                <p className="text-muted-foreground truncate text-xs">{role}</p>
              </div>
            </div>
          ) : null}
          <p className="text-muted-foreground px-2 pb-1 text-xs group-data-[collapsible=icon]:hidden">
            oNEST Real Estate
          </p>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="bg-background/90 sticky top-0 z-10 flex h-16 items-center gap-2 border-b px-4 backdrop-blur-xl">
          <SidebarTrigger className="md:hidden" />
          <Tooltip>
            {/* The wrapper carries the tooltip: a disabled input fires no
                pointer events of its own. */}
            <TooltipTrigger asChild>
              <div className="relative hidden w-full max-w-sm min-w-0 md:block">
                <Search
                  className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
                  strokeWidth={1.5}
                />
                <Input
                  type="search"
                  placeholder="Search across ONEST — coming soon"
                  className="pl-9"
                  aria-label="Search across ONEST — coming soon"
                  disabled
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>Search arrives with the next release</TooltipContent>
          </Tooltip>
          <div className="ml-auto flex items-center gap-1">
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
                    className="h-10 gap-2 rounded-full px-1 lg:pr-3"
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
