import { CheckCircle2 } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Progress } from "@/components/ui/progress";
import type { ProfileCompleteness } from "@/types";

/**
 * Progress, not a gate. Onboarding is already finished by the time this page
 * loads, so an incomplete score reports what is still worth adding and never
 * withholds anything.
 */
export function ProfileCompletenessPanel({
  completeness,
  sectionAnchors,
}: {
  completeness: ProfileCompleteness;
  sectionAnchors: Record<string, string>;
}) {
  const optional = completeness.missing.filter((item) => !item.required);
  const required = completeness.missing.filter((item) => item.required);

  return (
    <SurfaceCard>
      <PanelHeader
        title="Profile completeness"
        meta={
          <span className="text-sm font-semibold tabular-nums">
            {completeness.percent}%
          </span>
        }
      />
      <SurfaceCardContent className="grid gap-4">
        <Progress
          value={completeness.percent}
          aria-label={`Profile ${completeness.percent} percent complete`}
        />
        <p className="text-muted-foreground text-sm">
          {completeness.completed} of {completeness.total} details filled in.
        </p>

        {required.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="text-sm font-medium">Missing required details</p>
            <ul className="text-muted-foreground grid gap-1 text-sm">
              {required.map((item) => (
                <li key={item.key}>{item.label}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {optional.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="text-sm font-medium">Still worth adding</p>
            <ul className="grid gap-1 text-sm">
              {optional.map((item) => {
                const anchor = sectionAnchors[item.section];
                return (
                  <li key={item.key}>
                    {anchor ? (
                      <a
                        className="text-primary underline-offset-2 hover:underline"
                        href={`#${anchor}`}
                      >
                        {item.label}
                      </a>
                    ) : (
                      item.label
                    )}
                    <span className="text-muted-foreground">
                      {" "}
                      · {item.sectionLabel}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <p className="text-success flex items-center gap-1.5 text-sm">
            <CheckCircle2 className="size-4" aria-hidden />
            Everything on your profile is filled in.
          </p>
        )}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
