import { useState } from "react";

import { FormFieldError, fieldA11yProps } from "@/components/design-system/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import type { ValidationErrors } from "@/types/design-system";

export interface ProfileFormValues {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  streetAddress: string;
  city: string;
  state: string;
  zipCode: string;
  officeId: string;
  mlsNumber: string;
  nrdsNumber: string;
}

export interface OfficeGroup {
  label: string;
  offices: { id: number; name: string }[];
}

export interface StateOption {
  code: string;
  name: string;
}

/**
 * Rendered with a stable id so the field can point at it through
 * `aria-describedby` — `aria-invalid` alone marks a field as wrong without
 * ever telling a screen reader what is wrong with it.
 */
/**
 * Shared fields for onboarding and profile edit. Posts as a plain HTML form
 * so Django/Inertia can validate server-side (HTTP 422 on errors).
 *
 * shadcn Select is not a native form control, so office/state values are
 * mirrored into hidden inputs that the POST actually submits.
 */
export function ProfileFormFields({
  initial,
  validation,
  offices,
  states,
}: {
  initial: ProfileFormValues;
  validation: ValidationErrors;
  offices: OfficeGroup[];
  states: StateOption[];
}) {
  const [state, setState] = useState(initial.state);
  const [officeId, setOfficeId] = useState(initial.officeId);
  const errors = Object.fromEntries(
    Object.entries(validation.fields).map(([field, messages]) => [field, messages[0]]),
  ) as Record<string, string | undefined>;

  function describedBy(field: string) {
    return fieldA11yProps(field, validation)["aria-describedby"];
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="first_name">First name</Label>
          <Input
            id="first_name"
            name="first_name"
            defaultValue={initial.firstName}
            autoComplete="given-name"
            aria-invalid={Boolean(errors.first_name) || undefined}
            aria-describedby={describedBy("first_name")}
            required
          />
          <FormFieldError id="first_name_error" message={errors.first_name} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="last_name">Last name</Label>
          <Input
            id="last_name"
            name="last_name"
            defaultValue={initial.lastName}
            autoComplete="family-name"
            aria-invalid={Boolean(errors.last_name) || undefined}
            aria-describedby={describedBy("last_name")}
            required
          />
          <FormFieldError id="last_name_error" message={errors.last_name} />
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="phone_number">Phone number</Label>
        <Input
          id="phone_number"
          name="phone_number"
          type="tel"
          defaultValue={initial.phoneNumber}
          autoComplete="tel"
          placeholder="(202) 555-0100"
          aria-invalid={Boolean(errors.phone_number) || undefined}
          aria-describedby={describedBy("phone_number")}
          required
        />
        <FormFieldError id="phone_number_error" message={errors.phone_number} />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="street_address">Street address</Label>
        <Input
          id="street_address"
          name="street_address"
          defaultValue={initial.streetAddress}
          autoComplete="street-address"
          aria-invalid={Boolean(errors.street_address) || undefined}
          aria-describedby={describedBy("street_address")}
          required
        />
        <FormFieldError id="street_address_error" message={errors.street_address} />
      </div>

      <div className="grid gap-4 sm:grid-cols-6">
        <div className="grid gap-2 sm:col-span-3">
          <Label htmlFor="city">City</Label>
          <Input
            id="city"
            name="city"
            defaultValue={initial.city}
            autoComplete="address-level2"
            aria-invalid={Boolean(errors.city) || undefined}
            aria-describedby={describedBy("city")}
            required
          />
          <FormFieldError id="city_error" message={errors.city} />
        </div>
        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="state">State</Label>
          <input type="hidden" name="state" value={state} />
          <Select value={state || undefined} onValueChange={setState}>
            <SelectTrigger
              id="state"
              aria-invalid={Boolean(errors.state) || undefined}
              aria-describedby={describedBy("state")}
            >
              <SelectValue placeholder="Select a state" />
            </SelectTrigger>
            <SelectContent>
              {states.map((option) => (
                <SelectItem key={option.code} value={option.code}>
                  {option.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormFieldError id="state_error" message={errors.state} />
        </div>
        <div className="grid gap-2 sm:col-span-1">
          <Label htmlFor="zip_code">ZIP</Label>
          <Input
            id="zip_code"
            name="zip_code"
            defaultValue={initial.zipCode}
            autoComplete="postal-code"
            placeholder="12345"
            aria-invalid={Boolean(errors.zip_code) || undefined}
            aria-describedby={describedBy("zip_code")}
            required
          />
          <FormFieldError id="zip_code_error" message={errors.zip_code} />
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="office">Office location</Label>
        <input type="hidden" name="office" value={officeId} />
        <Select value={officeId || undefined} onValueChange={setOfficeId}>
          <SelectTrigger
            id="office"
            aria-invalid={Boolean(errors.office) || undefined}
            aria-describedby={describedBy("office")}
          >
            <SelectValue placeholder="Select your office" />
          </SelectTrigger>
          <SelectContent>
            {offices.map((group) => (
              <SelectGroup key={group.label}>
                <SelectLabel>{group.label}</SelectLabel>
                {group.offices.map((office) => (
                  <SelectItem key={office.id} value={String(office.id)}>
                    {office.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        <FormFieldError id="office_error" message={errors.office} />
      </div>

      <Separator />

      <div className="grid gap-1">
        <p className="text-sm font-medium">Licenses</p>
        <p className="text-sm text-muted-foreground">
          MLS and NRDS numbers are optional. You can add them later from your profile.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="mls_number">MLS number</Label>
          <Input
            id="mls_number"
            name="mls_number"
            defaultValue={initial.mlsNumber}
            placeholder="Optional"
            aria-invalid={Boolean(errors.mls_number) || undefined}
            aria-describedby={describedBy("mls_number")}
          />
          <FormFieldError id="mls_number_error" message={errors.mls_number} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="nrds_number">NRDS number</Label>
          <Input
            id="nrds_number"
            name="nrds_number"
            defaultValue={initial.nrdsNumber}
            inputMode="numeric"
            placeholder="Optional"
            aria-invalid={Boolean(errors.nrds_number) || undefined}
            aria-describedby={describedBy("nrds_number")}
          />
          <FormFieldError id="nrds_number_error" message={errors.nrds_number} />
        </div>
      </div>
    </div>
  );
}
