import { useState } from "react";

import { FormDescription, FormFieldError } from "@/components/design-system";
import { policyFor } from "@/components/onboarding/profile/field-ownership";
import { SelectField, TextField } from "@/components/profile/profile-fields";
import { Separator } from "@/components/ui/separator";
import { firstFieldError } from "@/lib/validation";
import type { OnboardingPageProps } from "@/types";

function ContactMethodChoice({
  page,
  value,
  onChange,
}: {
  page: OnboardingPageProps;
  value: string;
  onChange: (next: string) => void;
}) {
  const policy = policyFor(page.profileFlow.fields, "preferred_contact_method");
  const error = firstFieldError(page.validation, "preferred_contact_method");
  const options = [{ value: "", label: "No preference" }, ...page.contactMethods];

  return (
    <fieldset
      id="preferred_contact_method"
      aria-invalid={Boolean(error) || undefined}
      aria-describedby={error ? "preferred_contact_method_error" : undefined}
      className="grid gap-2"
    >
      <legend className="mb-2 flex w-full items-center gap-1 text-xs font-semibold tracking-[0.02em]">
        {policy.label}
        {policy.required ? null : (
          <span className="text-muted-foreground ml-auto font-normal">Optional</span>
        )}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <label
            key={option.value || "none"}
            className="has-checked:border-chip-primary-edge has-checked:bg-chip-primary has-focus-visible:ring-ring/50 hover:border-primary/30 flex min-h-9 cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors duration-(--motion-fast) has-focus-visible:ring-3"
          >
            <input
              type="radio"
              name="preferred_contact_method"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="accent-primary size-3.5 outline-none"
            />
            {option.label}
          </label>
        ))}
      </div>
      <FormFieldError id="preferred_contact_method_error" message={error} />
    </fieldset>
  );
}

export function ContactSection({
  page,
  onDirty,
}: {
  page: OnboardingPageProps;
  onDirty: () => void;
}) {
  const { initial, validation, profileFlow, states } = page;
  const field = (name: string) => policyFor(profileFlow.fields, name);
  const [contactMethod, setContactMethod] = useState(initial.preferredContactMethod);
  const [state, setState] = useState(initial.state);

  return (
    <div className="grid gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          name="phone_number"
          label={field("phone_number").label}
          type="tel"
          inputMode="tel"
          validation={validation}
          defaultValue={initial.phoneNumber}
          autoComplete="tel"
          placeholder="(202) 555-0100"
          required={field("phone_number").required}
          description="US numbers only. We format it for you."
        />
      </div>

      <ContactMethodChoice
        page={page}
        value={contactMethod}
        onChange={(next) => {
          setContactMethod(next);
          onDirty();
        }}
      />

      <Separator />

      <fieldset className="grid gap-4">
        <legend className="text-sm font-semibold">Home address</legend>
        <FormDescription className="-mt-2">
          Used for brokerage paperwork and mailings. It never appears in the agent
          directory.
        </FormDescription>
        <TextField
          name="street_address"
          label={field("street_address").label}
          validation={validation}
          defaultValue={initial.streetAddress}
          autoComplete="street-address"
          required={field("street_address").required}
        />
        <div className="grid gap-4 sm:grid-cols-6">
          <div className="sm:col-span-3">
            <TextField
              name="city"
              label={field("city").label}
              validation={validation}
              defaultValue={initial.city}
              autoComplete="address-level2"
              required={field("city").required}
            />
          </div>
          <SelectField
            className="sm:col-span-2"
            name="state"
            label={field("state").label}
            value={state}
            onChange={(next) => {
              setState(next);
              onDirty();
            }}
            placeholder="Select"
            options={states.map((option) => ({
              value: option.code,
              label: option.name,
            }))}
            validation={validation}
            required={field("state").required}
          />
          <div className="sm:col-span-1">
            <TextField
              name="zip_code"
              label="ZIP"
              validation={validation}
              defaultValue={initial.zipCode}
              autoComplete="postal-code"
              inputMode="numeric"
              placeholder="12345"
              required={field("zip_code").required}
            />
          </div>
        </div>
      </fieldset>
    </div>
  );
}
