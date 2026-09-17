import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import type { AgentOnboardingJourney } from "@/types";

/**
 * What the onboarding dialog shows, derived only from the canonical journey.
 *
 * Three stages summarize the server's milestones; nothing here decides a
 * milestone. `nextStepItems` reads a list of sources so a later module
 * (equipment, orientation, acknowledgements) adds one source function and
 * appears under Next steps without touching the profile form or access policy.
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

export type NextStepState = "done" | "waiting" | "attention" | "unavailable";

export interface NextStepItem {
  key: string;
  label: string;
  state: NextStepState;
  detail: string;
}

export type NextStepSource = (journey: AgentOnboardingJourney) => NextStepItem[];

const officeHandoff: NextStepSource = (journey) => {
  const { state, message } = journey.officeHandoff;
  return [
    {
      key: "office-handoff",
      label: ONBOARDING_COPY.nextSteps.officeHandoff,
      state:
        state === "notified"
          ? "done"
          : state === "notification_failed"
            ? "attention"
            : "waiting",
      detail: message,
    },
  ];
};

const contract: NextStepSource = (journey) => {
  const { state, label } = journey.contract;
  return [
    {
      key: "contract",
      label: ONBOARDING_COPY.nextSteps.contract,
      state:
        state === "active" || state === "signed"
          ? "done"
          : state === "blocked"
            ? "attention"
            : state === "unavailable"
              ? "unavailable"
              : "waiting",
      detail: label,
    },
  ];
};

const tools: NextStepSource = (journey) => {
  if (journey.toolsSource === "unavailable") {
    return [
      {
        key: "tools",
        label: ONBOARDING_COPY.nextSteps.tools,
        state: "unavailable",
        detail: ONBOARDING_COPY.nextSteps.toolsUnavailable,
      },
    ];
  }
  // Catalog-driven: every tool renders the same way, whatever the vendor.
  return journey.tools.map((tool) => ({
    key: `tool-${tool.key}`,
    label: tool.label,
    state: tool.complete
      ? "done"
      : tool.status === "blocked"
        ? "attention"
        : tool.status === "unavailable"
          ? "unavailable"
          : "waiting",
    detail: tool.invitationState === "sent" ? tool.invitationLabel : tool.statusLabel,
  }));
};

const blockers: NextStepSource = (journey) =>
  journey.blockers.map((blocker) => ({
    key: `blocker-${blocker.key}`,
    label: ONBOARDING_COPY.nextSteps.blocker,
    state: "attention",
    detail: blocker.message,
  }));

export const NEXT_STEP_SOURCES: readonly NextStepSource[] = [
  officeHandoff,
  contract,
  tools,
  blockers,
];

export function nextStepItems(
  journey: AgentOnboardingJourney,
  sources: readonly NextStepSource[] = NEXT_STEP_SOURCES,
): NextStepItem[] {
  return sources.flatMap((source) => source(journey));
}
