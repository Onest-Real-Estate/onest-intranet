import { Link } from "@inertiajs/react";

import { DialogFooter } from "@/components/design-system";
import { NextSteps } from "@/components/onboarding/NextSteps";
import { OfficeDetails } from "@/components/onboarding/OfficeDetails";
import { Button } from "@/components/ui/button";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import { routes } from "@/lib/routes";
import type {
  AgentActivationGuide,
  AgentOnboardingJourney,
  OnboardingOfficeSelection,
} from "@/types";

/**
 * The released dialog: what is confirmed, who has the case, and what is still
 * waiting on someone else. One gold action — the server's next action when it
 * has a destination, otherwise returning to the dashboard.
 */
export function ActivationCenter({
  journey,
  office,
  guides,
  onContinue,
}: {
  journey: AgentOnboardingJourney;
  office: OnboardingOfficeSelection | null;
  /** Per-tool activation guides, already gated server-side. */
  guides: Record<string, AgentActivationGuide>;
  onContinue: () => void;
}) {
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

      <NextSteps journey={journey} guides={guides} />

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
