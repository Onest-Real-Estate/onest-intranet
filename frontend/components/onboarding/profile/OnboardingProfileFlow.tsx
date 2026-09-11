import { Head, router, usePage, useRemember } from "@inertiajs/react";
import { LogOut } from "lucide-react";
import { useState } from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system";
import { ContactSection } from "@/components/onboarding/profile/ContactSection";
import { CredentialsSection } from "@/components/onboarding/profile/CredentialsSection";
import {
  PROP_FOR_FIELD,
  SECTION_ORDER,
  valuesDiffer,
} from "@/components/onboarding/profile/field-names";
import { IdentitySection } from "@/components/onboarding/profile/IdentitySection";
import {
  CONFIRMATION_FIELD,
  ReviewProblems,
  ReviewSection,
} from "@/components/onboarding/profile/ReviewSection";
import { SectionForm } from "@/components/onboarding/profile/SectionForm";
import { SectionStepper } from "@/components/onboarding/profile/SectionStepper";
import {
  UnsavedChangesDialog,
  useUnsavedChangesGuard,
} from "@/components/onboarding/profile/unsaved-changes";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type {
  OnboardingPageProps,
  OnboardingProfileSectionCode,
  SelfProfileValues,
} from "@/types";

interface SectionDraft {
  key: string;
  values: Record<string, string[]>;
}

/** Overlay unsaved values kept in history onto the server's initial values. */
function applyDraft(
  initial: SelfProfileValues,
  values: Record<string, string[]>,
  fields: string[],
): SelfProfileValues {
  const next = { ...initial } as unknown as Record<string, unknown>;
  for (const field of fields) {
    const prop = PROP_FOR_FIELD[field];
    if (!prop) {
      continue;
    }
    if (field === "languages") {
      // Unchecking every language posts nothing, which still means "none".
      next[prop] = values[field] ?? [];
    } else if (values[field] !== undefined) {
      next[prop] = values[field][0] ?? "";
    }
  }
  return next as unknown as SelfProfileValues;
}

/**
 * The resumable first-login profile, section by section.
 *
 * Self-contained on page props so the dashboard setup dialog can host it
 * without a second implementation. The server decides the current section,
 * each section's status and revision, field requirements, and what review
 * shows; this component renders those decisions and posts values back.
 */
export function OnboardingProfileFlow() {
  const page = usePage<OnboardingPageProps>().props;
  const { profileFlow, initial, saved, validation, csrfToken } = page;
  const current = profileFlow.currentSection;
  const index = Math.max(0, SECTION_ORDER.indexOf(current));
  const section =
    profileFlow.sections.find((item) => item.code === current) ??
    profileFlow.sections[0];

  const editableFields = Object.entries(profileFlow.fields)
    .filter(([, policy]) => policy.section === current && !policy.readOnly)
    .map(([name]) => name);
  // Edits belong to one section at one revision: moving on, or reloading after
  // a conflict, starts clean without an effect to reset it.
  const sectionKey = `${current}:${section?.revision ?? ""}`;

  // Unsaved values live in Inertia's remembered history state, so the
  // browser's Back and Forward buttons bring them back. That is the same
  // per-tab history entry that already holds the page props.
  const [draft, setDraft] = useRemember<SectionDraft | null>(
    null,
    "onboarding-profile-draft",
  );
  const restored =
    current !== "review" && draft?.key === sectionKey
      ? applyDraft(initial, draft.values, editableFields)
      : initial;
  const view = restored === initial ? page : { ...page, initial: restored };

  // After a 422, a conflict, or a restored draft the page opens with values the
  // server has not saved; those are unsaved changes before anything is typed.
  const startsDirty =
    current !== "review" && valuesDiffer(editableFields, restored, saved);
  const [touchedSection, setTouchedSection] = useState<string | null>(null);
  const touched = touchedSection === sectionKey;
  const setTouched = (next: boolean) => setTouchedSection(next ? sectionKey : null);
  const dirty = startsDirty || touched;
  const guard = useUnsavedChangesGuard(dirty);
  const [confirmed, setConfirmed] = useState(false);

  const labels: Record<string, string> = Object.fromEntries(
    Object.entries(profileFlow.fields).map(([name, policy]) => [name, policy.label]),
  );
  labels[CONFIRMATION_FIELD] = "Confirmation";

  function navigate(code: OnboardingProfileSectionCode) {
    if (code === current) {
      return;
    }
    router.get(routes.onboarding(), { section: code });
  }

  function refreshAfterPhoto() {
    router.reload({ only: ["profileFlow", "saved", "user"] });
  }

  const onBack = index > 0 ? () => navigate(SECTION_ORDER[index - 1]) : undefined;
  const commonFormProps = {
    csrfToken,
    validation,
    labels,
    dirty,
    onDirtyChange: (next: boolean) => {
      setTouched(next);
      if (!next) {
        setDraft(null);
      }
    },
    onBack,
  };

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 py-8 sm:py-12">
      <Head title={`${section?.label ?? "Profile"} · Set up your profile`} />

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-2">
          <h1 className="text-2xl leading-8 font-bold tracking-[-0.02em]">
            Set up your agent profile
          </h1>
          <p className="text-muted-foreground max-w-measure text-sm">
            About 3–5 minutes. Each section saves when you continue, so you can stop and
            pick up exactly where you left off.
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => router.post(routes.logout())}
        >
          <LogOut aria-hidden />
          Sign out
        </Button>
      </header>

      <SectionStepper
        sections={profileFlow.sections}
        current={current}
        onNavigate={navigate}
      />

      <SurfaceCard>
        <PanelHeader
          title={section?.label}
          description={section?.description}
          meta={
            <SurfaceCardMeta>
              Step {index + 1} of {SECTION_ORDER.length}
            </SurfaceCardMeta>
          }
          divided
        />
        <SurfaceCardContent>
          {current === "review" ? (
            <SectionForm
              {...commonFormProps}
              action={routes.onboarding_profile_finalize()}
              tokens={{
                expected_onboarding_version: String(profileFlow.onboardingVersion),
              }}
              summary={<ReviewProblems page={page} onNavigate={navigate} />}
              submitLabel="Finish setup"
              submittingLabel="Finishing…"
            >
              <ReviewSection
                page={page}
                confirmed={confirmed}
                onConfirmedChange={setConfirmed}
                onNavigate={navigate}
              />
            </SectionForm>
          ) : (
            <SectionForm
              {...commonFormProps}
              key={`${current}-${section?.revision ?? ""}`}
              action={routes.onboarding_profile_save(current)}
              tokens={{
                revision: section?.revision ?? "",
                expected_onboarding_version: String(profileFlow.onboardingVersion),
              }}
              onDraft={(values) => setDraft({ key: sectionKey, values })}
              submitLabel="Save and continue"
              submittingLabel="Saving…"
            >
              {current === "identity" ? (
                <IdentitySection page={view} onPhotoChange={refreshAfterPhoto} />
              ) : null}
              {current === "contact" ? (
                <ContactSection page={view} onDirty={() => setTouched(true)} />
              ) : null}
              {current === "credentials" ? (
                <CredentialsSection page={view} onDirty={() => setTouched(true)} />
              ) : null}
            </SectionForm>
          )}
        </SurfaceCardContent>
      </SurfaceCard>

      <UnsavedChangesDialog
        open={guard.pendingUrl !== null}
        onStay={guard.stay}
        onLeave={guard.leave}
      />
    </div>
  );
}
