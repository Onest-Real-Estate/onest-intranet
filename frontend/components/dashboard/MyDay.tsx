import { Link } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardFooter,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Timeline } from "@/components/design-system/timeline";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { routes } from "@/lib/routes";
import type { DashboardSchedule } from "@/types";

export function MyDay({ schedule }: { schedule: DashboardSchedule }) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title="My day"
        meta={<SurfaceCardMeta>{schedule.dateLabel}</SurfaceCardMeta>}
      />
      <SurfaceCardContent>
        <Timeline
          items={schedule.events.map((event, index) => ({
            id: `${event.time}-${event.title}`,
            title: event.title,
            description: event.place,
            meta: event.time,
            tone: index === 0 ? "info" : "neutral",
            current: index === 0,
          }))}
        />
      </SurfaceCardContent>
      <SurfaceCardFooter>
        <Button asChild variant="outline" size="sm" className="w-full">
          <Link href={routes.coming_soon("my-reservations")}>
            View full calendar
            <ArrowRight className="size-4" strokeWidth={1.5} aria-hidden />
          </Link>
        </Button>
      </SurfaceCardFooter>
    </SurfaceCard>
  );
}

export function MyDaySkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="My day" />
      <SurfaceCardContent className="grid gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
