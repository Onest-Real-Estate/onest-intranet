import { Head, router, useRemember } from "@inertiajs/react";
import { useEffect, useRef, useState } from "react";

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
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
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
 * The resumable first-login profile, section by section, inside the dashboard
 * setup dialog.
 *
 * The server decides the current section, each section's status and revision,
 * field requirements, and what review shows; this component renders those
 * decisions and posts values back. Section visits keep the dialog mounted, so
 * focus moves to the new section's heading and the change is announced.
 */
export function OnboardingProfileFlow({
  page,
  onDirtyChange,
}: {
  page: OnboardingPageProps;
  /** Lets the dialog warn before signing out over unsaved edits. */
  onDirtyChange?: (dirty: boolean) => void;
}) {
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
  const restoredOfficeConfirmed =
    current === "credentials" && draft?.key === sectionKey
      ? draft.values.confirm_office?.[0] === "true"
      : page.officeConfirmed;
  const sectionView =
    view.officeConfirmed === restoredOfficeConfirmed
      ? view
      : { ...view, officeConfirmed: restoredOfficeConfirmed };

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

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const shownSection = useRef(current);
  const [announcement, setAnnouncement] = useState("");
  const sectionLabel = section?.label ?? "";
  useEffect(() => {
    if (shownSection.current === current) {
      return;
    }
    shownSection.current = current;
    setAnnouncement(
      ONBOARDING_COPY.setup.stepAnnouncement(
        index + 1,
        SECTION_ORDER.length,
        sectionLabel,
      ),
    );
    headingRef.current?.focus();
  }, [current, index, sectionLabel]);

  const labels: Record<string, string> = Object.fromEntries(
    Object.entries(profileFlow.fields).map(([name, policy]) => [name, policy.label]),
  );
  labels[CONFIRMATION_FIELD] = "Confirmation";
  labels.confirm_office = "Office confirmation";
  const completedLabels = profileFlow.sections
    .filter((item) => item.status === "complete")
    .map((item) => item.label);

  function navigate(code: OnboardingProfileSectionCode) {
    if (code === current) {
      return;
    }
    router.get(routes.dashboard(), { section: code }, { preserveState: true });
  }

  function refreshAfterPhoto() {
    router.reload({ only: ["onboardingProfile", "onboardingJourney", "user"] });
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
    <div className="grid gap-5">
      <Head
        title={`${sectionLabel || "Profile"} · ${ONBOARDING_COPY.setup.headTitle}`}
      />
      <p role="status" className="sr-only">
        {announcement}
      </p>

      <SectionStepper
        sections={profileFlow.sections}
        current={current}
        onNavigate={navigate}
      />

      <section aria-labelledby="onboarding-section-heading" className="grid gap-5">
        <div className="border-border flex flex-wrap items-end justify-between gap-x-4 gap-y-1 border-b pb-3">
          <div className="grid min-w-0 gap-1">
            <h3
              ref={headingRef}
              id="onboarding-section-heading"
              tabIndex={-1}
              className="text-base font-semibold outline-none"
            >
              {sectionLabel}
            </h3>
            {section?.description ? (
              <p className="text-muted-foreground text-sm">{section.description}</p>
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs">
            {ONBOARDING_COPY.setup.stepOf(index + 1, SECTION_ORDER.length)} ·{" "}
            {ONBOARDING_COPY.setup.completedSections(completedLabels)}
          </p>
        </div>

        {current === "review" ? (
          <>
            <p className="text-muted-foreground max-w-measure text-sm">
              {ONBOARDING_COPY.setup.afterSubmit}
            </p>
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
          </>
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
              <CredentialsSection page={sectionView} onDirty={() => setTouched(true)} />
            ) : null}
          </SectionForm>
        )}
      </section>

      <UnsavedChangesDialog
        open={guard.pendingUrl !== null}
        onStay={guard.stay}
        onLeave={guard.leave}
      />
    </div>
  );
}
