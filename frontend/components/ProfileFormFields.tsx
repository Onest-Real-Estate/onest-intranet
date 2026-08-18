import { useState } from "react";

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

function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return <p className="text-sm text-destructive">{message}</p>;
}

/**
 * Shared fields for onboarding and profile edit. Posts as a plain HTML form
 * so Django/Inertia can validate server-side (HTTP 422 on errors).
 *
 * shadcn Select is not a native form control, so office/state values are
 * mirrored into hidden inputs that the POST actually submits.
 */
export function ProfileFormFields({
  initial,
  errors,
  offices,
  states,
}: {
  initial: ProfileFormValues;
  errors: Record<string, string>;
  offices: OfficeGroup[];
  states: StateOption[];
}) {
  const [state, setState] = useState(initial.state);
  const [officeId, setOfficeId] = useState(initial.officeId);

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
            required
          />
          <FieldError message={errors.first_name} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="last_name">Last name</Label>
          <Input
            id="last_name"
            name="last_name"
            defaultValue={initial.lastName}
            autoComplete="family-name"
            aria-invalid={Boolean(errors.last_name) || undefined}
            required
          />
          <FieldError message={errors.last_name} />
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
          required
        />
        <FieldError message={errors.phone_number} />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="street_address">Street address</Label>
        <Input
          id="street_address"
          name="street_address"
          defaultValue={initial.streetAddress}
          autoComplete="street-address"
          aria-invalid={Boolean(errors.street_address) || undefined}
          required
        />
        <FieldError message={errors.street_address} />
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
            required
          />
          <FieldError message={errors.city} />
        </div>
        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="state">State</Label>
          <input type="hidden" name="state" value={state} />
          <Select value={state || undefined} onValueChange={setState}>
            <SelectTrigger id="state" aria-invalid={Boolean(errors.state) || undefined}>
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
          <FieldError message={errors.state} />
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
            required
          />
          <FieldError message={errors.zip_code} />
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="office">Office location</Label>
        <input type="hidden" name="office" value={officeId} />
        <Select value={officeId || undefined} onValueChange={setOfficeId}>
          <SelectTrigger id="office" aria-invalid={Boolean(errors.office) || undefined}>
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
        <FieldError message={errors.office} />
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
          />
          <FieldError message={errors.mls_number} />
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
          />
          <FieldError message={errors.nrds_number} />
        </div>
      </div>
    </div>
  );
}
