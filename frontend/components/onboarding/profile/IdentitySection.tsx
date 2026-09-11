import { Callout } from "@/components/design-system";
import {
  policyFor,
  ReadOnlyField,
} from "@/components/onboarding/profile/field-ownership";
import { HeadshotField } from "@/components/onboarding/profile/HeadshotField";
import { TextField } from "@/components/profile/profile-fields";
import { firstFieldError } from "@/lib/validation";
import type { OnboardingPageProps } from "@/types";

export function IdentitySection({
  page,
  onPhotoChange,
}: {
  page: OnboardingPageProps;
  onPhotoChange: () => void;
}) {
  const { identity, initial, validation, profileFlow, csrfToken, limits } = page;
  const field = (name: string) => policyFor(profileFlow.fields, name);
  const legalName = [identity.legalName.firstName, identity.legalName.lastName]
    .filter(Boolean)
    .join(" ");
  const displayName =
    initial.preferredName || legalName || identity.email.split("@")[0] || "";

  return (
    <div className="grid gap-6">
      <section aria-labelledby="identity-account-heading" className="grid gap-3">
        <h3 id="identity-account-heading" className="text-sm font-semibold">
          From your Microsoft account
        </h3>
        <dl className="grid gap-4 sm:grid-cols-2">
          <ReadOnlyField
            label="Work email"
            value={identity.email}
            owner={identity.emailOwner}
            description="Change it in Microsoft 365; the hub follows the next time you sign in."
          />
          {identity.legalNameLocked ? (
            <ReadOnlyField
              label="Legal name"
              value={legalName}
              owner={field("first_name").owner}
              description="Ask IT to correct it in Microsoft if it is wrong."
            />
          ) : null}
        </dl>
        {identity.legalNameNotice ? (
          <Callout tone={identity.legalNameLocked ? "neutral" : "info"}>
            {identity.legalNameNotice}
          </Callout>
        ) : null}
      </section>

      {identity.legalNameLocked ? null : (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            name="first_name"
            label={field("first_name").label}
            validation={validation}
            defaultValue={initial.firstName}
            autoComplete="given-name"
            required={field("first_name").required}
          />
          <TextField
            name="last_name"
            label={field("last_name").label}
            validation={validation}
            defaultValue={initial.lastName}
            autoComplete="family-name"
            required={field("last_name").required}
          />
        </div>
      )}

      <TextField
        name="preferred_name"
        label={field("preferred_name").label}
        validation={validation}
        defaultValue={initial.preferredName}
        autoComplete="nickname"
        required={field("preferred_name").required}
        optional={!field("preferred_name").required}
        description={field("preferred_name").guidance || undefined}
      />

      <HeadshotField
        initialUrl={initial.headshotUrl}
        displayName={displayName}
        csrfToken={csrfToken}
        limits={limits}
        policy={field("headshot")}
        error={firstFieldError(validation, "headshot")}
        onPhotoChange={onPhotoChange}
      />
    </div>
  );
}
