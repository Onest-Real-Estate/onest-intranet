import { ChevronDown, Globe, Link2, Search } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Callout,
  DateField,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
} from "@/components/design-system";
import {
  OwnerBadge,
  policyFor,
  ReadOnlyField,
} from "@/components/onboarding/profile/field-ownership";
import {
  OFFICE_CONFIRMATION_FIELD,
  OfficeConfirmation,
} from "@/components/onboarding/profile/OfficeConfirmation";
import { loadOfficePreview } from "@/components/onboarding/profile/office-preview-transport";
import { LanguagePicker } from "@/components/profile/ProfileFormSections";
import { SelectField, TextField } from "@/components/profile/profile-fields";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { firstFieldError } from "@/lib/validation";
import type { OnboardingPageProps } from "@/types";

const INTRODUCTION_ID = "credentials-introduction";

export function CredentialsSection({
  page,
  onDirty,
}: {
  page: OnboardingPageProps;
  onDirty: () => void;
}) {
  const {
    initial,
    validation,
    profileFlow,
    offices,
    officeLabel,
    officeSelection,
    officeConfirmed,
    states,
    languageOptions,
    socialPlatforms,
    limits,
  } = page;
  const field = (name: string) => policyFor(profileFlow.fields, name);
  const officePolicy = field("office");
  const values = initial as unknown as Record<string, string>;

  const introductionFields = [
    "bio",
    "languages",
    "website_url",
    ...socialPlatforms.map((platform) => platform.name),
  ];
  const introductionHasErrors = introductionFields.some((name) =>
    Boolean(firstFieldError(validation, name)),
  );
  const introductionHasValues =
    Boolean(initial.bio || initial.websiteUrl || initial.languages.length) ||
    socialPlatforms.some((platform) => Boolean(values[platform.prop]));

  const [officeId, setOfficeId] = useState(initial.officeId);
  const [officePreview, setOfficePreview] = useState(officeSelection);
  const [officeLoading, setOfficeLoading] = useState(false);
  const [officeLoadError, setOfficeLoadError] = useState("");
  const [officeIsConfirmed, setOfficeIsConfirmed] = useState(officeConfirmed);
  const [officeSearch, setOfficeSearch] = useState("");
  const [licenseState, setLicenseState] = useState(initial.licenseState);
  const [languages, setLanguages] = useState<string[]>(initial.languages);
  const [bioLength, setBioLength] = useState(initial.bio.length);
  const [introductionOpen, setIntroductionOpen] = useState(
    introductionHasValues || introductionHasErrors,
  );

  // A server error inside the collapsed region has to be visible to be fixed.
  useEffect(() => {
    if (introductionHasErrors) {
      setIntroductionOpen(true);
    }
  }, [introductionHasErrors]);

  useEffect(() => {
    if (!officeId) {
      setOfficePreview(null);
      return;
    }
    if (officeSelection?.office.id === Number(officeId)) {
      setOfficePreview(officeSelection);
      setOfficeLoading(false);
      setOfficeLoadError("");
      return;
    }
    const controller = new AbortController();
    setOfficeLoading(true);
    setOfficeLoadError("");
    loadOfficePreview(
      routes.onboarding_office_preview(Number(officeId)),
      controller.signal,
    )
      .then(setOfficePreview)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setOfficePreview(null);
          setOfficeLoadError(
            error instanceof Error
              ? error.message
              : "We could not load that office right now.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setOfficeLoading(false);
        }
      });
    return () => controller.abort();
  }, [officeId, officeSelection]);

  const officeCount = offices.reduce((count, group) => count + group.offices.length, 0);
  const officeQuery = officeSearch.trim().toLocaleLowerCase();
  const filteredOffices = officeQuery
    ? offices
        .map((group) => ({
          ...group,
          offices: group.offices.filter((office) =>
            [office.name, office.city, office.state, office.region, group.label]
              .filter(Boolean)
              .some((value) => value?.toLocaleLowerCase().includes(officeQuery)),
          ),
        }))
        .filter((group) => group.offices.length > 0)
    : offices;
  const officeConfirmationError = firstFieldError(
    validation,
    OFFICE_CONFIRMATION_FIELD,
  );

  return (
    <div className="grid gap-6">
      {officeCount > 6 && !officePolicy.readOnly ? (
        <FormField>
          <FormLabel htmlFor="office_search">Find an office</FormLabel>
          <div className="relative">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
              aria-hidden
            />
            <Input
              id="office_search"
              type="search"
              value={officeSearch}
              onChange={(event) => setOfficeSearch(event.target.value)}
              onInput={(event) => event.stopPropagation()}
              placeholder="Search office, city, state, or region"
              className="pl-9"
            />
          </div>
        </FormField>
      ) : null}
      {officePolicy.readOnly ? (
        <dl>
          <ReadOnlyField
            label={officePolicy.label}
            value={officeLabel}
            owner={officePolicy.owner}
            description="Your office is managed by an administrator."
          />
        </dl>
      ) : (
        <SelectField
          name="office"
          label={officePolicy.label}
          value={officeId}
          onChange={(next) => {
            setOfficeId(next);
            setOfficeIsConfirmed(false);
            setOfficePreview(null);
            onDirty();
          }}
          placeholder="Select your office"
          groups={filteredOffices}
          validation={validation}
          required={officePolicy.required}
          description={
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <OwnerBadge owner={officePolicy.owner} />
              {officePolicy.guidance}
            </span>
          }
        />
      )}

      {officeLoading ? (
        <div
          role="status"
          aria-label="Loading office details"
          className="grid gap-3 rounded-lg border p-4"
        >
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : null}
      {officeLoadError ? (
        <Callout tone="destructive" title="Office details unavailable">
          {officeLoadError}
        </Callout>
      ) : null}
      {officePreview && !officeLoading ? (
        <OfficeConfirmation
          selection={officePreview}
          confirmed={officeIsConfirmed}
          onConfirmedChange={(value) => {
            setOfficeIsConfirmed(value);
            onDirty();
          }}
          error={officeConfirmationError}
        />
      ) : null}

      <Separator />

      <section aria-labelledby="credentials-license-heading" className="grid gap-4">
        <div className="grid gap-1">
          <h3 id="credentials-license-heading" className="text-sm font-semibold">
            License and memberships
          </h3>
          <p className="text-muted-foreground max-w-measure text-sm">
            Add only the numbers you actually have. Anything still pending can stay
            blank; your office can fill it in later.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            name="license_number"
            label={field("license_number").label}
            validation={validation}
            defaultValue={initial.licenseNumber}
            autoCapitalize="characters"
            required={field("license_number").required}
            optional={!field("license_number").required}
          />
          <SelectField
            name="license_state"
            label={field("license_state").label}
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
            required={field("license_state").required}
            optional={!field("license_state").required}
          />
          <DateField
            name="license_expires_on"
            label={field("license_expires_on").label}
            validation={validation}
            defaultValue={initial.licenseExpiresOn}
            required={field("license_expires_on").required}
            optional={!field("license_expires_on").required}
            onChange={onDirty}
          />
        </div>
        {field("license_number").guidance ? (
          <FormDescription className="-mt-2">
            {field("license_number").guidance}
          </FormDescription>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            name="mls_number"
            label={field("mls_number").label}
            validation={validation}
            defaultValue={initial.mlsNumber}
            required={field("mls_number").required}
            optional={!field("mls_number").required}
            description={field("mls_number").guidance || undefined}
          />
          <TextField
            name="nrds_number"
            label={field("nrds_number").label}
            validation={validation}
            defaultValue={initial.nrdsNumber}
            inputMode="numeric"
            required={field("nrds_number").required}
            optional={!field("nrds_number").required}
            description={field("nrds_number").guidance || undefined}
          />
        </div>
      </section>

      <Separator />

      <section className="grid gap-3">
        <h3 className="m-0">
          <button
            type="button"
            aria-expanded={introductionOpen}
            aria-controls={INTRODUCTION_ID}
            onClick={() => setIntroductionOpen((open) => !open)}
            className="hover:bg-muted/40 focus-visible:ring-ring/50 flex w-full items-center justify-between gap-3 rounded-md border px-4 py-3 text-left outline-none transition-colors duration-(--motion-fast) focus-visible:ring-3"
          >
            <span className="grid gap-0.5">
              <span className="text-sm font-semibold">Public introduction</span>
              <span className="text-muted-foreground text-xs font-normal">
                Optional · bio, languages, website, and social links
              </span>
            </span>
            <ChevronDown
              className={cn(
                "text-muted-foreground size-4 shrink-0 transition-transform duration-(--motion-fast)",
                introductionOpen && "rotate-180",
              )}
              aria-hidden
            />
          </button>
        </h3>
        {/* Hidden, not unmounted: collapsed values still post with the section. */}
        <div
          id={INTRODUCTION_ID}
          hidden={!introductionOpen}
          className="grid gap-5 pt-1"
        >
          <FormField>
            <FormLabel htmlFor="bio" optional>
              {field("bio").label}
            </FormLabel>
            <Textarea
              id="bio"
              name="bio"
              rows={4}
              maxLength={limits.bioMaxLength}
              defaultValue={initial.bio}
              onChange={(event) => setBioLength(event.target.value.length)}
              {...fieldA11yProps("bio", validation, "bio_description")}
            />
            <FormDescription id="bio_description">
              <span aria-live="polite">
                {bioLength} of {limits.bioMaxLength} characters. A few sentences about
                who you help and where.
              </span>
            </FormDescription>
            <FormFieldError
              id="bio_error"
              message={firstFieldError(validation, "bio")}
            />
          </FormField>

          <LanguagePicker
            options={languageOptions}
            selected={languages}
            max={limits.maxLanguages}
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

          <TextField
            name="website_url"
            label={field("website_url").label}
            type="url"
            inputMode="url"
            validation={validation}
            defaultValue={initial.websiteUrl}
            placeholder="https://example.com"
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
                inputMode="url"
                validation={validation}
                defaultValue={values[platform.prop] ?? ""}
                placeholder={platform.placeholder}
                optional
                leading={<Link2 />}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
