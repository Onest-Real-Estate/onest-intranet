import { describe, expect, it } from "vitest";

import {
  onboardingAnnouncement,
  parseOnboardingInvalidation,
} from "@/lib/onboarding/live";
import { activationGuide, agentJourney, agentTool } from "@/test/onboarding";

describe("onboarding live payload", () => {
  it("rejects malformed and unregistered events", () => {
    expect(parseOnboardingInvalidation({ stateVersion: 1 })).toBeNull();
    expect(
      parseOnboardingInvalidation({
        id: "facdb737-47aa-45e4-99a7-835c73973ff5",
        eventType: "onboarding.state_changed",
        sourceKey: "private_note",
        stateVersion: 1,
      }),
    ).toBeNull();
  });

  it("announces the guide unlocked by a newer journey", () => {
    const before = agentJourney({
      tools: [agentTool({ key: "skyslope", label: "SkySlope" })],
      activationGuides: { skyslope: { state: "locked" } },
    });
    const after = agentJourney({
      tools: [agentTool({ key: "skyslope", label: "SkySlope" })],
      activationGuides: { skyslope: activationGuide() },
    });
    expect(onboardingAnnouncement(before, after)).toBe(
      "Your SkySlope activation guide is now available.",
    );
  });

  it("does not announce an invalidation with no visible change", () => {
    const before = agentJourney({ stateVersion: 1 });
    const after = agentJourney({ stateVersion: 2 });
    expect(onboardingAnnouncement(before, after)).toBe("");
  });
});
