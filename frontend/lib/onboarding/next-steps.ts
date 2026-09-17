import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import type {
  AgentActivationGuide,
  AgentJourneyTool,
  AgentOnboardingJourney,
} from "@/types";

/**
 * What the activation center lists, derived only from server facts.
 *
 * Every row comes from a source function over `NextStepContext`. A future
 * module — equipment, orientation, acknowledgements — adds one source and
 * appears under Next steps without touching this file's renderer, and a future
 * *tool* needs no code at all: it arrives as a catalog row, and its guide as a
 * training item tagged with the same key.
 *
 * Nothing here decides whether a guide is unlocked. The server sends a guide
 * block per tool, already gated on that tool's own invitation; this module only
 * chooses which button that block deserves.
 */

export type NextStepState = "done" | "waiting" | "attention" | "unavailable";

export interface NextStepAction {
  label: string;
  href: string;
  /** The one thing on this row the agent should do now. */
  primary?: boolean;
}

export interface NextStepItem {
  key: string;
  label: string;
  state: NextStepState;
  detail: string;
  /** A quieter third line: why a row is where it is, or what to do about it. */
  note?: string;
  /** Present on tool rows: locked, watchable, finished, or unavailable. */
  guide?: AgentActivationGuide;
  actions: NextStepAction[];
}

export interface NextStepContext {
  journey: AgentOnboardingJourney;
  guides: Record<string, AgentActivationGuide>;
}

export type NextStepSource = (context: NextStepContext) => NextStepItem[];

const officeHandoff: NextStepSource = ({ journey }) => {
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
      actions: [],
    },
  ];
};

const contract: NextStepSource = ({ journey }) => {
  const { state, label, detail, actionHref, actionLabel } = journey.contract;
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
      note: detail,
      actions:
        actionHref && actionLabel
          ? [{ label: actionLabel, href: actionHref, primary: state === "sent" }]
          : [],
    },
  ];
};

/** The button a tool row earns, given what the server says about its guide. */
function toolActions(
  tool: AgentJourneyTool,
  guide: AgentActivationGuide | undefined,
): NextStepAction[] {
  if (guide?.state === "available" && guide.href) {
    return [
      {
        label: ONBOARDING_COPY.nextSteps.watchGuide(tool.label),
        href: guide.href,
        primary: true,
      },
    ];
  }
  if (guide?.state === "completed" && guide.href) {
    return [
      { label: ONBOARDING_COPY.nextSteps.watchAgain(tool.label), href: guide.href },
    ];
  }
  // Unlocked with nothing to watch: send the agent somewhere real rather than
  // rendering a button that opens nothing.
  if (guide?.state === "unavailable") {
    if (tool.helpUrl) {
      return [
        { label: ONBOARDING_COPY.nextSteps.vendorHelp(tool.label), href: tool.helpUrl },
      ];
    }
    if (tool.requestPath) {
      return [
        { label: ONBOARDING_COPY.activation.contactSupport, href: tool.requestPath },
      ];
    }
  }
  return [];
}

function toolState(tool: AgentJourneyTool): NextStepState {
  if (tool.complete) {
    return "done";
  }
  if (tool.status === "blocked") {
    return "attention";
  }
  return tool.status === "unavailable" ? "unavailable" : "waiting";
}

const tools: NextStepSource = ({ journey, guides }) => {
  if (journey.toolsSource === "unavailable") {
    return [
      {
        key: "tools",
        label: ONBOARDING_COPY.nextSteps.tools,
        state: "unavailable",
        detail: ONBOARDING_COPY.nextSteps.toolsUnavailable,
        actions: [],
      },
    ];
  }
  // Catalog-driven: every tool renders the same way, whatever the vendor.
  return journey.tools.map((tool) => {
    const guide = guides[tool.key];
    return {
      key: `tool-${tool.key}`,
      label: tool.label,
      state: toolState(tool),
      detail: tool.invitationState === "sent" ? tool.invitationLabel : tool.statusLabel,
      guide,
      actions: toolActions(tool, guide),
    };
  });
};

const blockers: NextStepSource = ({ journey }) =>
  journey.blockers.map((blocker) => ({
    key: `blocker-${blocker.key}`,
    label: ONBOARDING_COPY.nextSteps.blocker,
    state: "attention" as const,
    detail: blocker.message,
    actions: [],
  }));

export const NEXT_STEP_SOURCES: readonly NextStepSource[] = [
  officeHandoff,
  contract,
  tools,
  blockers,
];

export function nextStepItems(
  context: NextStepContext,
  sources: readonly NextStepSource[] = NEXT_STEP_SOURCES,
): NextStepItem[] {
  return sources.flatMap((source) => source(context));
}
