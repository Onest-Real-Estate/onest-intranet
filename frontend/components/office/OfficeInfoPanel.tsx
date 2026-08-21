import { Mail, Phone, UserRound } from "lucide-react";

import {
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import type { OfficeContactPerson, OfficeInfoPayload } from "@/types";

function ContactBlock({
  title,
  person,
  empty,
}: {
  title: string;
  person: OfficeContactPerson | null;
  empty: string;
}) {
  if (!person) {
    return (
      <div className="grid gap-1">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {title}
        </p>
        <p className="text-muted-foreground text-sm">{empty}</p>
      </div>
    );
  }
  return (
    <div className="grid gap-1">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {title}
      </p>
      <p className="text-foreground text-sm font-medium">{person.displayName}</p>
      <a
        className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
        href={`mailto:${person.email}`}
      >
        <Mail className="size-3.5" aria-hidden />
        {person.email}
      </a>
      {person.phoneNumber ? (
        <a
          className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
          href={`tel:${person.phoneNumber}`}
        >
          <Phone className="size-3.5" aria-hidden />
          {person.phoneNumber}
        </a>
      ) : null}
    </div>
  );
}

function formatHours(hours: unknown[]): string[] {
  if (!hours.length) return [];
  return hours.map((entry) => {
    if (typeof entry === "string") return entry;
    if (entry && typeof entry === "object") {
      try {
        return JSON.stringify(entry);
      } catch {
        return String(entry);
      }
    }
    return String(entry);
  });
}

function addressLines(info: OfficeInfoPayload): string {
  const parts = [
    info.streetAddress,
    [info.city, info.state, info.zipCode].filter(Boolean).join(", "),
  ].filter(Boolean);
  return parts.join("\n");
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
  const hours = formatHours(info.officeHours ?? []);
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
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Address
              </p>
              {address ? (
                <p className="text-foreground whitespace-pre-line text-sm">{address}</p>
              ) : (
                <p className="text-muted-foreground text-sm">Not listed yet.</p>
              )}
            </div>
            <div className="grid gap-2">
              {info.mainPhone ? (
                <a
                  className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
                  href={`tel:${info.mainPhone}`}
                >
                  <Phone className="size-3.5" aria-hidden />
                  {info.mainPhone}
                </a>
              ) : null}
              {info.publicEmail ? (
                <a
                  className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
                  href={`mailto:${info.publicEmail}`}
                >
                  <Mail className="size-3.5" aria-hidden />
                  {info.publicEmail}
                </a>
              ) : null}
              {info.includeInternal && info.internalEmail ? (
                <a
                  className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
                  href={`mailto:${info.internalEmail}`}
                >
                  <Mail className="size-3.5" aria-hidden />
                  {info.internalEmail}{" "}
                  <span className="text-muted-foreground">(internal)</span>
                </a>
              ) : null}
            </div>
          </div>

          <div className="grid gap-1">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Hours
            </p>
            {hours.length ? (
              <ul className="text-foreground grid gap-1 text-sm">
                {hours.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">Hours not listed.</p>
            )}
          </div>

          {info.parkingInstructions ? (
            <div className="grid gap-1">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Parking
              </p>
              <p className="text-foreground whitespace-pre-line text-sm">
                {info.parkingInstructions}
              </p>
            </div>
          ) : null}

          {showAccess ? (
            <div className="grid gap-1">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Access
                {info.accessInstructionsInternal ? " (internal)" : ""}
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
          title="Contacts"
          description="Current branch support contacts"
          meta={<UserRound className="text-muted-foreground size-4" aria-hidden />}
        />
        <SurfaceCardContent className="grid gap-6 sm:grid-cols-2">
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
          <div className="grid gap-3 sm:col-span-2">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Brokers
            </p>
            {info.contacts.brokers.length ? (
              <div className="grid gap-4 sm:grid-cols-2">
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
    </div>
  );
}
