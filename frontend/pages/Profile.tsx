import { Head, router, usePage } from "@inertiajs/react";
import { CheckCircle2, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  FormActionBar,
  FormErrorSummary,
  PageHeader,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { ProfileAdministrativePanel } from "@/components/profile/ProfileAdministrativePanel";
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
 * editable field below posts as one Inertia visit so a validation failure
 * anywhere leaves the whole set intact and re-rendered with what was typed.
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

  // Guard the browser's own navigation away from unsaved edits.
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

  // A 422 Inertia response re-renders with errors; move focus to the summary.
  useEffect(() => {
    if (hasErrors) {
      summaryRef.current?.focus();
    }
  }, [hasErrors]);

  const sectionProps = { initial, validation, onDirty: () => setDirty(true) };

  return (
    <div className="grid gap-8">
      <Head title="Your profile" />
      <PageHeader
        title="Your profile"
        description="Keep your contact details, credentials, and public introduction current. Everything here is yours alone — no one else can read or change it from this page."
        meta={
          <>
            <span className="border-chip-primary-edge bg-chip-primary text-primary inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums">
              {completeness.percent}% complete
              <span className="text-primary/60 font-medium">
                {" "}
                · {completeness.completed} of {completeness.total}
              </span>
            </span>
            <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium">
              <Lock className="size-3.5" aria-hidden />
              Visible only to you and your brokerage
            </span>
          </>
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-x-8">
        <form
          id="profile-form"
          method="post"
          action={routes.profile_submit()}
          className="order-2 grid content-start gap-6 lg:order-1"
          // Delegated: every uncontrolled text input in the sections below
          // reports through here, so no field has to thread a callback.
          onInput={() => setDirty(true)}
          onSubmit={(event) => {
            event.preventDefault();
            if (submitting) {
              return;
            }
            setSubmitting(true);
            const form = event.currentTarget;
            // FormData so Django request.POST receives the fields (JSON bodies
            // do not). Use the typed route rather than form.action, which the
            // browser expands to an absolute URL.
            router.post(routes.profile_submit(), new FormData(form), {
              preserveScroll: true,
              onSuccess: () => setDirty(false),
              onFinish: () => setSubmitting(false),
            });
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

          <FormActionBar
            status={
              submitting ? (
                "Saving your changes…"
              ) : dirty ? (
                <span className="flex items-center gap-2">
                  <span className="bg-warning relative flex size-2 rounded-full">
                    <span className="bg-warning absolute inline-flex h-full w-full animate-ping rounded-full opacity-60" />
                  </span>
                  You have unsaved changes.
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <CheckCircle2 className="text-success size-4" aria-hidden />
                  All changes saved.
                </span>
              )
            }
          >
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : "Save changes"}
            </Button>
          </FormActionBar>
        </form>

        <aside className="order-1 grid content-start gap-6 lg:order-2">
          <div id={SECTION_ANCHORS.photo} className="scroll-mt-24">
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
          <ProfileAdministrativePanel administrative={identity.administrative} />
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
