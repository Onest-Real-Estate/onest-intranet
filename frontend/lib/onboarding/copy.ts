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
    heading: "What happens next",
    watchGuide: (tool: string) => `Watch how to activate ${tool}`,
    watchAgain: (tool: string) => `Watch the ${tool} guide again`,
    vendorHelp: (tool: string) => `Open ${tool} help`,
    guideLocked: "The activation guide unlocks when your office sends the invitation.",
    guideUnavailable:
      "No activation guide is published for this tool yet. Use the help link or raise a support request.",
    guideCompleted: "You finished this guide.",
    guideMinutes: (minutes: number) => `${minutes} min`,
    guideTranscript: "Transcript available",
    state: {
      done: "Done",
      waiting: "Waiting",
      attention: "Needs attention",
      unavailable: "Unavailable",
    },
  },
  /**
   * Watching the inbox. The Hub cannot see an agent's mailbox, so none of this
   * claims a delivery — it says where an invitation is sent and what to do if
   * it does not arrive. It never asks for a link, a code, or a password.
   */
  inbox: {
    heading: "Watch your Microsoft Outlook inbox",
    body: (email: string) =>
      `Vendor invitations are sent to ${email}. They come from the vendor, not from the Hub.`,
    junk: "If you cannot find one, check Junk and the Other tab in Outlook.",
    safety:
      "Never paste an invitation link, code, or password into the Hub. Activate each account on the vendor's own site.",
    overdue: (hours: number) =>
      `An invitation was sent more than ${hours} hours ago and is still not set up. Raise a support request and we will chase it.`,
    support: "Contact IT Support",
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
