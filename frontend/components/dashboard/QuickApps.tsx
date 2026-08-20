import { ArrowRight, SquareArrowOutUpRight, TriangleAlert } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { IconWell } from "@/components/IconWell";
import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { Skeleton } from "@/components/ui/skeleton";
import { MICROSOFT_ICON_KEY, quickAccessIcon } from "@/lib/quick-access-icons";
import type { DashboardQuickApp } from "@/types";

/**
 * Vendor launchers, as a panel beside the news band.
 *
 * The rows are administered data now (`P1-025`): an administrator decides what
 * appears here, in what order, and for which offices and roles, and the server
 * has already resolved all of that by the time this component runs. Nothing
 * about the audience is decided in the browser.
 *
 * The mark comes from the link's approved icon key rather than from a guess at
 * the vendor's name, so the row is scannable by shape before anyone reads a
 * label. Microsoft is the one vendor whose real mark the app ships, so it uses
 * that rather than an impression of it.
 */
export function QuickApps({ apps }: { apps: DashboardQuickApp[] }) {
  return (
    <SurfaceCard className="arrive h-full">
      <PanelHeader title="Quick access" />
      <SurfaceCardContent className="flex flex-1 flex-col">
        {/* One column: the launchers sit in the narrow third of the top band,
            where two labels side by side would both truncate. */}
        <ul className="grid flex-1 auto-rows-fr grid-cols-1 gap-3">
          {apps.map((app) => (
            <li key={app.id} className="min-w-0">
              <QuickAppRow app={app} />
            </li>
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function QuickAppRow({ app }: { app: DashboardQuickApp }) {
  const isMicrosoft = app.icon === MICROSOFT_ICON_KEY;
  const Icon = isMicrosoft ? undefined : quickAccessIcon(app.icon);
  // An internal destination is an in-app path: opening it in a new tab would
  // fork the session's navigation for no reason.
  const external = app.external;
  const degraded = app.health === "degraded" || app.health === "offline";

  return (
    <a
      href={app.href}
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
      className="hover:border-primary/30 hover:bg-muted/40 focus-visible:ring-ring focus-visible:ring-offset-background group flex h-full items-center gap-3 rounded-lg border px-3 py-2 transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <IconWell icon={Icon} className="size-9 shrink-0">
        {isMicrosoft ? <MicrosoftLogo className="size-[1.125rem]" /> : null}
      </IconWell>
      {/* Two short lines beat "Micros…" in a half-width tile. */}
      <span className="min-w-0 flex-1 text-sm leading-tight font-medium">
        {app.name}
        {app.description ? (
          <span className="text-muted-foreground block truncate text-xs font-normal">
            {app.description}
          </span>
        ) : null}
      </span>
      {degraded ? (
        <span className="text-warning-ink flex shrink-0 items-center gap-1 text-xs">
          <TriangleAlert className="size-3.5" aria-hidden />
          <span className="sr-only">Integration status: </span>
          {app.health === "offline" ? "Offline" : "Degraded"}
        </span>
      ) : null}
      {external ? (
        <SquareArrowOutUpRight
          className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors"
          strokeWidth={1.5}
        />
      ) : (
        <ArrowRight
          className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors"
          strokeWidth={1.5}
        />
      )}
      {external ? <span className="sr-only"> (opens in a new tab)</span> : null}
    </a>
  );
}

export function QuickAppsSkeleton() {
  return (
    <SurfaceCard state="loading" className="h-full">
      <PanelHeader title="Quick access" />
      <SurfaceCardContent className="flex flex-1 flex-col">
        <div className="grid flex-1 auto-rows-fr grid-cols-1 gap-3">
          {["a1", "a2", "a3", "a4"].map((id) => (
            <Skeleton key={id} className="h-13 rounded-lg" />
          ))}
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
