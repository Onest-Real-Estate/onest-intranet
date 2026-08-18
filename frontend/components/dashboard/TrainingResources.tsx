import { GraduationCap, Megaphone } from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardTraining } from "@/types";

function Ring({ percent }: { percent: number }) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percent / 100) * circumference;
  return (
    <svg
      viewBox="0 0 96 96"
      className="size-24 -rotate-90"
      role="img"
      aria-label={`${percent} percent complete`}
    >
      <circle
        cx="48"
        cy="48"
        r={radius}
        fill="none"
        className="stroke-muted"
        strokeWidth="8"
      />
      <circle
        cx="48"
        cy="48"
        r={radius}
        fill="none"
        className="stroke-primary"
        strokeWidth="8"
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
      <Card>
        <CardHeader>
          <CardTitle asChild className="flex items-center gap-2">
            <h2>
              <IconWell
                icon={GraduationCap}
                tone="muted"
                className="size-8"
                iconClassName="size-4"
              />
              Continuing ED
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <div className="relative">
            <Ring percent={training.percent} />
            <span className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">
              {training.percent}%
            </span>
          </div>
          <p className="text-sm">{training.label}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle asChild className="flex items-center gap-2">
            <h2>
              <IconWell
                icon={Megaphone}
                tone="muted"
                className="size-8"
                iconClassName="size-4"
              />
              Resources
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-start gap-3">
          <IconWell icon={Megaphone} />
          <div>
            <p className="font-medium">{training.resourceTitle}</p>
            <p className="text-muted-foreground text-sm">{training.resourceHint}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function TrainingResourcesSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Skeleton className="h-36 rounded-xl" />
      <Skeleton className="h-36 rounded-xl" />
    </div>
  );
}
