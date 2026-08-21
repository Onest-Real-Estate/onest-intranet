import { Globe, Link2 } from "lucide-react";
import { useId, useState } from "react";

import {
  DateField,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import {
  descriptionId,
  SelectField,
  TextField,
} from "@/components/profile/profile-fields";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { firstFieldError } from "@/lib/validation";
import type {
  ContactMethodOption,
  LanguageOption,
  OfficeGroup,
  ProfileLicenseStatus,
  ProfileOffice,
  SelfProfileValues,
  SocialPlatformOption,
  StateOption,
} from "@/types";
import type { ValidationErrors } from "@/types/design-system";

export const SECTION_ANCHORS: Record<string, string> = {
  photo: "profile-photo",
  contact: "profile-contact",
  address: "profile-address",
  credentials: "profile-credentials",
  biography: "profile-biography",
  links: "profile-links",
};

interface SectionProps {
  initial: SelfProfileValues;
  validation: ValidationErrors;
  /** Called whenever a control changes, to arm the unsaved-changes guard. */
  onDirty: () => void;
}

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <SurfaceCard id={id} className="scroll-mt-24">
      <PanelHeader title={title} description={description} />
      <SurfaceCardContent className="grid gap-4">{children}</SurfaceCardContent>
    </SurfaceCard>
  );
}

// ---------------------------------------------------------------------------
// Contact
// ---------------------------------------------------------------------------

