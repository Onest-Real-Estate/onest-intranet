import { Link, router, usePage } from "@inertiajs/react";
import { LogOut } from "lucide-react";
import type { FormEvent, ReactNode } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
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

export function AppLayout({ children }: { children: ReactNode }) {
  const { user } = usePage<PageProps>().props;

  function handleLogout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.post(routes.logout());
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4">
          <nav className="flex items-center">
            <Link href={routes.home()} className="text-sm font-semibold tracking-tight">
              Onest
            </Link>
            <Separator orientation="vertical" className="mx-3 h-5" />
            <Button variant="ghost" size="sm" asChild>
              <Link href={routes.home()}>Home</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href={routes.dashboard()}>Dashboard</Link>
            </Button>
          </nav>
          <div className="flex items-center gap-3">
            {user ? (
              <>
                <span className="hidden text-sm text-muted-foreground sm:block">
                  {user.email}
                </span>
                <Avatar className="size-8">
                  <AvatarFallback>{initials(user.name)}</AvatarFallback>
                </Avatar>
                <form onSubmit={handleLogout}>
                  <Button type="submit" variant="outline" size="sm">
                    <LogOut />
                    Sign out
                  </Button>
                </form>
              </>
            ) : (
              <Button size="sm" asChild>
                <Link href={routes.login()}>Sign in</Link>
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="flex flex-1 flex-col">{children}</main>
      <footer className="border-t py-6 text-center text-xs text-muted-foreground">
        Onest — Django · Inertia.js · React · shadcn/ui
      </footer>
    </div>
  );
}
