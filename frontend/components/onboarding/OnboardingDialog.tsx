import { Head, router } from "@inertiajs/react";
import { LogOut } from "lucide-react";
import { type RefObject, useEffect, useRef, useState } from "react";

import {
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/design-system";
import { ActivationCenter } from "@/components/onboarding/ActivationCenter";
import { OnboardingProfileFlow } from "@/components/onboarding/profile/OnboardingProfileFlow";
import { UnsavedChangesDialog } from "@/components/onboarding/profile/unsaved-changes";
import { StageRail } from "@/components/onboarding/StageRail";
import { Button } from "@/components/ui/button";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import { setupStages } from "@/lib/onboarding/stages";
import { routes } from "@/lib/routes";
import type {
  AgentOnboardingJourney,
  DashboardPageProps,
  OnboardingPageProps,
} from "@/types";

// A centred dialog from `sm` up. Narrower, a full-height sheet that keeps its
// content inside the safe area and drops the centred entrance transform, which
// would otherwise pull the sheet off the top edge while it animates.
const SURFACE =
  "gap-6 sm:max-h-[calc(100svh-4rem)] sm:max-w-3xl max-sm:inset-0 max-sm:top-0 max-sm:left-0 max-sm:h-dvh max-sm:max-h-dvh max-sm:w-full max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:animate-none max-sm:rounded-none max-sm:border-0 max-sm:pt-[max(1.25rem,env(safe-area-inset-top))] max-sm:pb-[max(1.25rem,env(safe-area-inset-bottom))] max-sm:ps-[max(1rem,env(safe-area-inset-left))] max-sm:pe-[max(1rem,env(safe-area-inset-right))]";

const preventDismiss = (event: Event) => event.preventDefault();

/**
 * The dashboard-owned onboarding dialog.
 *
 * While the journey's strict gate is active it cannot be dismissed — no close
 * button, Escape, or outside click — and hosts the profile flow; signing out
 * stays available. Once the server releases the gate the same dialog becomes
 * the activation center, which the agent may close and reopen. The overlay is
 * presentation only: the server withholds dashboard data and blocks other
 * routes while the gate is active.
 */
export function OnboardingDialog({
  page,
  journey,
  open,
  onOpenChange,
  returnFocusRef,
}: {
  page: DashboardPageProps;
  journey: AgentOnboardingJourney;
  /** The activation center's open state; ignored while the gate is strict. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
}) {
  const strict = journey.strictGateActive;
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  // Finishing review keeps this dialog mounted; say what just unlocked.
  const wasStrict = useRef(strict);
  useEffect(() => {
    if (wasStrict.current && !strict) {
      setAnnouncement(ONBOARDING_COPY.activation.unlocked);
      titleRef.current?.focus();
    }
    wasStrict.current = strict;
  }, [strict]);

  function signOut() {
    setConfirmingSignOut(false);
    if (signingOut) {
      return;
    }
    setSigningOut(true);
    router.post(routes.logout(), {}, { onFinish: () => setSigningOut(false) });
  }

  const profilePage: OnboardingPageProps | null = page.onboardingProfile
    ? { ...page, ...page.onboardingProfile }
    : null;

  let title: string;
  let description: string;
  if (strict) {
    title = ONBOARDING_COPY.setup.title;
    description = ONBOARDING_COPY.setup.description;
  } else {
    title = ONBOARDING_COPY.activation.title;
    description =
      journey.officeHandoff.state === "notification_failed"
        ? journey.officeHandoff.message
        : journey.activationComplete
          ? ONBOARDING_COPY.activation.completeDescription
          : ONBOARDING_COPY.activation.description;
  }

  return (
    <Dialog
      open={strict || open}
      onOpenChange={(next) => {
        if (!strict) {
          onOpenChange(next);
        }
      }}
    >
      <DialogContent
        showCloseButton={!strict}
        fallbackFocusRef={returnFocusRef}
        className={SURFACE}
        onOpenAutoFocus={(event) => {
          // Start at the title so the dialog is read from the top, not at
          // whichever control happens to come first.
          event.preventDefault();
          titleRef.current?.focus();
        }}
        onEscapeKeyDown={strict ? preventDismiss : undefined}
        onPointerDownOutside={strict ? preventDismiss : undefined}
        onInteractOutside={strict ? preventDismiss : undefined}
      >
        <p role="status" className="sr-only">
          {announcement}
        </p>
        <DialogHeader className={strict ? "pr-0" : undefined}>
          <div className="flex items-start justify-between gap-4">
            <div className="grid min-w-0 gap-2">
              <DialogTitle
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl leading-8 font-semibold tracking-[-0.02em] outline-none"
              >
                {title}
              </DialogTitle>
              <DialogDescription className="max-w-measure">
                {description}
              </DialogDescription>
            </div>
            {strict ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="shrink-0"
                disabled={signingOut}
                aria-busy={signingOut || undefined}
                onClick={() => (dirty ? setConfirmingSignOut(true) : signOut())}
              >
                <LogOut aria-hidden />
                {signingOut
                  ? ONBOARDING_COPY.setup.signingOut
                  : ONBOARDING_COPY.setup.signOut}
              </Button>
            ) : null}
          </div>
        </DialogHeader>

        <StageRail stages={setupStages(journey)} />

        {strict ? (
          profilePage ? (
            <OnboardingProfileFlow page={profilePage} onDirtyChange={setDirty} />
          ) : (
            <>
              <Head title={ONBOARDING_COPY.setup.headTitle} />
              <Callout tone="warning" title={ONBOARDING_COPY.setup.unavailableTitle}>
                {ONBOARDING_COPY.setup.unavailable}
              </Callout>
            </>
          )
        ) : (
          <ActivationCenter
            journey={journey}
            office={page.onboardingActivation?.office ?? null}
            onContinue={() => onOpenChange(false)}
          />
        )}

        <UnsavedChangesDialog
          open={confirmingSignOut}
          onStay={() => setConfirmingSignOut(false)}
          onLeave={signOut}
          title={ONBOARDING_COPY.signOutGuard.title}
          description={ONBOARDING_COPY.signOutGuard.description}
          leaveLabel={ONBOARDING_COPY.signOutGuard.confirm}
          stayLabel={ONBOARDING_COPY.signOutGuard.stay}
        />
      </DialogContent>
    </Dialog>
  );
}
