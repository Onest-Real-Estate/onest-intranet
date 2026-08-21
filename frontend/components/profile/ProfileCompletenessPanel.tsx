import { ArrowUpRight, CheckCircle2, CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";

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

  // One authored moment: the bar sweeps to its real value on arrival instead
  // of snapping there before anyone has looked.
  const [shownPercent, setShownPercent] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShownPercent(completeness.percent));
    return () => cancelAnimationFrame(frame);
  }, [completeness.percent]);

  return (
    <SurfaceCard>
      <PanelHeader
        title="Profile completeness"
        meta={
          <span className="text-primary text-lg leading-none font-bold tabular-nums">
            {completeness.percent}%
          </span>
        }
      />
      <SurfaceCardContent className="grid gap-4">
        <Progress
          value={shownPercent}
          aria-label={`Profile ${completeness.percent} percent complete`}
        />
        <p className="text-muted-foreground text-sm tabular-nums">
          {completeness.completed} of {completeness.total} details filled in.
        </p>

        {required.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <CircleAlert className="text-warning-ink size-4" aria-hidden />
              Missing required details
            </p>
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
            <ul className="grid gap-0.5 text-sm">
              {optional.map((item) => {
                const anchor = sectionAnchors[item.section];
                return (
                  <li
                    key={item.key}
                    className="flex items-center justify-between gap-2"
                  >
                    {anchor ? (
                      <a
                        className="group hover:bg-muted/60 -mx-2 flex flex-1 items-center justify-between gap-2 rounded-lg px-2 py-1 transition-colors duration-(--motion-fast)"
                        href={`#${anchor}`}
                      >
                        <span>{item.label}</span>
                        <ArrowUpRight
                          className="text-muted-foreground group-hover:text-primary size-4 shrink-0 transition-colors duration-(--motion-fast)"
                          aria-hidden
                        />
                      </a>
                    ) : (
                      item.label
                    )}
                    <span className="text-muted-foreground">· {item.sectionLabel}</span>
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
