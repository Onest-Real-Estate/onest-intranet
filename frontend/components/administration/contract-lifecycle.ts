import {
  BadgeCheck,
  CalendarX2,
  CircleSlash,
  Eye,
  type LucideIcon,
  PenLine,
  RefreshCw,
  Send,
  Undo2,
} from "lucide-react";

import type { StatusTone } from "@/types/design-system";

/**
 * Every action code `apps.contract.lifecycle.allowed_actions` can hand the
 * workspace.
 *
 * This list is the frontend half of a two-sided contract. The sidebar used to
 * be a hand-written run of `allowedActions.includes(...)` checks, and it drifted
 * from the server: `mark_viewed`, `mark_signed`, and `expire` were authorized
 * and had no button, which dead-ended every contract at `sent`. The registry
 * below is now the only place an action is described, and
 * `test_lifecycle_actions_have_buttons` fails if the server learns a code this
 * file does not carry.
 */
export type LifecycleActionCode =
  | "submit_for_review"
  | "reopen"
  | "issue"
  | "mark_viewed"
  | "mark_signed"
  | "activate"
  | "retry_generation"
  | "supersede"
  | "expire"
  | "terminate";

/**
 * What the action is *for*, which decides where it sits and how loud it is.
 *
 * - `advance` moves the agreement toward being the agent's live contract.
 *   The earliest available one is the page's single primary action.
 * - `revise` walks something back or retries it — available, never suggested.
 * - `end` closes this version out. Separated by a rule, because the distance
 *   between "send this to the agent" and "terminate this agreement" should not
 *   be one mis-aimed click.
 */
export type LifecycleIntent = "advance" | "revise" | "end";

export interface LifecycleActionSpec {
  label: string;
  intent: LifecycleIntent;
  icon: LucideIcon;
  /** One line under the button when the move is not self-evident. */
  hint?: string;
}

/**
 * Order matters twice: it ranks the buttons inside a group, and for `advance`
 * it decides which single move is the gold one. At `sent` the server allows
 * both `mark_viewed` and `mark_signed`; the expected next step leads and the
 * skip-ahead stays available but quiet.
 */
export const LIFECYCLE_ACTION_ORDER: LifecycleActionCode[] = [
  "submit_for_review",
  "issue",
  "mark_viewed",
  "mark_signed",
  "activate",
  "reopen",
  "retry_generation",
  "supersede",
  "expire",
  "terminate",
];

export const LIFECYCLE_ACTIONS: Record<LifecycleActionCode, LifecycleActionSpec> = {
  submit_for_review: {
    label: "Submit for review",
    intent: "advance",
    icon: Send,
    hint: "Locks the draft for a reviewer without sending it to the agent.",
  },
  issue: {
    label: "Issue for company signature",
    intent: "advance",
    icon: Send,
    hint: "Freezes terms, queues the PDF, and waits for the named company officer to sign.",
  },
  mark_viewed: {
    label: "Mark as viewed",
    intent: "advance",
    icon: Eye,
    hint: "Record that the agent opened the agreement outside the Hub.",
  },
  mark_signed: {
    label: "Mark as signed",
    intent: "advance",
    icon: PenLine,
    hint: "Record a signature captured on paper or outside the Hub.",
  },
  activate: {
    label: "Activate",
    intent: "advance",
    icon: BadgeCheck,
    hint: "Make this the agent's governing agreement.",
  },
  reopen: {
    label: "Reopen draft",
    intent: "revise",
    icon: Undo2,
    hint: "Return to draft so the terms can be edited again.",
  },
  retry_generation: {
    label: "Retry PDF generation",
    intent: "revise",
    icon: RefreshCw,
  },
  supersede: {
    label: "Supersede",
    intent: "end",
    icon: CircleSlash,
    hint: "End this version because a replacement takes its place.",
  },
  expire: {
    label: "Expire",
    intent: "end",
    icon: CalendarX2,
    hint: "Close out an agreement that has reached its end date.",
  },
  terminate: {
    label: "Terminate",
    intent: "end",
    icon: CircleSlash,
    hint: "End the agreement outright. Terminal and not reversible here.",
  },
};

/**
 * Moves the server refuses without `confirmed=true`, plus `expire`.
 *
 * `expire` is not on the server's `CONFIRM_REQUIRED` list, but it writes a
 * terminal status: confirming it here costs one click and the extra flag is
 * inert for an action that does not read it.
 */
export type ConfirmLifecycleAction =
  | "issue"
  | "activate"
  | "supersede"
  | "expire"
  | "terminate";

export interface LifecycleConfirmCopy {
  title: string;
  description: string;
  confirmLabel: string;
  toLabel: string;
  impact: string;
}

