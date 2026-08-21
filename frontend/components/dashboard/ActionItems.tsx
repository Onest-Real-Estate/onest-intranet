import { Link } from "@inertiajs/react";
import { ArrowRight, Clock } from "lucide-react";

import { StatusBadge } from "@/components/design-system/status-badge";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardActionItem, DashboardActionItems } from "@/types";
import type { StatusTone } from "@/types/design-system";

function priorityTone(item: DashboardActionItem): StatusTone {
  if (item.overdue || item.priority === "critical") {
    return "destructive";
  }
  if (item.priority === "high") {
    return "warning";
  }
  if (item.priority === "low") {
    return "neutral";
  }
  return "info";
}

function statusLabel(item: DashboardActionItem): string {
  if (item.overdue) {
    return "Overdue";
  }
  return item.priorityLabel;
}

function ActionRow({ item }: { item: DashboardActionItem }) {
  return (
    <Link
      href={item.ctaHref}
      className="hover:border-ring/40 hover:bg-muted/40 focus-visible:ring-ring focus-visible:ring-offset-background flex items-start justify-between gap-3 rounded-lg border px-3 py-3 transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
      aria-label={`${item.title}. ${statusLabel(item)}. ${item.dueLabel}. ${item.ctaLabel}`}
    >
      <span className="grid min-w-0 gap-0.5">
        <span className="truncate text-sm font-medium">{item.title}</span>
        {item.context ? (
          <span className="text-muted-foreground truncate text-xs">{item.context}</span>
        ) : null}
        <span
          className={
            item.overdue
              ? "text-destructive mt-0.5 flex items-center gap-1.5 text-xs font-medium"
              : "text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs"
          }
        >
          <Clock className="size-3.5" strokeWidth={1.5} aria-hidden />
          {item.dueLabel}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <StatusBadge status={{ label: statusLabel(item), tone: priorityTone(item) }} />
        <span className="text-muted-foreground text-xs">{item.ctaLabel}</span>
      </span>
    </Link>
  );
}

/**
 * Prioritized work queue for the signed-in reader.
 *
 * Rows link to the permitted resolution workflow. There is no local completion
 * control: ticking a box here would invent a second truth beside the source
 * record, and legal/compliance items must never be marked done by dismiss.
 */
export function ActionItems({
  data,
  truncated = false,
}: {
  data: DashboardActionItems;
  truncated?: boolean;
}) {
  const capped = truncated || data.total > data.items.length;

  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title="Action items"
        meta={
          <SurfaceCardMeta>
            {capped
              ? `${data.items.length} of ${data.total} open`
              : `${data.total} open`}
          </SurfaceCardMeta>
        }
        action={
          capped ? (
            <Button asChild variant="ghost" size="sm" className="gap-1">
              <Link href={data.viewAllHref}>
                View all
                <ArrowRight className="size-3.5" strokeWidth={1.5} aria-hidden />
              </Link>
            </Button>
          ) : undefined
        }
      />
      <SurfaceCardContent className="grid gap-2">
        {data.items.map((item) => (
          <ActionRow key={item.id} item={item} />
        ))}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function ActionItemsSkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="Action items" />
      <SurfaceCardContent className="grid gap-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
