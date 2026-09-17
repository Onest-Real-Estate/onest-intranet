import { CheckCircle2, Circle, CircleDot, Lock } from "lucide-react";

import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import type { SetupStage, SetupStageState } from "@/lib/onboarding/stages";
import { cn } from "@/lib/utils";

const STATE_ICON = {
  complete: CheckCircle2,
  current: CircleDot,
  upcoming: Circle,
  locked: Lock,
} satisfies Record<SetupStageState, unknown>;

/** Three stages, each a distinct icon plus server wording — never colour alone. */
export function StageRail({ stages }: { stages: SetupStage[] }) {
  return (
    <ol
      aria-label={ONBOARDING_COPY.setup.stagesLabel}
      className="border-border grid grid-cols-3 gap-3 border-y py-3"
    >
      {stages.map((stage) => {
        const Icon = STATE_ICON[stage.state];
        const current = stage.state === "current";
        return (
          <li
            key={stage.code}
            aria-current={current ? "step" : undefined}
            className="flex min-w-0 items-start gap-2"
          >
            <Icon
              aria-hidden
              className={cn(
                "mt-0.5 size-4 shrink-0",
                stage.state === "complete"
                  ? "text-success"
                  : current
                    ? "text-primary"
                    : "text-muted-foreground",
              )}
            />
            <span className="grid min-w-0 gap-0.5">
              <span
                className={cn(
                  "text-xs font-semibold sm:text-sm",
                  current || stage.state === "complete"
                    ? "text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {stage.label}
              </span>
              <span className="text-muted-foreground truncate text-xs">
                {stage.detail}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
