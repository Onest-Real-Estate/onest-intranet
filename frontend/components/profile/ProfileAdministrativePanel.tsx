import { BadgeCheck, Lock } from "lucide-react";

import {
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import type { ProfileAdministrativeSummary } from "@/types";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
}

/**
 * The broker's half of the record, shown to the person it describes.
 *
 * Everything here arrives already decided: an agent can read their status,
 * their start date, and whether the brokerage has verified their license, but
 * there is no control to change any of it and `profile_submit` rejects the
 * field names outright. Operational notes are not in the payload at all —
 * withholding them is the server's job, not this component's.
 */
export function ProfileAdministrativePanel({
  administrative,
}: {
  administrative: ProfileAdministrativeSummary;
}) {
  const { agentStatus, licenseVerification, contractStatus } = administrative;
  return (
    <SurfaceCard state="read-only">
      <PanelHeader
        title="Brokerage record"
        description="Maintained by your office administrator."
        meta={
          <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <Lock className="size-3.5" aria-hidden />
            Read-only
          </span>
        }
      />
      <SurfaceCardContent className="grid gap-4">
        <dl className="grid gap-4">
          <ReadOnlyValue label="Agent status">
            <StatusBadge
              status={{ label: agentStatus.label, tone: agentStatus.tone }}
            />
          </ReadOnlyValue>
          <ReadOnlyValue label="Start date">
            {formatDate(administrative.startDate)}
          </ReadOnlyValue>
          <ReadOnlyValue label="Agent ID">
            {administrative.agentIdentifier || "—"}
          </ReadOnlyValue>
          <ReadOnlyValue label="License verification">
            <StatusBadge
              status={{
                label: licenseVerification.label,
                tone: licenseVerification.tone,
                icon: licenseVerification.state === "verified" ? BadgeCheck : undefined,
              }}
            />
            {licenseVerification.verifiedAt ? (
              <p className="text-muted-foreground mt-1 text-xs">
                Checked {formatDate(licenseVerification.verifiedAt)}
              </p>
            ) : null}
          </ReadOnlyValue>
          <ReadOnlyValue label="Contract status">
            <StatusBadge
              status={{ label: contractStatus.label, tone: contractStatus.tone }}
            />
            <p className="text-muted-foreground mt-1 text-xs">
              {contractStatus.available
                ? "Comes from your agent contract record."
                : contractStatus.reason}
            </p>
          </ReadOnlyValue>
        </dl>
        <p className="text-muted-foreground border-t pt-4 text-sm">
          Editing your license number or its expiry date here returns this record to
          “not verified” until the brokerage checks it again.
        </p>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
