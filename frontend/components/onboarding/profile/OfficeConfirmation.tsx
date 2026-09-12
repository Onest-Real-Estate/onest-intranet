import { Building2, Clock3, Mail, MapPin, Phone } from "lucide-react";

import { Callout, FormFieldError } from "@/components/design-system";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { OnboardingOfficeSelection } from "@/types";

export const OFFICE_CONFIRMATION_FIELD = "confirm_office";

function phoneHref(phone: string): string {
  return `tel:${phone.replace(/[^+\d]/g, "")}`;
}

function officeHoursLines(hours: unknown[]): string[] {
  return hours.flatMap((value) => {
    if (typeof value === "string") {
      return value.trim() ? [value.trim()] : [];
    }
    if (!value || typeof value !== "object") {
      return [];
    }
    const row = value as Record<string, unknown>;
    const day = String(row.day ?? row.label ?? "").trim();
    const period = String(row.hours ?? row.value ?? "").trim();
    return day || period ? [`${day}${day && period ? ": " : ""}${period}`] : [];
  });
}

const contactLink =
  "text-primary inline-flex min-w-0 items-center gap-1.5 text-sm hover:underline";

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
  const locality = [office.city, office.state].filter(Boolean).join(", ");
  const address = [office.streetAddress, locality, office.zipCode]
    .filter(Boolean)
    .join(" · ");
  const hours = officeHoursLines(office.officeHours);

  return (
    <section aria-labelledby="office-confirmation-heading" className="grid gap-4">
      <div className="bg-muted/30 overflow-hidden rounded-lg border">
        <div className="border-border grid gap-1 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Building2 className="text-muted-foreground size-4" aria-hidden />
            <h3 id="office-confirmation-heading" className="text-sm font-semibold">
              {office.name}
            </h3>
          </div>
          <p className="text-muted-foreground text-xs">{office.hierarchy}</p>
        </div>
        <dl className="divide-border grid divide-y bg-background">
          <div className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
            <dt className="text-muted-foreground flex items-center gap-2 text-xs font-semibold uppercase">
              <MapPin className="size-3.5" aria-hidden /> Office address
            </dt>
            <dd className="text-sm">{address || "Address not listed yet."}</dd>
          </div>
          {office.mainPhone || office.publicEmail ? (
            <div className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
              <dt className="text-muted-foreground text-xs font-semibold uppercase">
                Main contact
              </dt>
              <dd className="flex flex-wrap gap-x-4 gap-y-1">
                {office.mainPhone ? (
                  <a className={contactLink} href={phoneHref(office.mainPhone)}>
                    <Phone className="size-3.5" aria-hidden /> {office.mainPhone}
                  </a>
                ) : null}
                {office.publicEmail ? (
                  <a className={contactLink} href={`mailto:${office.publicEmail}`}>
                    <Mail className="size-3.5" aria-hidden /> {office.publicEmail}
                  </a>
                ) : null}
              </dd>
            </div>
          ) : null}
          {hours.length ? (
            <div className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
              <dt className="text-muted-foreground flex items-center gap-2 text-xs font-semibold uppercase">
                <Clock3 className="size-3.5" aria-hidden /> Office hours
              </dt>
              <dd className="grid gap-0.5 text-sm">
                {hours.map((line) => (
                  <span key={line}>{line}</span>
                ))}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>

      {administrator ? (
        <div className="grid gap-1.5 rounded-lg border px-4 py-3">
          <p className="text-muted-foreground text-xs font-semibold uppercase">
            {administrator.resolutionLabel}
          </p>
          <p className="text-sm font-semibold">{administrator.name}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {administrator.phone ? (
              <a
                className={contactLink}
                href={phoneHref(administrator.phone)}
                aria-label={`Call ${administrator.name}`}
              >
                <Phone className="size-3.5" aria-hidden /> {administrator.phone}
              </a>
            ) : null}
            <a
              className={contactLink}
              href={`mailto:${administrator.email}`}
              aria-label={`Email ${administrator.name}`}
            >
              <Mail className="size-3.5" aria-hidden /> {administrator.email}
            </a>
          </div>
        </div>
      ) : (
        <Callout tone="warning" title="Office administrator unavailable">
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
