import { Clock } from "lucide-react";
import { useState } from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardActionItems } from "@/types";

export function ActionItems({ data }: { data: DashboardActionItems }) {
  // Local only: there is no completion endpoint yet, but a checkbox that
  // snaps back the moment you tick it reads as broken rather than pending.
  const [done, setDone] = useState<Record<string, boolean>>({});
  const remaining = data.items.filter((item) => !done[item.id]).length;

  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title="Action items"
        meta={
          <SurfaceCardMeta>
            {remaining} of {data.total} open
          </SurfaceCardMeta>
        }
      />
      <SurfaceCardContent className="grid gap-2">
        {data.items.map((item) => {
          const checked = Boolean(done[item.id]);
          return (
            <div
              key={item.id}
              className="hover:bg-muted/40 flex items-start gap-3 rounded-lg border px-3 py-3 transition-colors"
              data-done={checked || undefined}
            >
              <Checkbox
                className="mt-0.5"
                aria-label={item.title}
                checked={checked}
                onCheckedChange={(value) =>
                  setDone((prev) => ({ ...prev, [item.id]: value === true }))
                }
              />
              <span className={`grid min-w-0 gap-0.5 ${checked ? "opacity-60" : ""}`}>
                <span
                  className={`text-sm font-medium ${checked ? "line-through" : ""}`}
                >
                  {item.title}
                </span>
                <span className="text-muted-foreground text-xs">{item.property}</span>
                <span
                  className={
                    item.late && !checked
                      ? "text-destructive mt-0.5 flex items-center gap-1.5 text-xs font-medium"
                      : "text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs"
                  }
                >
                  <Clock className="size-3.5" strokeWidth={1.5} aria-hidden />
                  {item.late && !checked ? `Late · ${item.due}` : item.due}
                </span>
              </span>
            </div>
          );
        })}
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
