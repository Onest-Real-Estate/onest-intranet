import { describe, expect, it } from "vitest";

import {
  NEXT_STEP_SOURCES,
  type NextStepSource,
  nextStepItems,
  setupStages,
} from "@/lib/onboarding/stages";
import type { AgentOnboardingJourney } from "@/types";

function journey(
  overrides: Partial<AgentOnboardingJourney> = {},
): AgentOnboardingJourney {
  return {
    schemaVersion: 1,
    profile: { state: "complete", label: "Complete", updatedAt: null },
    office: { state: "confirmed", label: "Confirmed", updatedAt: null },
    officeHandoff: {
      state: "pending",
      label: "Pending",
      updatedAt: null,
      recipient: null,
      message: "We are recording the handoff to your office administrator.",
      delivery: { state: "pending", label: "Pending", channels: [] },
    },
    contract: { state: "sent", label: "Sent", updatedAt: null },
    toolsSource: "available",
    tools: [],
    requiredSetupComplete: true,
    activationComplete: false,
    strictGateActive: false,
    currentStep: { code: "activation", label: "Activation" },
    nextAction: {
      code: "wait_for_office",
      label: "Your office administrator is handling the next steps",
      href: null,
      method: null,
    },
    version: "1:now",
    updatedAt: "2026-08-19T09:00:00-04:00",
    blockers: [],
    ...overrides,
  };
}

describe("setupStages", () => {
  it("marks the server's current step and locks next steps until release", () => {
    const stages = setupStages(
      journey({
        profile: { state: "complete", label: "Complete", updatedAt: null },
        office: { state: "selected", label: "Selected", updatedAt: null },
        requiredSetupComplete: false,
        strictGateActive: true,
        currentStep: { code: "office", label: "Office" },
      }),
    );
    expect(stages.map(({ code, state, detail }) => [code, state, detail])).toEqual([
      ["profile", "complete", "Complete"],
      ["office", "current", "Selected"],
      ["next_steps", "locked", "After setup"],
    ]);
  });

  it("completes next steps only when the server says activation is complete", () => {
    expect(setupStages(journey())[2].state).toBe("current");
    expect(setupStages(journey({ activationComplete: true }))[2].state).toBe(
      "complete",
    );
  });
});

describe("nextStepItems", () => {
  it("states an unavailable tool source once instead of inventing tool progress", () => {
    const items = nextStepItems(journey({ toolsSource: "unavailable" }));
    expect(items.map((item) => [item.key, item.state])).toEqual([
      ["office-handoff", "waiting"],
      ["contract", "waiting"],
      ["tools", "unavailable"],
    ]);
  });

  it("surfaces server blockers as items needing attention", () => {
    const items = nextStepItems(
      journey({ blockers: [{ key: "task-1", message: "Upload your W-9." }] }),
    );
    expect(items.at(-1)).toMatchObject({
      state: "attention",
      detail: "Upload your W-9.",
    });
  });

  it("lets a later module add a source without touching the dialog", () => {
    const orientation: NextStepSource = () => [
      { key: "orientation", label: "Orientation", state: "waiting", detail: "Soon" },
    ];
    const items = nextStepItems(journey(), [...NEXT_STEP_SOURCES, orientation]);
    expect(items.at(-1)?.key).toBe("orientation");
  });
});
