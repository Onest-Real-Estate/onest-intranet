import { Link } from "@inertiajs/react";
import { AlertCircle, CheckCircle2, CircleDashed, CircleSlash } from "lucide-react";

import { DialogFooter } from "@/components/design-system";
import { OfficeDetails } from "@/components/onboarding/OfficeDetails";
import { Button } from "@/components/ui/button";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import { type NextStepState, nextStepItems } from "@/lib/onboarding/stages";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { AgentOnboardingJourney, OnboardingOfficeSelection } from "@/types";

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
 * The released dialog: what is confirmed, who has the case, and what is still
 * waiting on someone else. One gold action — the server's next action when it
 * has a destination, otherwise returning to the dashboard.
 */
export function ActivationCenter({
  journey,
  office,
  onContinue,
}: {
  journey: AgentOnboardingJourney;
  office: OnboardingOfficeSelection | null;
  onContinue: () => void;
}) {
  const items = nextStepItems(journey);
  const action = journey.nextAction;
  const handoffFailed = journey.officeHandoff.state === "notification_failed";

  return (
    <>
      {office ? (
        <section aria-labelledby="activation-office-heading" className="grid gap-2">
          <h3 id="activation-office-heading" className="text-sm font-semibold">
            {ONBOARDING_COPY.activation.officeHeading}
          </h3>
          <OfficeDetails selection={office} />
        </section>
      ) : null}

      <section aria-labelledby="activation-next-heading" className="grid gap-2">
        <h3 id="activation-next-heading" className="text-sm font-semibold">
          {ONBOARDING_COPY.activation.nextStepsHeading}
        </h3>
        <ul className="divide-border border-border divide-y border-y">
          {items.map((item) => {
            const Icon = STATE_ICON[item.state];
            return (
              <li key={item.key} className="flex items-start gap-3 py-3">
                <Icon
                  aria-hidden
                  className={cn("mt-0.5 size-4 shrink-0", STATE_TONE[item.state])}
                />
                <div className="grid min-w-0 flex-1 gap-0.5">
                  <span className="text-sm font-medium">{item.label}</span>
                  <span className="text-muted-foreground text-sm">{item.detail}</span>
                </div>
                <span className="text-muted-foreground shrink-0 text-xs font-medium">
                  {ONBOARDING_COPY.nextSteps.state[item.state]}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <DialogFooter>
        {handoffFailed ? (
          <Button asChild variant="outline">
            <Link href={routes.it_support()}>
              {ONBOARDING_COPY.activation.contactSupport}
            </Link>
          </Button>
        ) : null}
        {action.href ? (
          <>
            <Button type="button" variant="outline" onClick={onContinue}>
              {ONBOARDING_COPY.activation.continue}
            </Button>
            <Button asChild>
              <Link href={action.href}>{action.label}</Link>
            </Button>
          </>
        ) : (
          <Button type="button" onClick={onContinue}>
            {ONBOARDING_COPY.activation.continue}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
