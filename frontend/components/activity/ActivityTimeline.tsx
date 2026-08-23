import { FileText, History, LoaderCircle } from "lucide-react";

import { EmptyState } from "@/components/design-system/empty-state";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Timeline } from "@/components/design-system/timeline";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ActivityTimelineEntry, ActivityTimelinePage } from "@/types";
import type { StatusTone } from "@/types/design-system";

function toneFor(entry: ActivityTimelineEntry): StatusTone {
  if (entry.outcome === "denied" || entry.outcome === "failure") {
    return "destructive";
  }
  if (entry.actorKind === "system" || entry.actorKind === "service") {
    return "info";
  }
  if (entry.visibility === "redacted" || entry.visibility === "summary") {
    return "warning";
  }
  return "neutral";
}

function descriptionFor(entry: ActivityTimelineEntry): string | undefined {
  const parts: string[] = [entry.actorLabel];
  if (entry.reason) {
    parts.push(entry.reason);
  } else if (entry.changeSummary.length) {
    parts.push(entry.changeSummary.join(", "));
  }
  if (entry.files.length) {
    parts.push(
      entry.files.length === 1 ? entry.files[0].name : `${entry.files.length} files`,
    );
  }
  return parts.filter(Boolean).join(" · ") || undefined;
}

export function ActivityTimeline({
  title = "Activity",
  page,
  state = "ready",
  errorMessage,
  onLoadMore,
  loadingMore = false,
  className,
  compactEmpty = false,
}: {
  title?: string;
  page?: ActivityTimelinePage | null;
  state?: "ready" | "loading" | "error" | "empty";
  errorMessage?: string;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  className?: string;
  compactEmpty?: boolean;
}) {
  const entries = page?.entries ?? [];
  const resolvedState = state === "ready" && entries.length === 0 ? "empty" : state;

  return (
    <SurfaceCard
      className={cn("arrive", className)}
      state={resolvedState === "loading" ? "loading" : undefined}
    >
      <PanelHeader
        title={title}
        meta={
          <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <History className="size-3.5" aria-hidden />
            {page?.timezone ? page.timezone : "Audited"}
          </span>
        }
      />
      <SurfaceCardContent>
        {resolvedState === "loading" ? <ActivityTimelineSkeletonRows /> : null}

        {resolvedState === "error" ? (
          <EmptyState
            compact={compactEmpty}
            icon={History}
            title="Activity unavailable"
            description={
              errorMessage ||
              "This timeline could not be loaded. Try again in a moment."
            }
          />
        ) : null}

        {resolvedState === "empty" ? (
          <EmptyState
            compact={compactEmpty}
            icon={History}
            title="No activity yet"
            description="Changes on this record will show up here in order."
          />
        ) : null}

        {resolvedState === "ready" ? (
          <div className="grid gap-4">
            <Timeline
              aria-label={title}
              items={entries.map((entry) => ({
                id: entry.id,
                title: entry.summary,
                meta: entry.occurredAtDisplay,
                description: descriptionFor(entry),
                tone: toneFor(entry),
                icon: entry.files.length ? FileText : undefined,
              }))}
            />
            {page?.hasMore && onLoadMore ? (
              <div className="flex justify-center">
                <button
                  type="button"
                  className="text-primary inline-flex items-center gap-2 text-sm font-medium disabled:opacity-60"
                  onClick={onLoadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden />
                  ) : null}
                  {loadingMore ? "Loading…" : "Load older activity"}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function ActivityTimelineSkeletonRows() {
  return (
    <div className="grid gap-3" role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading activity</span>
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function ActivityTimelineSkeleton({ title = "Activity" }: { title?: string }) {
  return <ActivityTimeline title={title} state="loading" page={null} />;
}
