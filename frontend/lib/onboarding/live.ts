import type { AgentOnboardingJourney } from "@/types";

export interface OnboardingInvalidation {
  id: string;
  eventType: "onboarding.state_changed";
  sourceKey: string;
  stateVersion: number;
}

const SOURCES = new Set([
  "profile",
  "office",
  "ownership",
  "tool",
  "contract",
  "training",
  "blocker",
  "account",
  "access",
]);

export function parseOnboardingInvalidation(
  value: unknown,
): OnboardingInvalidation | null {
  if (!value || typeof value !== "object") return null;
  const event = value as Record<string, unknown>;
  if (
    typeof event.id !== "string" ||
    !/^[0-9a-f-]{36}$/i.test(event.id) ||
    event.eventType !== "onboarding.state_changed" ||
    typeof event.sourceKey !== "string" ||
    !SOURCES.has(event.sourceKey) ||
    typeof event.stateVersion !== "number" ||
    !Number.isSafeInteger(event.stateVersion) ||
    event.stateVersion < 1
  ) {
    return null;
  }
  return event as unknown as OnboardingInvalidation;
}

export function onboardingAnnouncement(
  before: AgentOnboardingJourney,
  after: AgentOnboardingJourney,
): string {
  for (const tool of after.tools) {
    const previous = before.activationGuides?.[tool.key];
    const current = after.activationGuides?.[tool.key];
    if (
      current &&
      (current.state === "available" || current.state === "completed") &&
      previous?.state !== "available" &&
      previous?.state !== "completed"
    ) {
      return `Your ${tool.label} activation guide is now available.`;
    }
  }
  if (before.contract.state !== after.contract.state) {
    return "Your agent contract status has changed.";
  }
  for (const tool of after.tools) {
    if (before.tools.find((item) => item.key === tool.key)?.state !== tool.state) {
      return `Your ${tool.label} setup status has changed.`;
    }
  }
  if (before.officeHandoff.state !== after.officeHandoff.state) {
    return "Your office handoff status has changed.";
  }
  if (
    before.profile.state !== after.profile.state ||
    before.office.state !== after.office.state ||
    before.currentStep.code !== after.currentStep.code ||
    JSON.stringify(before.blockers) !== JSON.stringify(after.blockers)
  ) {
    return "Your onboarding status has changed.";
  }
  return "";
}
