import { Link } from "@inertiajs/react";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Lock,
  PlayCircle,
} from "lucide-react";

import { Callout } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import {
  type NextStepItem,
  type NextStepState,
  nextStepItems,
} from "@/lib/onboarding/next-steps";
import { cn } from "@/lib/utils";
import type { AgentActivationGuide, AgentOnboardingJourney } from "@/types";

const STATE_ICON = {
  done: CheckCircle2,
  waiting: CircleDashed,
  attention: AlertCircle,
  unavailable: CircleSlash,
} satisfies Record<NextStepState, unknown>;

const STATE_TONE: Record<NextStepState, string> = {
  done: "text-success",
  waiting: "text-muted-foreground",
  attention: "text-warning-ink",
  unavailable: "text-muted-foreground",
};

/**
 * What a row says about its guide when there is no button to press.
 *
 * A locked row says so plainly rather than going quiet: the agent should know
 * a guide is coming and what unlocks it. `available` and `completed` need no
 * note — their button carries the meaning.
 */
function guideNote(guide: AgentActivationGuide | undefined): string | null {
  if (guide?.state === "locked") {
    return ONBOARDING_COPY.nextSteps.guideLocked;
  }
  if (guide?.state === "unavailable") {
    return ONBOARDING_COPY.nextSteps.guideUnavailable;
  }
  if (guide?.state === "completed") {
    return ONBOARDING_COPY.nextSteps.guideCompleted;
  }
  return null;
}

/** Runtime and transcript, shown before the agent commits to opening a video. */
function guideMeta(guide: AgentActivationGuide | undefined): string[] {
  if (!guide || (guide.state !== "available" && guide.state !== "completed")) {
    return [];
  }
  const parts: string[] = [];
  if (guide.estimatedMinutes) {
    parts.push(ONBOARDING_COPY.nextSteps.guideMinutes(guide.estimatedMinutes));
  }
  if (guide.hasTranscript) {
    parts.push(ONBOARDING_COPY.nextSteps.guideTranscript);
  }
  return parts;
}

function Row({ item }: { item: NextStepItem }) {
  const Icon = item.guide?.state === "locked" ? Lock : STATE_ICON[item.state];
  const note = item.note ?? guideNote(item.guide);
  const meta = guideMeta(item.guide);
  return (
    <li className="grid gap-2 py-3 sm:grid-cols-[1.25rem_1fr_auto] sm:gap-x-3">
      <Icon
        aria-hidden
        className={cn("mt-0.5 hidden size-4 shrink-0 sm:block", STATE_TONE[item.state])}
      />
      <div className="grid min-w-0 gap-0.5">
        <span className="flex min-w-0 items-start gap-2 text-sm font-medium">
          <Icon
            aria-hidden
            className={cn("mt-0.5 size-4 shrink-0 sm:hidden", STATE_TONE[item.state])}
          />
          <span className="min-w-0">{item.label}</span>
        </span>
        <span className="text-muted-foreground text-sm">{item.detail}</span>
        {note ? <span className="text-muted-foreground text-xs">{note}</span> : null}
        {meta.length ? (
          <span className="text-muted-foreground text-xs">{meta.join(" · ")}</span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-start gap-2 sm:justify-end">
        <span className="text-muted-foreground order-last shrink-0 self-center text-xs font-medium sm:order-first">
          {ONBOARDING_COPY.nextSteps.state[item.state]}
        </span>
        {item.actions.map((action) => (
          <Button
            key={action.href + action.label}
            asChild
            size="sm"
            variant={action.primary ? "default" : "outline"}
          >
            <Link href={action.href}>
              {item.guide && action.primary ? <PlayCircle aria-hidden /> : null}
              {action.label}
            </Link>
          </Button>
        ))}
      </div>
    </li>
  );
}

/**
 * The activation center's list: office handoff, contract, every catalog tool,
 * and anything still needing attention — plus the inbox guidance that explains
 * where a vendor invitation actually arrives.
 *
 * Adding a tool never touches this component. Rows come from the sources in
 * `next-steps.ts`, and a tool's guide button comes from a server block that was
 * already gated on that tool's own invitation.
 */
export function NextSteps({
  journey,
  guides,
}: {
  journey: AgentOnboardingJourney;
  guides: Record<string, AgentActivationGuide>;
}) {
  const items = nextStepItems({ journey, guides });
  const inbox = journey.invitationInbox;

  return (
    <section aria-labelledby="activation-next-heading" className="grid gap-3">
      <h3 id="activation-next-heading" className="text-sm font-semibold">
        {ONBOARDING_COPY.nextSteps.heading}
      </h3>

      <Callout
        tone={inbox.overdue ? "warning" : "info"}
        title={ONBOARDING_COPY.inbox.heading}
        action={
          inbox.overdue ? (
            <Button asChild size="sm" variant="outline">
              <Link href={inbox.supportHref}>{ONBOARDING_COPY.inbox.support}</Link>
            </Button>
          ) : null
        }
      >
        <p>{ONBOARDING_COPY.inbox.body(inbox.email)}</p>
        <p>{ONBOARDING_COPY.inbox.junk}</p>
        <p>{ONBOARDING_COPY.inbox.safety}</p>
        {inbox.overdue ? (
          <p className="font-medium">
            {ONBOARDING_COPY.inbox.overdue(inbox.followUpHours)}
          </p>
        ) : null}
      </Callout>

      <ul className="divide-border border-border divide-y border-y">
        {items.map((item) => (
          <Row key={item.key} item={item} />
        ))}
      </ul>
    </section>
  );
}
