import { Head, usePage } from "@inertiajs/react";
import { useEffect, useRef, useState } from "react";

import {
  FormErrorSummary,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { ProfileCompletenessPanel } from "@/components/profile/ProfileCompletenessPanel";
import {
  ProfileAddressSection,
  ProfileBiographySection,
  ProfileContactSection,
  ProfileCredentialsSection,
  ProfileLinksSection,
  SECTION_ANCHORS,
} from "@/components/profile/ProfileFormSections";
import { ProfileIdentityPanel } from "@/components/profile/ProfileIdentityPanel";
import { ProfilePhotoPanel } from "@/components/profile/ProfilePhotoPanel";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type { ProfilePageProps } from "@/types";

/** Django field name → the wording used in the error summary. */
const ERROR_LABELS: Record<string, string> = {
  first_name: "First name",
  last_name: "Last name",
  preferred_name: "Preferred name",
  phone_number: "Phone number",
  preferred_contact_method: "Preferred contact method",
  street_address: "Street address",
  city: "City",
  state: "State",
  zip_code: "ZIP code",
  office: "Office location",
  mls_number: "MLS number",
  nrds_number: "NRDS number",
  license_number: "License number",
  license_state: "License state",
  license_expires_on: "License expiration",
  bio: "Professional bio",
  languages: "Languages",
  website_url: "Website",
  linkedin_url: "LinkedIn",
  facebook_url: "Facebook",
  instagram_url: "Instagram",
  x_url: "X",
};

/**
 * The self-service agent profile.
 *
 * Two halves with different save semantics, and the page says which is which:
 * the photo panel writes straight through to its own endpoint, while every
 * editable field below posts as one form so a validation failure anywhere
 * leaves the whole set intact and re-rendered with what was typed.
 */
export default function Profile() {
  const {
    csrfToken,
    initial,
    validation,
    offices,
    states,
    languageOptions,
    contactMethods,
    socialPlatforms,
    identity,
    editable,
    completeness,
    limits,
    shell,
  } = usePage<ProfilePageProps>().props;

  const [dirty, setDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasErrors = hasValidationErrors(validation);

  // Guard the browser's own navigation. Inertia link navigation away from this
  // page is a full document request too, so this covers both.
  useEffect(() => {
    if (!dirty) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // A 422 re-render arrives as a fresh document, so move focus to the summary
  // rather than leaving it at the top of an apparently unchanged page.
  useEffect(() => {
    if (hasErrors) {
      summaryRef.current?.focus();
    }
  }, [hasErrors]);

  const sectionProps = { initial, validation, onDirty: () => setDirty(true) };

  return (
    <div className="grid gap-6">
      <Head title="Your profile" />
      <PageHeader
        title="Your profile"
        description="Keep your contact details, credentials, and public introduction current. Everything here is yours alone — no one else can read or change it from this page."
        meta={
          <span className="tabular-nums">
            {completeness.percent}% complete · {completeness.completed} of{" "}
            {completeness.total} details
          </span>
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-8">
        <form
          id="profile-form"
          method="post"
          action={routes.profile_submit()}
          className="order-2 grid gap-6 lg:order-1"
          // Delegated: every uncontrolled text input in the sections below
          // reports through here, so no field has to thread a callback.
          onInput={() => setDirty(true)}
          onSubmit={() => {
            setDirty(false);
            setSubmitting(true);
          }}
        >
          <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />

          <div ref={summaryRef} tabIndex={-1} className="outline-none">
            <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
          </div>

          <ProfileContactSection {...sectionProps} contactMethods={contactMethods} />
          <ProfileAddressSection {...sectionProps} states={states} />
          <ProfileCredentialsSection
            {...sectionProps}
            states={states}
            offices={offices}
            officeEditable={editable.office}
            office={identity.office}
            licenseStatus={identity.licenseStatus}
          />
          <ProfileBiographySection
            {...sectionProps}
            languageOptions={languageOptions}
            maxLanguages={limits.maxLanguages}
            bioMaxLength={limits.bioMaxLength}
          />
          <ProfileLinksSection {...sectionProps} socialPlatforms={socialPlatforms} />

          <SurfaceCard>
            <SurfaceCardContent className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-muted-foreground text-sm" aria-live="polite">
                {submitting
                  ? "Saving your changes…"
                  : dirty
                    ? "You have unsaved changes."
                    : "All changes saved."}
              </p>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Saving…" : "Save changes"}
              </Button>
            </SurfaceCardContent>
          </SurfaceCard>
        </form>

        <aside className="order-1 grid gap-6 lg:order-2">
          <div id={SECTION_ANCHORS.photo}>
            <ProfilePhotoPanel
              headshotUrl={initial.headshotUrl}
              displayName={identity.preferredDisplayName || identity.displayName}
              csrfToken={csrfToken}
              limits={limits}
            />
          </div>
          <ProfileCompletenessPanel
            completeness={completeness}
            sectionAnchors={SECTION_ANCHORS}
          />
          <ProfileIdentityPanel identity={identity} helpUrl={shell.help.url} />
        </aside>
      </div>
    </div>
  );
}

Profile.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Your profile",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Your profile", href: routes.profile() },
        ],
      },
      variant: "standard",
    },
  ] as const;
