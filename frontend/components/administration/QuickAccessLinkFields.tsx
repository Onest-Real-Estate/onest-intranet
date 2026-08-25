import { useState } from "react";

import {
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  NativeSelect,
} from "@/components/design-system";
import { Input } from "@/components/ui/input";
import { firstFieldError } from "@/lib/validation";
import type { QuickAccessChoice, QuickAccessOfficeChoice } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

/** Previously submitted values the create sheet repopulates after a 422. */
export interface QuickAccessLinkDraft {
  stableKey?: string;
  name?: string;
  description?: string;
  destinationType?: string;
  destinationValue?: string;
  icon?: string;
  sortOrder?: string;
  publishStartAt?: string;
  publishEndAt?: string;
  sso?: string;
  health?: string;
  setup?: string;
  isActive?: boolean;
  companyWide?: boolean;
  roles?: string[];
  offices?: number[];
}

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="text-muted-foreground col-span-full text-xs font-semibold tracking-[0.02em]">
      {children}
    </p>
  );
}

function CheckboxRow({
  id,
  name,
  label,
  defaultChecked,
  disabled,
  onChange,
}: {
  id: string;
  name: string;
  label: string;
  defaultChecked: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        id={id}
        name={name}
        defaultChecked={defaultChecked}
        disabled={disabled}
        onChange={onChange ? (event) => onChange(event.target.checked) : undefined}
        className="accent-primary size-4"
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

/**
 * The shared Quick Access link field set for the create slide-over.
 *
 * Everything here is an uncontrolled control that posts under its own name:
 * the sheet submits like a full page, so a failed create re-renders the list
 * with this draft restored server-side and no client state to reconcile.
 */
export function QuickAccessLinkFields({
  defaults,
  errors,
  iconOptions,
  internalDestinations,
  destinationTypeOptions,
  ssoOptions,
  healthOptions,
  setupOptions,
  roleOptions,
  officeOptions,
  capabilities,
}: {
  defaults: QuickAccessLinkDraft | undefined;
  errors: ValidationErrors;
  iconOptions: QuickAccessChoice[];
  internalDestinations: QuickAccessChoice[];
  destinationTypeOptions: QuickAccessChoice[];
  ssoOptions: QuickAccessChoice[];
  healthOptions: QuickAccessChoice[];
  setupOptions: QuickAccessChoice[];
  roleOptions: QuickAccessChoice[];
  officeOptions: QuickAccessOfficeChoice[];
  capabilities: { companyWide: boolean; scopeLevel: "brokerage" | "scoped" };
}) {
  // Local display state only — the checkbox itself still posts natively.
  const [companyWide, setCompanyWide] = useState(defaults?.companyWide ?? false);
  const isInternal = (defaults?.destinationType ?? "external_url") === "internal_route";

  return (
    <div className="grid gap-5">
      <SectionLabel>The tool</SectionLabel>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="name" required>
            Name
          </FormLabel>
          <Input
            id="name"
            name="name"
            defaultValue={defaults?.name ?? ""}
            required
            {...fieldA11yProps("name", errors)}
          />
          <FormFieldError message={firstFieldError(errors, "name")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="stable_key" required>
            Stable key
          </FormLabel>
          <Input
            id="stable_key"
            name="stable_key"
            defaultValue={defaults?.stableKey ?? ""}
            required
            {...fieldA11yProps("stable_key", errors)}
          />
          <FormDescription>
            Permanent identity used by audit records. It cannot be changed later.
          </FormDescription>
          <FormFieldError message={firstFieldError(errors, "stable_key")} />
        </FormField>

        <FormField className="sm:col-span-2">
          <FormLabel htmlFor="description" optional>
            Description
          </FormLabel>
          <Input
            id="description"
            name="description"
            defaultValue={defaults?.description ?? ""}
            {...fieldA11yProps("description", errors)}
          />
          <FormFieldError message={firstFieldError(errors, "description")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="icon" required>
            Icon
          </FormLabel>
          {/* Native selects so values post with the plain form submit; the
              server re-validates every choice either way. */}
          <NativeSelect
            id="icon"
            name="icon"
            defaultValue={defaults?.icon ?? "app-window"}
          >
            {iconOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError message={firstFieldError(errors, "icon")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="sort_order" optional>
            Position
          </FormLabel>
          <Input
            id="sort_order"
            name="sort_order"
            type="number"
            min={0}
            defaultValue={defaults?.sortOrder ?? "0"}
            {...fieldA11yProps("sort_order", errors)}
          />
          <FormDescription>Lower sorts first. Reorder from the list.</FormDescription>
          <FormFieldError message={firstFieldError(errors, "sort_order")} />
        </FormField>
      </div>

      <SectionLabel>Destination</SectionLabel>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="destination_type" required>
            Destination type
          </FormLabel>
          <NativeSelect
            id="destination_type"
            name="destination_type"
            defaultValue={defaults?.destinationType ?? "external_url"}
          >
            {destinationTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError message={firstFieldError(errors, "destination_type")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="destination_value" required>
            Destination
          </FormLabel>
          {isInternal ? (
            <NativeSelect
              id="destination_value"
              name="destination_value"
              defaultValue={defaults?.destinationValue ?? ""}
              required
            >
              <option value="" disabled>
                Choose a page
              </option>
              {internalDestinations.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <Input
              id="destination_value"
              name="destination_value"
              inputMode="url"
              placeholder="https://"
              defaultValue={defaults?.destinationValue ?? ""}
              required
              {...fieldA11yProps("destination_value", errors)}
            />
          )}
          <FormDescription>
            Never include a token, key, or password in a destination.
          </FormDescription>
          <FormFieldError message={firstFieldError(errors, "destination_value")} />
        </FormField>
      </div>

      <SectionLabel>Audience</SectionLabel>
      <div className="grid gap-4">
        <FormField>
          <CheckboxRow
            id="company_wide"
            name="company_wide"
            label="Publish company-wide"
            defaultChecked={defaults?.companyWide ?? false}
            disabled={!capabilities.companyWide}
            onChange={setCompanyWide}
          />
          <span className="text-muted-foreground text-xs" id="company_wide_help">
            {capabilities.companyWide
              ? "Ignores the office list and shows this to every office."
              : "Your role cannot publish brokerage-wide."}
          </span>
          <FormFieldError message={firstFieldError(errors, "company_wide")} />
        </FormField>

        <fieldset className="grid min-w-0 gap-2">
          <legend className="text-xs font-semibold tracking-[0.02em]">
            Role audience
          </legend>
          <span className="text-muted-foreground text-xs" id="roles_help">
            Leave every box clear to show this link to every role.
          </span>
          <div className="grid gap-2 sm:grid-cols-2">
            {roleOptions.map((option) => (
              <CheckboxRow
                key={option.value}
                id={`role_${option.value}`}
                name="roles"
                label={option.label}
                defaultChecked={(defaults?.roles ?? []).includes(option.value)}
              />
            ))}
          </div>
          <FormFieldError message={firstFieldError(errors, "roles")} />
        </fieldset>

        <fieldset className="grid min-w-0 gap-2">
          <legend className="text-xs font-semibold tracking-[0.02em]">
            Office audience
          </legend>
          <span className="text-muted-foreground text-xs" id="offices_help">
            Only offices inside your own scope are listed.
          </span>
          <div className="max-h-64 overflow-y-auto rounded-lg border p-3">
            <div className="grid gap-2">
              {officeOptions.map((option) => (
                <CheckboxRow
                  key={option.value}
                  id={`office_${option.value}`}
                  name="offices"
                  label={option.label}
                  defaultChecked={(defaults?.offices ?? []).includes(option.value)}
                  disabled={companyWide}
                />
              ))}
            </div>
          </div>
          <FormFieldError message={firstFieldError(errors, "offices")} />
        </fieldset>
      </div>

      <SectionLabel>Availability and integration</SectionLabel>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="publish_start_at" optional>
            Publish from
          </FormLabel>
          <Input
            id="publish_start_at"
            name="publish_start_at"
            type="datetime-local"
            defaultValue={defaults?.publishStartAt ?? ""}
            {...fieldA11yProps("publish_start_at", errors)}
          />
          <FormFieldError message={firstFieldError(errors, "publish_start_at")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="publish_end_at" optional>
            Publish until
          </FormLabel>
          <Input
            id="publish_end_at"
            name="publish_end_at"
            type="datetime-local"
            defaultValue={defaults?.publishEndAt ?? ""}
            {...fieldA11yProps("publish_end_at", errors)}
          />
          <FormFieldError message={firstFieldError(errors, "publish_end_at")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="sso_capability">Single sign-on</FormLabel>
          <NativeSelect
            id="sso_capability"
            name="sso_capability"
            defaultValue={defaults?.sso ?? "none"}
          >
            {ssoOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError message={firstFieldError(errors, "sso_capability")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="integration_health">Integration health</FormLabel>
          <NativeSelect
            id="integration_health"
            name="integration_health"
            defaultValue={defaults?.health ?? "unknown"}
          >
            {healthOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError message={firstFieldError(errors, "integration_health")} />
        </FormField>

        <FormField>
          <FormLabel htmlFor="setup_behavior">Setup behaviour</FormLabel>
          <NativeSelect
            id="setup_behavior"
            name="setup_behavior"
            defaultValue={defaults?.setup ?? "self_service"}
          >
            {setupOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <FormFieldError message={firstFieldError(errors, "setup_behavior")} />
        </FormField>

        <FormField>
          <div className="flex h-9 items-center">
            <CheckboxRow
              id="is_active"
              name="is_active"
              label="Active"
              defaultChecked={defaults?.isActive ?? true}
            />
          </div>
        </FormField>
      </div>
    </div>
  );
}
