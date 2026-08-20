import type React from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DashboardActivity, DashboardActivityEntry } from "@/types";
import type { StatusTone } from "@/types/design-system";

const dotTone: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground/40",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  destructive: "bg-destructive",
};

function Entry({ entry }: { entry: DashboardActivityEntry }) {
  return (
    <li className="flex items-start gap-3">
      <span
        className={cn("mt-1.5 size-2 shrink-0 rounded-full", dotTone[entry.tone])}
        aria-hidden
      />
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="text-sm leading-5">
          <span className="font-medium">{entry.actor}</span>{" "}
          <span className="text-muted-foreground">{entry.action}</span>{" "}
          <span className="font-medium">{entry.target}</span>
        </span>
        <SurfaceCardMeta>{entry.at}</SurfaceCardMeta>
      </span>
    </li>
  );
}

/**
 * Recent administrative events in the reader's effective scope.
 *
 * This is a convenience view of activity the audit log already records; it is
 * never the record itself, and it shows only events the reader's scope covers.
 */
export function ActivityFeed({
  title,
  data,
  action,
}: {
  title: string;
  data: DashboardActivity;
  action?: React.ReactNode;
}) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader title={title} action={action} />
      <SurfaceCardContent>
        <ul className="grid gap-3">
          {data.entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function ActivityFeedSkeleton({ title }: { title: string }) {
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
