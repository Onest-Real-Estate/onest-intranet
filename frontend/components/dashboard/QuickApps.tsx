import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  Contact,
  ShieldCheck,
  Signature,
  SquareArrowOutUpRight,
} from "lucide-react";
import type { ReactNode } from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { IconWell } from "@/components/IconWell";
import { MicrosoftLogo } from "@/components/MicrosoftLogo";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardQuickApp } from "@/types";

/**
 * Each launcher gets a mark that says what the product *does* — a cloud for
 * SkySlope and a window for Microsoft 365 were shapes, not meanings, and four
 * unrelated glyphs in a row read as placeholder art.
 *
 * Lofty is the CRM (a contact card), SkySlope is transaction compliance (a
 * shield), dotloop is where things get signed (a signature). The four silhouettes
 * are deliberately unlike each other, so the row is scannable by shape before
 * anyone reads a label.
 *
 * Microsoft is the one vendor whose real mark we already ship, so it uses that
 * rather than an impression of it; the rest stay in the Lucide vocabulary the
 * sidebar uses instead of us approximating logos we do not have.
 */
const APP_ICONS: Record<string, LucideIcon> = {
  lofty: Contact,
  skyslope: ShieldCheck,
  dotloop: Signature,
};

const APP_MARKS: Record<string, ReactNode> = {
  microsoft365: <MicrosoftLogo className="size-[1.125rem]" />,
};

/**
 * Vendor launchers, as a panel beside the news band.
 *
 * The tiles used to be free-standing cards under a bare heading, which left
 * them a half-step out of line with every other panel on the page. They are
 * bordered rows inside one panel now — the same shape the task and contract
 * queues use — so the top band reads as two panels rather than a panel and a
 * loose group of buttons.
 */
export function QuickApps({ apps }: { apps: DashboardQuickApp[] }) {
  return (
    <SurfaceCard className="arrive h-full">
      <PanelHeader title="Quick access" />
      <SurfaceCardContent className="flex flex-1 flex-col">
        {/* One column: the launchers sit in the narrow third of the top band,
            where two labels side by side would both truncate. */}
        <div className="grid flex-1 auto-rows-fr grid-cols-1 gap-3">
          {apps.map((app) => {
            const mark = APP_MARKS[app.id];
            const Icon = mark ? undefined : (APP_ICONS[app.id] ?? AppWindow);
            return (
              <a
                key={app.id}
                href={app.href}
                target="_blank"
                rel="noreferrer"
                className="hover:border-primary/30 hover:bg-muted/40 focus-visible:ring-ring focus-visible:ring-offset-background group flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <IconWell icon={Icon} className="size-9 shrink-0">
                  {mark}
                </IconWell>
                {/* Two short lines beat "Micros…" in a half-width tile. */}
                <span className="min-w-0 flex-1 text-sm leading-tight font-medium">
                  {app.name}
                </span>
                <SquareArrowOutUpRight
                  className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors"
                  strokeWidth={1.5}
                />
              </a>
            );
          })}
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
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