export const CONFIRM_LIFECYCLE: Record<ConfirmLifecycleAction, LifecycleConfirmCopy> = {
  issue: {
    title: "Issue this contract?",
    description:
      "Freezes party, office, terms, template version, and calculation rule version, then queues PDF generation and waits for the named company officer to sign before releasing the agreement to the agent.",
    confirmLabel: "Confirm issue",
    toLabel: "Awaiting company signature",
    impact: "The named company signatory must sign before the agent can.",
  },
  activate: {
    title: "Activate this contract?",
    description:
      "Marks the signed agreement as the agent's active brokerage contract and supersedes any prior active contract for the same recipient.",
    confirmLabel: "Confirm activate",
    toLabel: "Active",
    impact: "Onboarding and operations treat this version as the live agreement.",
  },
  supersede: {
    title: "Supersede this contract?",
    description:
      "Ends this version without terminating the agent relationship. Use when a replacement agreement will take its place.",
    confirmLabel: "Confirm supersede",
    toLabel: "Superseded",
    impact: "This version leaves the active pipeline and cannot be reactivated.",
  },
  expire: {
    title: "Expire this contract?",
    description:
      "Closes out an agreement that has reached its end date. The agent keeps the record but no longer has a governing agreement from this version.",
    confirmLabel: "Confirm expire",
    toLabel: "Expired",
    impact: "This version leaves the active pipeline and cannot be reactivated.",
  },
  terminate: {
    title: "Terminate this contract?",
    description:
      "Ends this agreement. This is a terminal status and cannot be undone from the workspace.",
    confirmLabel: "Confirm terminate",
    toLabel: "Terminated",
    impact: "The agent no longer has this version as a live or pending agreement.",
  },
};

export function isLifecycleActionCode(value: string): value is LifecycleActionCode {
  return value in LIFECYCLE_ACTIONS;
}

export function needsConfirmation(
  code: LifecycleActionCode,
): code is ConfirmLifecycleAction {
  return code in CONFIRM_LIFECYCLE;
}

/** Timestamp keys on the serialized contract, in pipeline order. */
type StampKey =
  | "createdAt"
  | "companySignedAt"
  | "sentAt"
  | "viewedAt"
  | "signedAt"
  | "activatedAt"
  | "supersededAt"
  | "expiredAt"
  | "terminatedAt";

interface PipelineStep {
  code: string;
  label: string;
  stamp: StampKey | null;
}

/** The happy path, in the order `_TARGET_STATUS` moves a contract through it. */
const PIPELINE: PipelineStep[] = [
  { code: "draft", label: "Draft", stamp: "createdAt" },
  { code: "ready_for_review", label: "Ready for review", stamp: null },
  {
    code: "awaiting_company_signature",
    label: "Awaiting company signature",
    stamp: "companySignedAt",
  },
  { code: "sent", label: "Sent to agent", stamp: "sentAt" },
  { code: "viewed", label: "Viewed", stamp: "viewedAt" },
  { code: "signed", label: "Signed", stamp: "signedAt" },
  { code: "active", label: "Active", stamp: "activatedAt" },
];

const TERMINAL: Record<string, { label: string; stamp: StampKey; tone: StatusTone }> = {
  superseded: { label: "Superseded", stamp: "supersededAt", tone: "neutral" },
  expired: { label: "Expired", stamp: "expiredAt", tone: "warning" },
  terminated: { label: "Terminated", stamp: "terminatedAt", tone: "destructive" },
};

export type ContractStamps = Partial<Record<StampKey, string | null>>;

export interface LifecycleStep {
  id: string;
  label: string;
  /** ISO stamp for the moment the step was reached, when one was recorded. */
  at: string | null;
  state: "done" | "current" | "upcoming";
  tone: StatusTone;
}

/**
 * Where this contract sits in the pipeline, and how far it actually travelled.
 *
 * A terminal or errored contract has left the happy path, so its position is
 * read back off the timestamps rather than off the status: a contract that was
 * terminated while `sent` should show three steps behind it, not none.
 */
export function lifecycleSteps(
  status: string,
  stamps: ContractStamps,
): LifecycleStep[] {
  const stampedIndex = PIPELINE.reduce(
    (furthest, step, index) => (step.stamp && stamps[step.stamp] ? index : furthest),
    0,
  );
  const directIndex = PIPELINE.findIndex((step) => step.code === status);
  const terminal = TERMINAL[status];
  const errored = status === "generation_error";
  // Generation failure happens after issue, while waiting on company signature
  // (or after company signing, while still `sent`). Index 2 is that gate.
  const currentIndex = errored
    ? Math.max(stampedIndex, 2)
    : directIndex >= 0
      ? directIndex
      : stampedIndex;

  const walked = terminal || errored ? currentIndex + 1 : PIPELINE.length;
  const steps: LifecycleStep[] = PIPELINE.slice(0, walked).map((step, index) => {
    const at = step.stamp ? (stamps[step.stamp] ?? null) : null;
    if (index < currentIndex || ((terminal || errored) && index <= currentIndex)) {
      return { id: step.code, label: step.label, at, state: "done", tone: "success" };
    }
    if (index === currentIndex) {
      return { id: step.code, label: step.label, at, state: "current", tone: "info" };
    }
    return { id: step.code, label: step.label, at, state: "upcoming", tone: "neutral" };
  });

  if (terminal) {
    steps.push({
      id: status,
      label: terminal.label,
      at: stamps[terminal.stamp] ?? null,
      state: "current",
      tone: terminal.tone,
    });
  } else if (errored) {
    steps.push({
      id: status,
      label: "Generation error",
      at: null,
      state: "current",
      tone: "destructive",
    });
  }

  return steps;
}
