import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  Building2,
  Cloud,
  Files,
  SquareArrowOutUpRight,
} from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardQuickApp } from "@/types";

const APP_ICONS: Record<string, LucideIcon> = {
  lofty: Building2,
  skyslope: Cloud,
  microsoft365: AppWindow,
  dotloop: Files,
};

export function QuickApps({ apps }: { apps: DashboardQuickApp[] }) {
  return (
    <section className="grid gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Quick access</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {apps.map((app) => {
          const Icon = APP_ICONS[app.id] ?? AppWindow;
          return (
            <a
              key={app.id}
              href={app.href}
              target="_blank"
              rel="noreferrer"
              className="focus-visible:ring-ring rounded-xl focus-visible:ring-2 focus-visible:outline-none"
            >
              <Card className="hover:bg-muted/40 h-full py-0 transition-colors">
                <CardContent className="flex flex-row items-center gap-3 px-4 py-3">
                  <IconWell icon={Icon} className="size-9 shrink-0" />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {app.name}
                  </span>
                  <SquareArrowOutUpRight
                    className="text-muted-foreground size-4 shrink-0"
                    strokeWidth={1.5}
                  />
                </CardContent>
              </Card>
            </a>
          );
        })}
      </div>
    </section>
  );
}

export function QuickAppsSkeleton() {
  return (
    <section className="grid gap-3">
      <Skeleton className="h-6 w-32" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {["a1", "a2", "a3", "a4"].map((id) => (
          <Skeleton key={id} className="h-16 rounded-xl" />
        ))}
      </div>
    </section>
  );
}
