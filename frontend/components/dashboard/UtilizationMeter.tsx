import type React from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardMeter } from "@/types";

/** A ratio with no denominator is unmeasured, which is not the same as zero. */
const UNMEASURED = "Not measured";

function percent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

/**
 * Utilization as a set of ratios — booked room-minutes over published open
 * hours today.
 *
 * A null ratio renders as "Not measured" rather than 0%: a room with no
 * published open hours was not available to book, and showing an empty bar
 * would read as "nobody used it".
 */
export function UtilizationMeter({
  title,
  data,
  action,
}: {
  title: string;
  data: DashboardMeter;
  action?: React.ReactNode;
}) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title={title}
        meta={<SurfaceCardMeta>{data.headline}</SurfaceCardMeta>}
        action={action}
      />
      <SurfaceCardContent className="grid gap-3">
        <p className="text-muted-foreground text-xs">{data.caption}</p>
        {data.series.map((entry) => {
          const measured = entry.ratio !== null;
          return (
            <div key={entry.label} className="grid gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate text-sm font-medium">{entry.label}</span>
                <span className="text-muted-foreground shrink-0 text-xs font-medium tabular-nums">
                  {measured ? percent(entry.ratio as number) : UNMEASURED}
                </span>
              </div>
              <Progress
                // Clamped for the bar only; the label above still reports the
                // real figure, so a double-booked room reads as over 100%.
                value={measured ? Math.min((entry.ratio as number) * 100, 100) : 0}
                className={measured ? undefined : "opacity-40"}
                aria-label={`${entry.label}: ${measured ? percent(entry.ratio as number) : UNMEASURED}`}
              />
              {entry.caption ? (
                <p className="text-muted-foreground text-xs">{entry.caption}</p>
              ) : null}
            </div>
          );
        })}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function UtilizationMeterSkeleton({ title }: { title: string }) {
  return (
    <SurfaceCard state="loading">
      <PanelHeader title={title} />
      <SurfaceCardContent className="grid gap-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
