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
import type { FormEvent, ReactNode } from "react";

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
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  HUB_APP_NAV,
  HUB_DIRECTORY_NAV,
  HUB_PRIMARY_NAV,
  type HubNavItem,
} from "@/lib/hub-nav";
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
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
              <Link href={item.href} aria-current={active ? "page" : undefined}>
                <item.icon className="size-5" strokeWidth={1.5} />
                <span>{item.title}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
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
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <Link
            href={routes.dashboard()}
            className="flex items-center gap-2 rounded-md px-1 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
            aria-label="ONEST HUB home"
          >
            <span className="brand-surface grid size-8 shrink-0 place-items-center rounded-lg">
              <BrandMark className="size-6" />
            </span>
            <span className="text-sm font-bold tracking-[-0.03em] group-data-[collapsible=icon]:hidden">
              ONEST HUB
            </span>
          </Link>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <NavList items={HUB_PRIMARY_NAV} current={current} />
            </SidebarGroupContent>
          </SidebarGroup>
          <SidebarGroup>
            <SidebarGroupLabel>Apps</SidebarGroupLabel>
            <SidebarGroupContent>
              <NavList items={HUB_APP_NAV} current={current} />
            </SidebarGroupContent>
          </SidebarGroup>
          <SidebarGroup>
            <SidebarGroupContent>
              <NavList items={HUB_DIRECTORY_NAV} current={current} />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          {user ? (
            <div className="flex items-center gap-2 rounded-lg bg-sidebar-accent/60 p-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:p-0">
              <Avatar className="size-9 shrink-0 border border-primary/20">
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
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="bg-background/90 sticky top-0 z-10 flex h-14 items-center gap-2 border-b px-4 backdrop-blur-xl">
          <SidebarTrigger />
          <div className="relative mx-auto hidden min-w-0 max-w-xl flex-1 md:block">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
              strokeWidth={1.5}
            />
            <Input
              type="search"
              placeholder="Search across ONEST…"
              className="pl-9"
              aria-label="Search across ONEST"
            />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" aria-label="Help">
              <CircleHelp className="size-5" strokeWidth={1.5} />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Notifications">
              <Bell className="size-5" strokeWidth={1.5} />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Create new">
              <Plus className="size-5" strokeWidth={1.5} />
            </Button>
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="rounded-full">
                    <Avatar className="size-8">
                      <AvatarFallback className="brand-surface text-[10px] font-semibold">
                        {initials(name)}
                      </AvatarFallback>
                    </Avatar>
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
        <div className="flex flex-1 flex-col">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
