import { Link } from "@inertiajs/react";

import {
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Progress } from "@/components/ui/progress";
import { completionPresentation } from "@/lib/training";
import type { TrainingCourseRollup, TrainingModuleRow } from "@/types";

export function TrainingCourseModules({
  modules,
  rollup,
}: {
  modules: TrainingModuleRow[];
  rollup?: TrainingCourseRollup | null;
}) {
  if (modules.length === 0) {
    return null;
  }
  const percent = rollup?.percent ?? 0;

  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-4">
        <div className="grid gap-2">
          <h2 className="text-sm font-semibold">Course modules</h2>
          {rollup ? (
            <>
              <Progress
                value={percent}
                aria-label={`${rollup.completed} of ${rollup.total} modules complete`}
              />
              <p className="text-muted-foreground text-xs tabular-nums">
                {rollup.completed} of {rollup.total} modules complete
              </p>
            </>
          ) : null}
        </div>
        <ul className="grid gap-2">
          {modules.map((module) => {
            const completion = completionPresentation(
              module.completion?.status ?? "not_started",
            );
            return (
              <li
                key={module.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
              >
                <Link
                  href={module.detailUrl ?? `/training-learning/${module.id}`}
                  className="text-sm font-medium underline-offset-4 hover:underline"
                >
                  {module.title}
                </Link>
                <StatusBadge status={completion} />
              </li>
            );
          })}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
