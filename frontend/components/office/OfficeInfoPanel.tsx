import { Check, Copy, Mail, MapPin, Phone } from "lucide-react";
import { useState, type ReactNode } from "react";

import {
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import type { OfficeContactPerson, OfficeInfoPayload } from "@/types";

const DAY_ORDER = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

const DAY_LABELS: Record<string, string> = {
  monday: "Monday",
  tuesday: "Tuesday",
  wednesday: "Wednesday",
  thursday: "Thursday",
  friday: "Friday",
  saturday: "Saturday",
  sunday: "Sunday",
};

const FIELD_LABEL = "text-muted-foreground text-xs font-medium tracking-wide uppercase";

const CONTACT_LINK =
  "text-primary inline-flex min-w-0 items-center gap-1.5 text-sm underline-offset-2 hover:underline";

function telHref(phoneNumber: string): string {
  return `tel:${phoneNumber.replace(/[^+\d]/g, "")}`;
}

function ContactBlock({
  title,
  person,
  empty,
}: {
  title: string;
  person: OfficeContactPerson | null;
  empty: string;
}) {
  return (
    <div className="grid min-w-0 content-start gap-1">
      <p className={FIELD_LABEL}>{title}</p>
      {!person ? (
        <p className="text-muted-foreground text-sm">{empty}</p>
      ) : (
        <>
          <p className="text-foreground text-sm font-medium">{person.displayName}</p>
          <a
            className={CONTACT_LINK}
            href={`mailto:${person.email}`}
            title={person.email}
          >
            <Mail className="size-3.5 shrink-0" aria-hidden />
            <span className="break-all underline">{person.email}</span>
          </a>
          {person.phoneNumber ? (
            <a
              className={CONTACT_LINK}
              href={telHref(person.phoneNumber)}
              title={person.phoneNumber}
            >
              <Phone className="size-3.5 shrink-0" aria-hidden />
              <span className="tabular-nums">{person.phoneNumber}</span>
            </a>
          ) : null}
        </>
      )}
    </div>
  );
}

interface ParsedHours {
  lines: string[];
  structured: boolean;
}

function parseHours(hours: unknown[]): ParsedHours {
  const entries = hours
    .map((entry) => {
      if (!entry || typeof entry !== "object") return null;
      const record = entry as Record<string, unknown>;
      const day = typeof record.day === "string" ? record.day.toLowerCase() : null;
      if (!day) return null;
      const open = typeof record.open === "string" ? record.open : null;
      const close = typeof record.close === "string" ? record.close : null;
      return { day, open, close };
    })
    .filter((entry) => entry !== null);
  if (!entries.length) {
    return {
      lines: hours.filter((entry): entry is string => typeof entry === "string"),
      structured: false,
    };
  }
  const byDay = new Map(entries.map((entry) => [entry.day, entry]));
  const lines = DAY_ORDER.map((day) => {
    const entry = byDay.get(day);
    if (!entry?.open || !entry.close) {
      return `${DAY_LABELS[day]}: Closed`;
    }
    return `${DAY_LABELS[day]}: ${entry.open}–${entry.close}`;
  });
  return { lines, structured: true };
}

function ContactLinkRow({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className={CONTACT_LINK} href={href}>
      {children}
    </a>
  );
}

function addressLines(info: OfficeInfoPayload): string {
  const parts = [
    info.streetAddress,
    [info.city, info.state, info.zipCode].filter(Boolean).join(", "),
  ].filter(Boolean);
  return parts.join("\n");
}

function CopyAddressButton({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  const singleLine = address.replaceAll("\n", ", ");
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => {
        navigator.clipboard
          .writeText(singleLine)
          .then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          })
          .catch(() => {});
      }}
      aria-label={copied ? "Address copied" : "Copy address"}
    >
      {copied ? (
        <Check className="size-3.5" aria-hidden />
      ) : (
        <Copy className="size-3.5" aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

/**
 * Shared agent-facing office brochure used by Office Info and admin preview.
 */
export function OfficeInfoPanel({
  info,
  preview = false,
}: {
  info: OfficeInfoPayload;
  preview?: boolean;
}) {
  const { lines: hourLines, structured } = parseHours(info.officeHours ?? []);
  const address = addressLines(info);
  const showAccess =
    Boolean(info.accessInstructions) &&
    (info.includeInternal || !info.accessInstructionsInternal);

  return (
    <div className="grid gap-6">
      {preview ? (
        <p className="text-muted-foreground text-sm">
          Preview of what agents assigned to this office see.
        </p>
      ) : null}
      <SurfaceCard>
        <PanelHeader
          divided
          title={info.name}
          description={info.pathLabel}
          meta={
            <StatusBadge
              status={{
                label: info.isActive ? "Active" : "Inactive",
                tone: info.isActive ? "success" : "neutral",
              }}
            />
          }
        />
        <SurfaceCardContent className="grid gap-6">
          <div className="grid min-w-0 gap-4 sm:grid-cols-2">
            <div className="grid min-w-0 content-start gap-1">
              <p className={FIELD_LABEL}>Address</p>
              {address ? (
                <>
                  <p className="text-foreground whitespace-pre-line text-sm">
                    {address}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <CopyAddressButton address={address} />
                    {info.directionsUrl ? (
                      <Button type="button" variant="outline" size="sm" asChild>
                        <a
                          href={info.directionsUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <MapPin className="size-3.5" aria-hidden />
                          Directions
                        </a>
                      </Button>
                    ) : null}
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">Not listed yet.</p>
              )}
            </div>
            <div className="grid min-w-0 content-start gap-2">
              <p className={FIELD_LABEL}>Contact</p>
              {info.mainPhone ? (
                <ContactLinkRow href={telHref(info.mainPhone)}>
                  <Phone className="size-3.5 shrink-0" aria-hidden />
                  <span className="tabular-nums">{info.mainPhone}</span>
                </ContactLinkRow>
              ) : null}
              {info.publicEmail ? (
                <ContactLinkRow href={`mailto:${info.publicEmail}`}>
                  <Mail className="size-3.5 shrink-0" aria-hidden />
                  <span className="break-all underline">{info.publicEmail}</span>
                </ContactLinkRow>
              ) : null}
              {info.includeInternal && info.internalEmail ? (
                <ContactLinkRow href={`mailto:${info.internalEmail}`}>
                  <Mail className="size-3.5 shrink-0" aria-hidden />
                  <span className="break-all underline">{info.internalEmail}</span>
                  <span className="text-muted-foreground">(internal)</span>
                </ContactLinkRow>
              ) : null}
              {!info.mainPhone && !info.publicEmail ? (
                <p className="text-muted-foreground text-sm">Not listed yet.</p>
              ) : null}
            </div>
          </div>

          <div className="grid min-w-0 gap-1">
            <p className={FIELD_LABEL}>Hours</p>
            {hourLines.length ? (
              <>
                <ul className="text-foreground grid gap-1 text-sm">
                  {hourLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {structured ? (
                  <p className="text-muted-foreground text-xs">
                    Times shown in Eastern Time.
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Hours not listed.</p>
            )}
          </div>

          {info.parkingInstructions ? (
            <div className="grid min-w-0 gap-1">
              <p className={FIELD_LABEL}>Parking</p>
              <p className="text-foreground whitespace-pre-line text-sm">
                {info.parkingInstructions}
              </p>
            </div>
          ) : null}

          {showAccess ? (
            <div className="grid min-w-0 gap-1">
              <p className={FIELD_LABEL}>
                Access{info.accessInstructionsInternal ? " (internal)" : ""}
              </p>
              <p className="text-foreground whitespace-pre-line text-sm">
                {info.accessInstructions}
              </p>
            </div>
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      <SurfaceCard>
        <PanelHeader
          divided
          title="Contacts"
          description="Current branch support contacts"
        />
        <SurfaceCardContent className="grid gap-x-6 gap-y-6 sm:grid-cols-2">
          <ContactBlock
            title="Branch manager"
            person={info.contacts.branchManager}
            empty="No branch manager assigned."
          />
          <ContactBlock
            title="Branch admin"
            person={info.contacts.branchAdmin}
            empty="No branch admin assigned."
          />
          <ContactBlock
            title="Transaction coordinator"
            person={info.contacts.transactionCoordinator}
            empty="No transaction coordinator assigned."
          />
          <ContactBlock
            title="IT support"
            person={info.contacts.itSupport}
            empty="No IT support contact assigned."
          />
          <div className="grid min-w-0 gap-3 sm:col-span-2">
            <p className={FIELD_LABEL}>Brokers</p>
            {info.contacts.brokers.length ? (
              <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                {info.contacts.brokers.map((broker) => (
                  <ContactBlock
                    key={broker.id}
                    title={broker.isPrimary ? "Primary broker" : "Broker"}
                    person={broker}
                    empty=""
                  />
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">No broker contacts.</p>
            )}
          </div>
        </SurfaceCardContent>
      </SurfaceCard>

      {info.corporateContacts.length ? (
        <SurfaceCard>
          <PanelHeader
            divided
            title="Companywide support"
            description="Leadership and corporate directory for every office"
          />
          <SurfaceCardContent className="grid gap-x-6 gap-y-6 sm:grid-cols-2">
            {info.corporateContacts.map((person) => (
              <ContactBlock
                key={`${person.assignmentType}-${person.id}`}
                title={person.assignmentTypeLabel}
                person={person}
                empty=""
              />
            ))}
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}
