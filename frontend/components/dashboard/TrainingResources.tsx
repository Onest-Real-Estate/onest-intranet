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
    <SurfaceCard className="arrive">
      <PanelHeader title="Training & resources" />
      {/* The panel shares a row with whatever sits beside it and stretches to
          that row's height. A body pinned to the top of a stretched card leaves
          a bar of dead space under it; centring the two sections in the height
          the card actually got keeps the panel looking drawn rather than
          padded. */}
      <SurfaceCardContent className="grid flex-1 content-center gap-5 @md:grid-cols-[auto_1fr] @md:items-center">
        <section
          className="flex items-center gap-4"
          aria-labelledby="training-progress"
        >
          <div className="relative shrink-0">
            <Ring percent={training.percent} />
            <span className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">
              {training.percent}%
            </span>
          </div>
          <div className="grid gap-1">
            <h3 id="training-progress" className="text-sm font-semibold">
              Continuing education
            </h3>
            <p className="text-muted-foreground text-sm leading-6">{training.label}</p>
          </div>
        </section>
        <section className="grid gap-1 border-t pt-4 @md:border-t-0 @md:border-l @md:pt-0 @md:pl-5">
          <h3 className="text-sm font-semibold">Featured resource</h3>
          <p className="font-medium">{training.resourceTitle}</p>
          <p className="text-muted-foreground text-sm leading-6">
            {training.resourceHint}
          </p>
        </section>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function TrainingResourcesSkeleton() {
  return (
    <SurfaceCard state="loading">
      <PanelHeader title="Training & resources" />
      <SurfaceCardContent className="grid gap-4 @md:grid-cols-2">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
