import { Percent, TrendingUp } from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardMarket } from "@/types";

export function MarketSnapshot({ market }: { market: DashboardMarket }) {
  return (
    <Card className="arrive">
      <CardHeader>
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={TrendingUp}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            Market snapshot
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {market.rates.map((rate) => (
          <div key={rate.label} className="grid gap-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5">
                <Percent className="text-muted-foreground size-3.5" strokeWidth={1.5} />
                {rate.label}
              </span>
              <span className="font-medium tabular-nums">{rate.value}</span>
            </div>
            <Progress value={rate.bar} aria-label={`${rate.label} ${rate.value}`} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function MarketSnapshotSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-36" />
      </CardHeader>
      <CardContent className="grid gap-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </CardContent>
    </Card>
  );
}
