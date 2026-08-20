import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardTraining } from "@/types";

function Ring({ percent }: { percent: number }) {
  const radius = 32;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;
  return (
    <svg
      viewBox="0 0 80 80"
      className="size-20 -rotate-90"
      role="img"
      aria-label={`${percent} percent complete`}
    >
      <circle
        cx="40"
        cy="40"
        r={radius}
        fill="none"
        className="stroke-muted"
        strokeWidth="7"
      />
      <circle
        cx="40"
        cy="40"
        r={radius}
        fill="none"
        className="stroke-primary"
        strokeWidth="7"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function TrainingResources({ training }: { training: DashboardTraining }) {
  return (
    <div className="arrive grid gap-4 sm:grid-cols-2">
      <SurfaceCard>
        <PanelHeader title="Continuing ED" />
        <SurfaceCardContent className="flex items-center gap-4">
          <div className="relative shrink-0">
            <Ring percent={training.percent} />
            <span className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">
              {training.percent}%
            </span>
          </div>
          <p className="text-sm leading-6">{training.label}</p>
        </SurfaceCardContent>
      </SurfaceCard>
      <SurfaceCard>
        <PanelHeader title="Resources" />
        <SurfaceCardContent>
          <p className="font-medium">{training.resourceTitle}</p>
          <p className="text-muted-foreground mt-1 text-sm leading-6">
            {training.resourceHint}
          </p>
        </SurfaceCardContent>
      </SurfaceCard>
    </div>
  );
}

export function TrainingResourcesSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Skeleton className="h-40 rounded-xl" />
      <Skeleton className="h-40 rounded-xl" />
    </div>
  );
}
