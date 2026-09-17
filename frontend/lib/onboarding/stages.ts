import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import type { AgentOnboardingJourney } from "@/types";

/**
 * What the onboarding dialog shows, derived only from the canonical journey.
 *
 * Three stages summarize the server's milestones; nothing here decides a
 * milestone. The rows under the last stage live in `next-steps.ts`.
 */

export type SetupStageCode = "profile" | "office" | "next_steps";
export type SetupStageState = "complete" | "current" | "upcoming" | "locked";

export interface SetupStage {
  code: SetupStageCode;
  label: string;
  state: SetupStageState;
  /** Server wording for the stage's state, shown beside its icon. */
  detail: string;
}

export function setupStages(journey: AgentOnboardingJourney): SetupStage[] {
  const step = journey.currentStep.code;
  const profileComplete = journey.profile.state === "complete";
  const officeComplete = journey.office.state === "confirmed";
  let nextSteps: Pick<SetupStage, "state" | "detail">;
  if (!journey.requiredSetupComplete) {
    nextSteps = { state: "locked", detail: ONBOARDING_COPY.stageState.locked };
  } else if (journey.activationComplete) {
    nextSteps = { state: "complete", detail: ONBOARDING_COPY.stageState.complete };
  } else {
    nextSteps = { state: "current", detail: ONBOARDING_COPY.stageState.inProgress };
  }
  return [
    {
      code: "profile",
      label: ONBOARDING_COPY.stages.profile,
      state: profileComplete ? "complete" : step === "profile" ? "current" : "upcoming",
      detail: journey.profile.label,
    },
    {
      code: "office",
      label: ONBOARDING_COPY.stages.office,
      state: officeComplete ? "complete" : step === "office" ? "current" : "upcoming",
      detail: journey.office.label,
    },
    { code: "next_steps", label: ONBOARDING_COPY.stages.nextSteps, ...nextSteps },
  ];
}