export function ProfileContactSection({
  initial,
  validation,
  onDirty,
  contactMethods,
}: SectionProps & { contactMethods: ContactMethodOption[] }) {
  const [contactMethod, setContactMethod] = useState(initial.preferredContactMethod);

  return (
    <Section
      id={SECTION_ANCHORS.contact}
      title="Contact details"
      description="How colleagues and clients reach you."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          name="first_name"
          label="First name"
          validation={validation}
          defaultValue={initial.firstName}
          autoComplete="given-name"
          required
        />
        <TextField
          name="last_name"
          label="Last name"
          validation={validation}
          defaultValue={initial.lastName}
          autoComplete="family-name"
          required
        />
      </div>
      <TextField
        name="preferred_name"
        label="Preferred name"
        validation={validation}
        defaultValue={initial.preferredName}
        autoComplete="nickname"
        optional
        description="Used in greetings and directory listings when it differs from your legal first name."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          name="phone_number"
          label="Phone number"
          type="tel"
          validation={validation}
          defaultValue={initial.phoneNumber}
          autoComplete="tel"
          placeholder="(202) 555-0100"
          required
        />
        <SelectField
          name="preferred_contact_method"
          label="Preferred contact method"
          value={contactMethod}
          onChange={(next) => {
            setContactMethod(next);
            onDirty();
          }}
          placeholder="No preference"
          options={contactMethods.map((method) => ({
            value: method.value,
            label: method.label,
          }))}
          validation={validation}
          optional
        />
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Address
// ---------------------------------------------------------------------------

export function ProfileAddressSection({
  initial,
  validation,
  onDirty,
  states,
}: SectionProps & { states: StateOption[] }) {
  const [state, setState] = useState(initial.state);

  return (
    <Section
      id={SECTION_ANCHORS.address}
      title="Mailing address"
      description="Where paperwork and physical mail should reach you."
    >
      <TextField
        name="street_address"
        label="Street address"
        validation={validation}
        defaultValue={initial.streetAddress}
        autoComplete="street-address"
        required
      />
      <div className="grid gap-4 sm:grid-cols-6">
        <TextField
          className="sm:col-span-3"
          name="city"
          label="City"
          validation={validation}
          defaultValue={initial.city}
          autoComplete="address-level2"
          required
        />
        <div className="sm:col-span-2">
          <SelectField
            name="state"
            label="State"
            value={state}
            onChange={(next) => {
              setState(next);
              onDirty();
            }}
            placeholder="Select a state"
            options={states.map((option) => ({
              value: option.code,
              label: option.name,
            }))}
            validation={validation}
            required
          />
        </div>
        <TextField
          className="sm:col-span-1"
          name="zip_code"
          label="ZIP"
          validation={validation}
          defaultValue={initial.zipCode}
          autoComplete="postal-code"
          placeholder="12345"
          required
        />
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Office and credentials
// ---------------------------------------------------------------------------

function licenseStatusPresentation(status: ProfileLicenseStatus) {
  if (status.state === "expired") {
    return { label: `Expired ${Math.abs(status.days)} days ago`, tone: status.tone };
  }
  if (status.state === "expiring") {
    return { label: `Expires in ${status.days} days`, tone: status.tone };
  }
  return { label: "Current", tone: status.tone };
}

export function ProfileCredentialsSection({
  initial,
  validation,
  onDirty,
  states,
  offices,
  officeEditable,
  office,
  licenseStatus,
}: SectionProps & {
  states: StateOption[];
  offices: OfficeGroup[];
  officeEditable: boolean;
  office: ProfileOffice | null;
  licenseStatus: ProfileLicenseStatus | null;
}) {
  const [officeId, setOfficeId] = useState(initial.officeId);
  const [licenseState, setLicenseState] = useState(initial.licenseState);

  return (
    <Section
      id={SECTION_ANCHORS.credentials}
      title="Office and credentials"
      description="Your work location and the license and membership numbers tied to it."
    >
      {officeEditable ? (
        <SelectField
          name="office"
          label="Office location"
          value={officeId}
          onChange={(next) => {
            setOfficeId(next);
            onDirty();
          }}
          placeholder="Select your office"
          groups={offices}
          validation={validation}
          required
        />
      ) : (
        <FormField>
          <FormLabel htmlFor="office_readonly">Office location</FormLabel>
          <p
            id="office_readonly"
            className="bg-muted/40 rounded-md border px-3 py-2 text-sm"
          >
            {office ? office.pathLabel : "Not assigned"}
          </p>
          <FormDescription>
            Your office scopes what you can see across the hub, so an administrator has
            to move it. Everything else on this page is yours to edit.
          </FormDescription>
        </FormField>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          name="mls_number"
          label="MLS number"
          validation={validation}
          defaultValue={initial.mlsNumber}
          optional
        />
        <TextField
          name="nrds_number"
          label="NRDS number"
          validation={validation}
          defaultValue={initial.nrdsNumber}
          inputMode="numeric"
          optional
          description="8 or 9 digits."
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          name="license_number"
          label="License number"
          validation={validation}
          defaultValue={initial.licenseNumber}
          optional
        />
        <SelectField
          name="license_state"
          label="License state"
          value={licenseState}
          onChange={(next) => {
            setLicenseState(next);
            onDirty();
          }}
          placeholder="Select a state"
          options={states.map((option) => ({
            value: option.code,
            label: option.name,
          }))}
          validation={validation}
          optional
        />
        <DateField
          name="license_expires_on"
          label="License expiration"
          validation={validation}
          defaultValue={initial.licenseExpiresOn}
          optional
          onChange={onDirty}
        />
      </div>

      {licenseStatus ? (
        <p className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">License on file:</span>
          <StatusBadge status={licenseStatusPresentation(licenseStatus)} />
        </p>
      ) : null}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Biography and languages
// ---------------------------------------------------------------------------

function LanguagePicker({
  options,
  selected,
  max,
  onToggle,
  validation,
}: {
  options: LanguageOption[];
  selected: string[];
  max: number;
  onToggle: (code: string, next: boolean) => void;
  validation: ValidationErrors;
}) {
  const groupId = useId();
  const atLimit = selected.length >= max;
  const error = firstFieldError(validation, "languages");

  return (
    <fieldset
      className="grid gap-2"
      aria-describedby={`${groupId}-help${error ? " languages_error" : ""}`}
      aria-invalid={Boolean(error) || undefined}
    >
      <legend className="text-sm leading-none font-medium">
        Languages you work in
      </legend>
      <FormDescription id={`${groupId}-help`}>
        Choose up to {max}. {selected.length} selected.
      </FormDescription>
      {/* Hidden inputs carry the selection: the styled checkbox is a button. */}
      {selected.map((code) => (
        <input key={code} type="hidden" name="languages" value={code} />
      ))}
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const checked = selected.includes(option.code);
          const id = `${groupId}-${option.code}`;
          return (
            <div
              key={option.code}
              className={cn(
                "-m-px flex items-center gap-2 rounded-full border py-1.5 pr-4 pl-3 transition-colors duration-(--motion-fast)",
                checked
                  ? "border-primary/40 bg-primary/10"
                  : "border-border hover:border-primary/30 hover:bg-muted/50",
              )}
            >
              <Checkbox
                id={id}
                checked={checked}
                disabled={!checked && atLimit}
                onCheckedChange={(next) => onToggle(option.code, next === true)}
              />
              <label
                htmlFor={id}
                className="cursor-pointer text-sm leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-60"
              >
                {option.name}
              </label>
            </div>
          );
        })}
      </div>
      <FormFieldError id="languages_error" message={error} />
    </fieldset>
  );
}

export function ProfileBiographySection({
  initial,
  validation,
  onDirty,
  languageOptions,
  maxLanguages,
  bioMaxLength,
}: SectionProps & {
  languageOptions: LanguageOption[];
  maxLanguages: number;
  bioMaxLength: number;
}) {
  const [bioLength, setBioLength] = useState(initial.bio.length);
  const [languages, setLanguages] = useState<string[]>(initial.languages);
  const bioHelp = descriptionId("bio");
  const bioNearLimit = bioLength >= bioMaxLength * 0.9;

  return (
    <Section
      id={SECTION_ANCHORS.biography}
      title="Biography and languages"
      description="A short introduction shown wherever your name appears in the hub."
    >
      <FormField>
        <FormLabel htmlFor="bio" optional>
          Professional bio
        </FormLabel>
        <Textarea
          id="bio"
          name="bio"
          rows={6}
          maxLength={bioMaxLength}
          defaultValue={initial.bio}
          onChange={(event) => {
            setBioLength(event.target.value.length);
            onDirty();
          }}
          {...fieldA11yProps("bio", validation, bioHelp)}
        />
        <div
          className={cn(
            "mt-1.5 h-1 w-full overflow-hidden rounded-full transition-colors duration-(--motion-fast)",
            bioNearLimit ? "bg-warning/25" : "bg-muted",
          )}
          role="presentation"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-(--motion-slow) ease-out",
              bioNearLimit ? "bg-warning" : "bg-primary/50",
            )}
            style={{ width: `${Math.min(100, (bioLength / bioMaxLength) * 100)}%` }}
          />
        </div>
        <FormDescription id={bioHelp}>
          <span
            aria-live="polite"
            className={bioNearLimit ? "text-warning-ink font-medium" : undefined}
          >
            {bioLength} of {bioMaxLength} characters used.
          </span>
        </FormDescription>
        <FormFieldError id="bio_error" message={firstFieldError(validation, "bio")} />
      </FormField>

      <LanguagePicker
        options={languageOptions}
        selected={languages}
        max={maxLanguages}
        validation={validation}
        onToggle={(code, next) => {
          setLanguages((current) =>
            next
              ? current.includes(code)
                ? current
                : [...current, code]
              : current.filter((item) => item !== code),
          );
          onDirty();
        }}
      />
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Links
// ---------------------------------------------------------------------------

export function ProfileLinksSection({
  initial,
  validation,
  socialPlatforms,
}: SectionProps & { socialPlatforms: SocialPlatformOption[] }) {
  const values = initial as unknown as Record<string, string>;

  return (
    <Section
      id={SECTION_ANCHORS.links}
      title="Website and social links"
      description="Public profiles clients can look you up on. Each link is checked against its own site."
    >
      <TextField
        name="website_url"
        label="Website"
        type="url"
        validation={validation}
        defaultValue={initial.websiteUrl}
        placeholder="https://example.com"
        inputMode="url"
        optional
        leading={<Globe />}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        {socialPlatforms.map((platform) => (
          <TextField
            key={platform.name}
            name={platform.name}
            label={platform.label}
            type="url"
            validation={validation}
            defaultValue={values[platform.prop] ?? ""}
            placeholder={platform.placeholder}
            inputMode="url"
            optional
            leading={<Link2 />}
          />
        ))}
      </div>
    </Section>
  );
}
