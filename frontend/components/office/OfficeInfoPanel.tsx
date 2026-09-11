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
 * One fact, as a ruled row rather than a card.
 *
 * These were bordered tiles in a grid — white boxes on a white panel, each
 * with its own outline and a differently tinted icon. Six of them float six
 * ways and invite the eye to compare their edges instead of reading their
 * contents. A hairline puts every fact on one baseline and makes the panel a
 * single object, which is what the surrounding system already does with
 * tables and metric strips.
 *
 * The rules run the full width of the panel on purpose: an inset rule draws a
 * box without admitting it.
 */
function FactRow({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5 px-5 py-4 @lg:grid-cols-[10.5rem_minmax(0,1fr)] @lg:gap-6">
      <dt className="text-muted-foreground flex items-center gap-2 self-start text-xs font-semibold tracking-[0.02em] uppercase @lg:pt-0.5">
        {/* Muted, not tinted. The tile's own contract says a tone that is not
            encoding something a reader could act on is decoration — and
            "address is blue, hours are amber" encodes nothing. */}
        <Icon className="size-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
        {label}
      </dt>
      <dd className="grid min-w-0 content-start gap-2.5">{children}</dd>
    </div>
  );
}

function NotListed({ children = "Not listed yet." }: { children?: ReactNode }) {
  return <p className="text-muted-foreground text-sm">{children}</p>;
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
 * One person, as a ruled row.
 *
 * A grid of bordered contact tiles is a wall of same-sized boxes: six people
 * rendered as six outlines, where the only thing that varies is the text
 * inside. Ruled rows put every name on one left edge, so the column scans as a
 * directory — and the actions land on a common right edge instead of wrapping
 * differently inside each tile.
 */
function ContactRow({
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
      <li className="grid gap-0.5 px-5 py-3.5">
        <p className="text-muted-foreground text-xs font-semibold tracking-[0.02em] uppercase">
          {title}
        </p>
        <p className="text-muted-foreground text-sm">{empty}</p>
      </li>
    );
  }

  return (
    <li className="hover:bg-accent/40 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3.5 transition-colors duration-(--motion-fast)">
      <span
        aria-hidden
        className="bg-muted text-muted-foreground grid size-9 shrink-0 place-items-center rounded-md text-xs font-semibold"
      >
        {initials(person.displayName)}
      </span>
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="text-foreground truncate text-sm font-semibold">
          {person.displayName}
        </p>
        <p className="text-muted-foreground truncate text-xs">{title}</p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
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
    </li>
  );
}

/** A ruled directory: one object, hairlines between the people in it. */
function ContactList({ children }: { children: ReactNode }) {
  return <ul className="divide-border/70 divide-y">{children}</ul>;
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
        {/* `px-0` so the rules meet the panel's own edges; each row carries the
            inset instead. */}
        <SurfaceCardContent className="px-0">
          <dl className="divide-border/70 divide-y">
            <FactRow icon={MapPin} label="Address">
              {address ? (
                <>
                  <p className="text-foreground text-sm leading-6 whitespace-pre-line">
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
                <NotListed />
              )}
            </FactRow>

            <FactRow icon={Phone} label="Contact">
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
              {!info.mainPhone && !info.publicEmail ? <NotListed /> : null}
            </FactRow>

            <FactRow icon={Clock} label="Hours">
              {hourRows.length ? (
                <>
                  {structured ? (
                    // A week of equal lines makes a reader find themselves in
                    // it. Today is the row they came for.
                    <dl className="grid max-w-[21rem] gap-y-0.5 text-sm">
                      {hourRows.map((row) => {
                        const isToday = row.day === today;
                        return (
                          <div
                            key={row.day}
                            className={cn(
                              // The leader is what makes seven times read as a
                              // column of figures rather than seven sentences.
                              "border-border/60 flex items-baseline justify-between gap-3 border-b border-dotted py-1 last:border-b-0",
                              isToday
                                ? "text-foreground font-semibold"
                                : "text-muted-foreground",
                            )}
                          >
                            <dt className="min-w-0 truncate">
                              {row.label}
                              {isToday ? (
                                // Not gold. The Spent Gold Rule keeps that for
                                // brand and action, and the two links in this
                                // panel are the page's only legitimate claims
                                // on it — the row is already carried by weight
                                // and full-contrast ink.
                                <span className="text-muted-foreground ml-1.5 text-micro font-semibold tracking-[0.02em] uppercase">
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
                <NotListed>Hours not listed.</NotListed>
              )}
            </FactRow>

            {info.parkingInstructions ? (
              <FactRow icon={Car} label="Parking">
                <p className="text-foreground max-w-measure text-sm leading-6 whitespace-pre-line">
                  {info.parkingInstructions}
                </p>
              </FactRow>
            ) : null}

            {showAccess ? (
              <FactRow
                icon={KeyRound}
                label={`Access${info.accessInstructionsInternal ? " · internal" : ""}`}
              >
                <p className="text-foreground max-w-measure text-sm leading-6 whitespace-pre-line">
                  {info.accessInstructions}
                </p>
              </FactRow>
            ) : null}
          </dl>
        </SurfaceCardContent>
      </SurfaceCard>

      <SurfaceCard>
        <PanelHeader
          divided
          title="Contacts"
          description="Current branch support contacts"
        />
        <SurfaceCardContent className="px-0">
          <ContactList>
            <ContactRow
              title="Branch manager"
              person={info.contacts.branchManager}
              empty="No branch manager assigned."
            />
            <ContactRow
              title="Branch admin"
              person={info.contacts.branchAdmin}
              empty="No branch admin assigned."
            />
            <ContactRow
              title="Transaction coordinator"
              person={info.contacts.transactionCoordinator}
              empty="No transaction coordinator assigned."
            />
            <ContactRow
              title="IT support"
              person={info.contacts.itSupport}
              empty="No IT support contact assigned."
            />
            {info.contacts.brokers.length ? (
              info.contacts.brokers.map((broker) => (
                <ContactRow
                  key={broker.id}
                  title={broker.isPrimary ? "Primary broker" : "Broker"}
                  person={broker}
                  empty=""
                />
              ))
            ) : (
              <li className="text-muted-foreground px-5 py-3.5 text-sm">
                No broker contacts.
              </li>
            )}
          </ContactList>
        </SurfaceCardContent>
      </SurfaceCard>

      {info.corporateContacts.length ? (
        <SurfaceCard>
          <PanelHeader
            divided
            title="Companywide support"
            description="Leadership and corporate directory for every office"
          />
          <SurfaceCardContent className="px-0">
            <ContactList>
              {info.corporateContacts.map((person) => (
                <ContactRow
                  key={`${person.assignmentType}-${person.id}`}
                  title={person.assignmentTypeLabel}
                  person={person}
                  empty=""
                />
              ))}
            </ContactList>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}
