import { Bot, FileText, History, LoaderCircle, ShieldAlert } from "lucide-react";

import { EmptyState } from "@/components/design-system/empty-state";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Timeline } from "@/components/design-system/timeline";
import { Button } from "@/components/ui/button";
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

function markFor(entry: ActivityTimelineEntry) {
  if (entry.files.length) return FileText;
  if (entry.outcome === "denied" || entry.outcome === "failure") return ShieldAlert;
  if (entry.actorKind === "system" || entry.actorKind === "service") return Bot;
  return undefined;
}

function descriptionFor(entry: ActivityTimelineEntry): string | undefined {
  const parts: string[] = [];

  if (entry.actorKind === "system" || entry.actorKind === "service") {
    parts.push(`${entry.actorLabel} (automated)`);
  } else if (entry.actorKind === "anonymous" || entry.actorKind === "unknown") {
    parts.push(entry.actorLabel || "Unknown actor");
  } else {
    parts.push(entry.actorLabel);
  }

  if (entry.reason) {
    parts.push(entry.reason);
  } else if (entry.changeSummary.length) {
    const fields = entry.changeSummary.slice(0, 4).join(", ");
    const extra =
      entry.changeSummary.length > 4 ? ` +${entry.changeSummary.length - 4} more` : "";
    parts.push(
      entry.visibility === "full"
        ? `Changed ${fields}${extra}`
        : `Updated ${fields}${extra}`,
    );
  }

  if (entry.visibility === "redacted" || entry.visibility === "summary") {
    parts.push("Some details hidden");
  }

  if (entry.files.length === 1) {
    parts.push(entry.files[0].name);
  } else if (entry.files.length > 1) {
    parts.push(`${entry.files.length} files`);
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
  onRetry,
  className,
  compactEmpty = false,
}: {
  title?: string;
  page?: ActivityTimelinePage | null;
  state?: "ready" | "loading" | "error" | "empty";
  errorMessage?: string;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  onRetry?: () => void;
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
        description={
          resolvedState === "ready"
            ? "Newest first. Times use the brokerage timezone."
            : undefined
        }
        meta={
          <span className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tabular-nums">
            <History className="size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 truncate">
              {page?.timezone ? page.timezone : "Audited"}
            </span>
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
            actions={
              onRetry ? (
                <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                  Try again
                </Button>
              ) : undefined
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
          <div className="grid gap-5">
            <Timeline
              aria-label={title}
              items={entries.map((entry) => ({
                id: entry.id,
                title: entry.summary,
                meta: entry.occurredAtDisplay,
                description: descriptionFor(entry),
                tone: toneFor(entry),
                icon: markFor(entry),
              }))}
            />
            {page?.hasMore && onLoadMore ? (
              <div className="border-border/60 flex justify-center border-t pt-4">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onLoadMore}
                  disabled={loadingMore}
                  aria-busy={loadingMore || undefined}
                >
                  {loadingMore ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden />
                  ) : null}
                  {loadingMore ? "Loading…" : "Load older activity"}
                </Button>
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
    <div className="grid gap-4" role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading activity</span>
      {[0, 1, 2].map((row) => (
        <div
          key={row}
          className="grid grid-cols-[1.25rem_minmax(0,1fr)] items-start gap-3"
        >
          <Skeleton className="mt-1 size-2.5 rounded-full" />
          <div className="grid gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ActivityTimelineSkeleton({ title = "Activity" }: { title?: string }) {
  return <ActivityTimeline title={title} state="loading" page={null} />;
}
