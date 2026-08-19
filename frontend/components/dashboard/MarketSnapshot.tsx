import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardMarket } from "@/types";

export function MarketSnapshot({ market }: { market: DashboardMarket }) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader title="Market snapshot" />
      <SurfaceCardContent className="grid gap-4">
        {market.rates.map((rate) => (
          <div key={rate.label} className="grid gap-2">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-muted-foreground truncate">{rate.label}</span>
              <span className="font-semibold tabular-nums">{rate.value}</span>
            </div>
            <Progress
              value={rate.bar}
              className="h-1.5"
              aria-label={`${rate.label} ${rate.value}`}
            />
          </div>
        ))}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function MarketSnapshotSkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="Market snapshot" />
      <SurfaceCardContent className="grid gap-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
