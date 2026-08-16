import { Link, usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { AppLayout } from "@/components/AppLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

export default function Home() {
  const { user } = usePage<PageProps>().props;

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-20 text-center">
      <Badge variant="secondary">Django + Inertia + React + shadcn/ui</Badge>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
        The Onest starter template
      </h1>
      <p className="max-w-xl text-muted-foreground">
        A Django backend serving an Inertia.js React frontend, with Microsoft SSO
        through django-allauth and type-safe Django URLs in TypeScript.
      </p>
      <div className="flex items-center gap-3 pt-2">
        {user ? (
          <Button size="lg" asChild>
            <Link href={routes.dashboard()}>Go to dashboard</Link>
          </Button>
        ) : (
          <Button size="lg" asChild>
            <Link href={routes.login()}>Sign in with Microsoft</Link>
          </Button>
        )}
      </div>
    </div>
  );
}

Home.layout = (page: ReactNode) => <AppLayout>{page}</AppLayout>;
