import { Mail, Phone } from "lucide-react";
import type { ReactNode } from "react";

import type { OnboardingOfficeSelection } from "@/types";

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

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-muted-foreground text-xs font-semibold uppercase">{term}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

/**
 * Public facts for one office as a ruled definition list — hairlines, no card.
 * Only fields the office payload already treats as public reach this list.
 */
export function OfficeDetails({
  selection,
  showName = true,
}: {
  selection: OnboardingOfficeSelection;
  /** Off when the caller already names the office in its own heading. */
  showName?: boolean;
}) {
  const { office, administrator } = selection;
  const locality = [office.city, office.state].filter(Boolean).join(", ");
  const address = [office.streetAddress, locality, office.zipCode]
    .filter(Boolean)
    .join(" · ");
  const hours = officeHoursLines(office.officeHours);

  return (
    <dl className="divide-border border-border divide-y border-y">
      {showName ? (
        <Row term="Office">
          <span className="block font-medium">{office.name}</span>
          <span className="text-muted-foreground block text-xs">
            {office.hierarchy}
          </span>
        </Row>
      ) : null}
      <Row term="Office address">{address || "Address not listed yet."}</Row>
      {office.mainPhone || office.publicEmail ? (
        <Row term="Main contact">
          <span className="flex flex-wrap gap-x-4 gap-y-1">
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
          </span>
        </Row>
      ) : null}
      {hours.length ? (
        <Row term="Office hours">
          <span className="grid gap-0.5">
            {hours.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </span>
        </Row>
      ) : null}
      {administrator ? (
        <Row term={administrator.resolutionLabel}>
          <span className="block font-medium">{administrator.name}</span>
          <span className="flex flex-wrap gap-x-4 gap-y-1">
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
          </span>
        </Row>
      ) : null}
    </dl>
  );
}
