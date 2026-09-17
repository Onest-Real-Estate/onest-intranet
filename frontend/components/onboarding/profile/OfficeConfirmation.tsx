import { Building2 } from "lucide-react";

import { Callout, FormFieldError } from "@/components/design-system";
import { OfficeDetails } from "@/components/onboarding/OfficeDetails";
import { Checkbox } from "@/components/ui/checkbox";
import { ONBOARDING_COPY } from "@/lib/onboarding/copy";
import { cn } from "@/lib/utils";
import type { OnboardingOfficeSelection } from "@/types";

export const OFFICE_CONFIRMATION_FIELD = "confirm_office";

export function OfficeConfirmation({
  selection,
  confirmed,
  onConfirmedChange,
  error,
}: {
  selection: OnboardingOfficeSelection;
  confirmed: boolean;
  onConfirmedChange: (value: boolean) => void;
  error?: string;
}) {
  const { office, administrator, support } = selection;

  return (
    <section aria-labelledby="office-confirmation-heading" className="grid gap-4">
      <div className="grid gap-1">
        <h3
          id="office-confirmation-heading"
          className="flex items-center gap-2 text-sm font-semibold"
        >
          <Building2 className="text-muted-foreground size-4" aria-hidden />
          {office.name}
        </h3>
        <p className="text-muted-foreground text-xs">{office.hierarchy}</p>
      </div>

      <OfficeDetails selection={selection} showName={false} />

      {administrator ? null : (
        <Callout tone="warning" title={ONBOARDING_COPY.office.administratorUnavailable}>
          {support.message}
        </Callout>
      )}

      <Callout tone="info" title="What this choice controls">
        Your office determines local resources, administrator ownership, required tools,
        and contract routing. This is your office address; it never changes the home or
        mailing address you entered earlier.
      </Callout>

      <div className="grid gap-2">
        <div
          id={OFFICE_CONFIRMATION_FIELD}
          className={cn(
            "flex items-start gap-3 rounded-lg border p-4",
            error ? "border-destructive/60" : "border-border",
          )}
        >
          <input
            type="hidden"
            name={OFFICE_CONFIRMATION_FIELD}
            value={confirmed ? "true" : "false"}
          />
          <input type="hidden" name="confirmed_office_id" value={office.id} />
          <Checkbox
            id="confirm_office_input"
            checked={confirmed}
            onCheckedChange={(value) => onConfirmedChange(value === true)}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={error ? "confirm_office_error" : undefined}
            className="mt-0.5"
          />
          <label
            htmlFor="confirm_office_input"
            className="grid cursor-pointer gap-1 text-sm"
          >
            <span className="font-medium">
              I confirm this is the office I will work from.
            </span>
            <span className="text-muted-foreground">
              Changing the office selection requires a new confirmation.
            </span>
          </label>
        </div>
        <FormFieldError id="confirm_office_error" message={error} />
      </div>
    </section>
  );
}
