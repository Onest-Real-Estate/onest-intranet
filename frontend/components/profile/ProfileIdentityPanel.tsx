import { Lock, ShieldCheck } from "lucide-react";

import {
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Badge } from "@/components/ui/badge";
import type { ProfileIdentity } from "@/types";

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
 * The account facts an agent cannot change themselves.
 *
 * Rendered as values rather than disabled inputs on purpose: a greyed-out text
 * box invites people to try typing in it and then says nothing about why it
 * refused. Each group instead states who owns the value and where to go for a
 * correction.
 */
export function ProfileIdentityPanel({
  identity,
  helpUrl,
}: {
  identity: ProfileIdentity;
  helpUrl: string | null;
}) {
  return (
    <SurfaceCard state="read-only">
      <PanelHeader
        title="Account details"
        description="Managed for you — ask an administrator if any of this is wrong."
        meta={
          <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <Lock className="size-3.5" aria-hidden />
            Read-only
          </span>
        }
      />
      <SurfaceCardContent className="grid gap-4">
        <dl className="grid gap-4">
          <ReadOnlyValue label="Work email">
            <span className="break-all">{identity.email}</span>
            <p className="text-muted-foreground mt-1 text-xs">
              Comes from Microsoft sign-in. Changing it is an IT request.
            </p>
          </ReadOnlyValue>
          <ReadOnlyValue label="Legal name on file">
            {identity.legalName || "—"}
          </ReadOnlyValue>
          <ReadOnlyValue label="Roles">
            {identity.roles.length > 0 ? (
              <span className="flex flex-wrap gap-1.5">
                {identity.roles.map((role) => (
                  <Badge key={role} variant="secondary" className="gap-1">
                    <ShieldCheck className="size-3" aria-hidden />
                    {role}
                  </Badge>
                ))}
              </span>
            ) : (
              "—"
            )}
          </ReadOnlyValue>
          <ReadOnlyValue label="Account status">
            <StatusBadge
              status={
                identity.accountStatus === "active"
                  ? { label: "Active", tone: "success" }
                  : { label: "Inactive", tone: "destructive" }
              }
            />
          </ReadOnlyValue>
          <ReadOnlyValue label="Member since">
            {formatDate(identity.memberSince)}
          </ReadOnlyValue>
          <ReadOnlyValue label="Onboarding completed">
            {formatDate(identity.onboardingCompletedAt)}
          </ReadOnlyValue>
        </dl>
        <p className="text-muted-foreground border-t pt-4 text-sm">
          Need one of these corrected?{" "}
          {helpUrl ? (
            <a
              className="text-primary underline underline-offset-2"
              href={helpUrl}
              rel="noreferrer noopener"
              target="_blank"
            >
              Open a support request
            </a>
          ) : (
            <span>Contact your office administrator.</span>
          )}
        </p>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
