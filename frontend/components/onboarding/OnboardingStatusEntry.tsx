import { CircleDot } from "lucide-react";
import type { Ref } from "react";

import { Button } from "@/components/ui/button";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import type { AgentOnboardingJourney } from "@/types";

/**
 * The quiet, persistent way back into the activation center while office staff
 * finish setup. It states the server's handoff message and next action only.
 */
export function OnboardingStatusEntry({
  journey,
  onOpen,
  ref,
}: {
  journey: AgentOnboardingJourney;
  onOpen: () => void;
  ref?: Ref<HTMLButtonElement>;
}) {
  return (
    <section
      aria-labelledby="onboarding-status-title"
      className="bg-card border-border shadow-card flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border px-4 py-3"
    >
      <CircleDot className="text-primary size-4 shrink-0" aria-hidden />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <h2 id="onboarding-status-title" className="text-sm font-semibold">
          {ONBOARDING_COPY.activation.statusTitle}
        </h2>
        <p className="text-muted-foreground text-sm">
          {journey.officeHandoff.message} {journey.nextAction.label}.
        </p>
      </div>
      <Button ref={ref} type="button" variant="outline" size="sm" onClick={onOpen}>
        {ONBOARDING_COPY.activation.statusAction}
      </Button>
    </section>
  );
}
