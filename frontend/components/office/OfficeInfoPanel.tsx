import {
  Car,
  Check,
  Clock,
  Copy,
  KeyRound,
  type LucideIcon,
  Mail,
  MapPin,
  Phone,
} from "lucide-react";
import { type ReactNode, useState } from "react";

import {
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { IconWell, type IconWellTone } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "?"
  );
}

/**
 * One person, as a card.
 *
 * These used to be label-and-value blocks in a two-column grid — a page of
 * support contacts that read as a form. A person is the most concrete thing on
 * this page and the thing an agent is actually here to find, so each gets an
 * object of their own: a mark, their name, the role they hold, and the two
 * ways to reach them as real controls rather than as wrapped URLs.
 */
function ContactCard({
  title,
  person,
  empty,
}: {
  title: string;
  person: OfficeContactPerson | null;
  empty: string;
}) {
  if (!person) {
    if (!empty) {
      return null;
    }
    return (
      <div className="border-border/70 grid min-w-0 content-start gap-1 rounded-lg border border-dashed p-4">
        <p className={FIELD_LABEL}>{title}</p>
        <p className="text-muted-foreground text-sm">{empty}</p>
      </div>
    );
  }

  return (
    <div className="bg-card border-border/70 hover:border-border-strong flex min-w-0 items-start gap-3 rounded-lg border p-4 transition-colors duration-(--motion-fast)">
      <span
        aria-hidden
        className="brand-surface grid size-9 shrink-0 place-items-center rounded-md text-xs font-semibold"
      >
        {initials(person.displayName)}
      </span>
      <div className="grid min-w-0 flex-1 gap-1.5">
        <div className="min-w-0">
          <p className="text-foreground truncate text-sm font-semibold">
            {person.displayName}
          </p>
          <p className={FIELD_LABEL}>{title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button asChild variant="outline" size="sm" className="h-7 px-2 text-xs">
            <a href={`mailto:${person.email}`} title={person.email}>
              <Mail className="size-3.5" aria-hidden />
              Email
            </a>
          </Button>
          {person.phoneNumber ? (
            <Button asChild variant="outline" size="sm" className="h-7 px-2 text-xs">
              <a href={telHref(person.phoneNumber)} title={person.phoneNumber}>
                <Phone className="size-3.5" aria-hidden />
                <span className="tabular-nums">{person.phoneNumber}</span>
              </a>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface HourRow {
  /** Lower-case weekday key, or "" for a free-text line the office typed. */
  day: string;
  label: string;
  value: string;
}

interface ParsedHours {
  rows: HourRow[];
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
      rows: hours
        .filter((entry): entry is string => typeof entry === "string")
        .map((line) => ({ day: "", label: line, value: "" })),
      structured: false,
    };
  }
  const byDay = new Map(entries.map((entry) => [entry.day, entry]));
  const rows = DAY_ORDER.map((day) => {
    const entry = byDay.get(day);
    return {
      day,
      label: DAY_LABELS[day] ?? day,
      value: entry?.open && entry.close ? `${entry.open}–${entry.close}` : "Closed",
    };
  });
  return { rows, structured: true };
}

/**
 * Today's key, so the week reads as "am I able to walk in right now" rather
 * than as seven equally-weighted lines a reader has to find themselves in.
 */
function todayKey(): string {
  return DAY_ORDER[(new Date().getDay() + 6) % 7] ?? "";
}

/**
 * One fact about the office, as an object rather than a label-and-value pair.
 *
 * The tone is not decoration: it separates *where* from *how to reach* from
 * *when*, which is the first cut an agent makes when they open this page. The
 * mark repeats that in a second, non-colour channel.
 */
function FactCard({
  icon,
  tone = "muted",
  title,
  className,
  children,
}: {
  icon: LucideIcon;
  tone?: IconWellTone;
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "border-border/70 bg-card grid min-w-0 content-start gap-2.5 rounded-lg border p-4",
        className,
      )}
    >
      <div className="flex items-center gap-2.5">
        <IconWell icon={icon} tone={tone} className="size-8" iconClassName="size-4" />
        <h3 className={FIELD_LABEL}>{title}</h3>
      </div>
      {children}
    </section>
  );
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
  const { rows: hourRows, structured } = parseHours(info.officeHours ?? []);
  const today = structured ? todayKey() : "";
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
        <SurfaceCardContent className="grid gap-3 @2xl:grid-cols-2">
          <FactCard icon={MapPin} tone="info" title="Address">
            {address ? (
              <>
                <p className="text-foreground whitespace-pre-line text-sm leading-6">
                  {address}
                </p>
                <div className="flex flex-wrap items-center gap-2">
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
          </FactCard>

          <FactCard icon={Phone} tone="success" title="Contact">
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
          </FactCard>

          <FactCard
            icon={Clock}
            tone="warning"
            title="Hours"
            className="@2xl:col-span-2"
          >
            {hourRows.length ? (
              <>
                {structured ? (
                  // A week of equal lines makes a reader find themselves in it.
                  // Today is the row they came for.
                  <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                    {hourRows.map((row) => {
                      const isToday = row.day === today;
                      return (
                        <div
                          key={row.day}
                          className={cn(
                            "flex items-baseline justify-between gap-4 rounded-sm",
                            isToday
                              ? "text-foreground font-semibold"
                              : "text-muted-foreground",
                          )}
                        >
                          <dt className="min-w-0 truncate">
                            {row.label}
                            {isToday ? (
                              <span className="text-primary ml-1.5 text-xs font-semibold">
                                Today
                              </span>
                            ) : null}
                          </dt>
                          <dd className="shrink-0 tabular-nums">{row.value}</dd>
                        </div>
                      );
                    })}
                  </dl>
                ) : (
                  <ul className="text-foreground grid gap-1 text-sm">
                    {hourRows.map((row) => (
                      <li key={row.label}>{row.label}</li>
                    ))}
                  </ul>
                )}
                {structured ? (
                  <p className="text-muted-foreground text-xs">
                    Times shown in Eastern Time.
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Hours not listed.</p>
            )}
          </FactCard>

          {info.parkingInstructions ? (
            <FactCard icon={Car} tone="neutral" title="Parking">
              <p className="text-foreground whitespace-pre-line text-sm leading-6">
                {info.parkingInstructions}
              </p>
            </FactCard>
          ) : null}

          {showAccess ? (
            <FactCard
              icon={KeyRound}
              tone={info.accessInstructionsInternal ? "warning" : "neutral"}
              title={`Access${info.accessInstructionsInternal ? " (internal)" : ""}`}
            >
              <p className="text-foreground whitespace-pre-line text-sm leading-6">
                {info.accessInstructions}
              </p>
            </FactCard>
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      <SurfaceCard>
        <PanelHeader
          divided
          title="Contacts"
          description="Current branch support contacts"
        />
        <SurfaceCardContent className="grid gap-3 @2xl:grid-cols-2">
          <ContactCard
            title="Branch manager"
            person={info.contacts.branchManager}
            empty="No branch manager assigned."
          />
          <ContactCard
            title="Branch admin"
            person={info.contacts.branchAdmin}
            empty="No branch admin assigned."
          />
          <ContactCard
            title="Transaction coordinator"
            person={info.contacts.transactionCoordinator}
            empty="No transaction coordinator assigned."
          />
          <ContactCard
            title="IT support"
            person={info.contacts.itSupport}
            empty="No IT support contact assigned."
          />
          {info.contacts.brokers.length ? (
            info.contacts.brokers.map((broker) => (
              <ContactCard
                key={broker.id}
                title={broker.isPrimary ? "Primary broker" : "Broker"}
                person={broker}
                empty=""
              />
            ))
          ) : (
            <p className="text-muted-foreground text-sm @2xl:col-span-2">
              No broker contacts.
            </p>
          )}
        </SurfaceCardContent>
      </SurfaceCard>

      {info.corporateContacts.length ? (
        <SurfaceCard>
          <PanelHeader
            divided
            title="Companywide support"
            description="Leadership and corporate directory for every office"
          />
          <SurfaceCardContent className="grid gap-3 @2xl:grid-cols-2">
            {info.corporateContacts.map((person) => (
              <ContactCard
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
