import { Link } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";
import type React from "react";

import { StatusBadge } from "@/components/design-system/status-badge";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardQueue, DashboardQueueRow } from "@/types";

function Row({ row }: { row: DashboardQueueRow }) {
  const body = (
    <>
      <span className="grid min-w-0 gap-0.5">
        <span className="truncate text-sm font-medium">{row.title}</span>
        {row.subtitle ? (
          <span className="text-muted-foreground truncate text-xs">{row.subtitle}</span>
        ) : null}
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        {row.badge ? (
          <StatusBadge status={{ label: row.badge, tone: row.tone }} />
        ) : null}
        {row.meta ? <SurfaceCardMeta>{row.meta}</SurfaceCardMeta> : null}
      </span>
    </>
  );

  const className =
    "flex items-start justify-between gap-3 rounded-lg border px-3 py-3 transition-colors duration-(--motion-fast)";

  if (row.href) {
    return (
      <Link
        href={row.href}
        className={`${className} hover:border-ring/40 hover:bg-muted/40 focus-visible:ring-ring focus-visible:ring-offset-background focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none`}
      >
        {body}
      </Link>
    );
  }
  return <div className={className}>{body}</div>;
}

/**
 * A bounded queue of records that need attention — contracts, exceptions,
 * tasks, overdue inventory, support tickets.
 *
 * `total` is the count in the reader's effective scope and may exceed the rows
 * the provider sent, so the panel says how many it is showing rather than
 * implying the list is complete.
 */
export function WorkQueue({
  title,
  data,
  action,
}: {
  title: string;
  data: DashboardQueue;
  action?: React.ReactNode;
}) {
  const truncated = data.total > data.rows.length;
  // The panel is a window on a queue, so it says where the rest of it is. The
  // provider sends the destination it already reversed and guarded; an explicit
  // `action` still wins for a caller that needs a different control.
  const viewAll =
    action ??
    (data.viewAllHref ? (
      <Button asChild variant="ghost" size="sm" className="gap-1">
        <Link href={data.viewAllHref}>
          View all
          <ArrowRight className="size-3.5" strokeWidth={1.5} aria-hidden />
        </Link>
      </Button>
    ) : undefined);
  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title={title}
        meta={
          <SurfaceCardMeta>
            {truncated ? `${data.rows.length} of ${data.total}` : `${data.total} open`}
          </SurfaceCardMeta>
        }
        action={viewAll}
      />
      <SurfaceCardContent className="grid gap-2">
        {data.rows.map((row) => (
          <Row key={row.id} row={row} />
        ))}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function WorkQueueSkeleton({ title }: { title: string }) {
  return (
    <SurfaceCard state="loading">
      <PanelHeader title={title} />
      <SurfaceCardContent className="grid gap-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
