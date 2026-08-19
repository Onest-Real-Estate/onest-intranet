import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  Building2,
  Cloud,
  Files,
  SquareArrowOutUpRight,
} from "lucide-react";

import {
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { IconWell } from "@/components/IconWell";
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
    <section className="arrive grid gap-3">
      <h2 className="text-base font-semibold tracking-[-0.01em]">Quick access</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {apps.map((app) => {
          const Icon = APP_ICONS[app.id] ?? AppWindow;
          return (
            <a
              key={app.id}
              href={app.href}
              target="_blank"
              rel="noreferrer"
              className="focus-visible:ring-ring focus-visible:ring-offset-background group rounded-xl focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <SurfaceCard interactive className="h-full gap-0 py-0">
                <SurfaceCardContent className="flex flex-row items-center gap-3 px-3.5 py-3">
                  <IconWell icon={Icon} className="size-9 shrink-0" />
                  {/* Two short lines beat "Micros…" in a half-width card. */}
                  <span className="min-w-0 flex-1 text-sm leading-tight font-medium">
                    {app.name}
                  </span>
                  <SquareArrowOutUpRight
                    className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors"
                    strokeWidth={1.5}
                  />
                </SurfaceCardContent>
              </SurfaceCard>
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
          <Skeleton key={id} className="h-[3.75rem] rounded-xl" />
        ))}
      </div>
    </section>
  );
}
