import { describe, expect, it } from "vitest";

import { setupStages } from "@/lib/onboarding/stages";
import { agentJourney as journey } from "@/test/onboarding";

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
