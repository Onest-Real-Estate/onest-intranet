/**
 * Every sentence the onboarding dialog says on its own behalf.
 *
 * Wording that reports what the server has recorded — the office handoff,
 * contract, tool invitations, blockers — is not here. It arrives as labels on
 * the journey payload, so nothing in this file can claim a delivery, an
 * invitation, or an activation the server has not proven.
 */
export const ONBOARDING_COPY = {
  setup: {
    title: "Finish setting up your oNEST profile",
    description:
      "We use these details for your office, contracts, and internal directory.",
    headTitle: "Set up your profile",
    signOut: "Sign out",
    signingOut: "Signing out…",
    stagesLabel: "Setup stages",
    stepOf: (step: number, total: number) => `Step ${step} of ${total}`,
    stepAnnouncement: (step: number, total: number, label: string) =>
      `Step ${step} of ${total}: ${label}`,
    completedSections: (labels: string[]) =>
      labels.length > 0 ? `Done: ${labels.join(", ")}` : "Nothing saved yet",
    afterSubmit:
      "When you finish, your details go to your office so they can set up your account. You can use the Hub while they work.",
    unavailableTitle: "Setup could not load",
    unavailable:
      "Your setup details could not be loaded. Reload the page to pick up where you left off.",
  },
  stages: {
    profile: "Your profile",
    office: "Your office",
    nextSteps: "Next steps",
  },
  stageState: {
    locked: "After setup",
    inProgress: "In progress",
    complete: "Complete",
  },
  activation: {
    title: "Next steps",
    description: "Your office administrator is handling the next steps.",
    completeDescription: "Your onboarding is complete.",
    unlocked: "Your profile and office are confirmed. Next steps are now available.",
    continue: "Continue to dashboard",
    officeHeading: "Your office",
    nextStepsHeading: "What happens next",
    contactSupport: "Contact IT Support",
    statusTitle: "Setup in progress",
    statusAction: "View setup",
  },
  nextSteps: {
    officeHandoff: "Office handoff",
    contract: "Agent contract",
    tools: "Brokerage tools",
    toolsUnavailable: "Tool status is not available right now.",
    blocker: "Needs attention",
    state: {
      done: "Done",
      waiting: "Waiting",
      attention: "Needs attention",
      unavailable: "Unavailable",
    },
  },
  office: {
    administratorUnavailable: "Office administrator unavailable",
  },
  signOutGuard: {
    title: "Sign out without saving?",
    description:
      "The changes in this section have not been saved. Everything you saved earlier stays exactly as it was.",
    confirm: "Sign out",
    stay: "Keep editing",
  },
} as const;
