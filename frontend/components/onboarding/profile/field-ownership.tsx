import { Building2, KeyRound, Lock } from "lucide-react";
import type { ReactNode } from "react";

import { FormDescription } from "@/components/design-system";
import { cn } from "@/lib/utils";
import type { OnboardingFieldPolicy, ProfileFieldOwner } from "@/types";

const OWNER_LABELS: Record<ProfileFieldOwner, string | null> = {
  microsoft: "Managed by Microsoft",
  brokerage: "Managed by oNEST",
  agent: null,
};

/**
 * Names who owns a value the agent cannot simply type over. Microsoft and the
 * brokerage get different marks and tones so the two are never confused, and
 * the words are always present so colour is not the only signal.
 */
export function OwnerBadge({
  owner,
  className,
}: {
  owner: ProfileFieldOwner;
  className?: string;
}) {
  const label = OWNER_LABELS[owner];
  if (!label) {
    return null;
  }
  const Icon = owner === "microsoft" ? KeyRound : Building2;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium",
        owner === "microsoft"
          ? "border-chip-info-edge bg-chip-info text-info"
          : "border-chip-neutral-edge bg-chip-neutral text-muted-foreground",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {label}
    </span>
  );
}

/**
 * A value shown for reference, deliberately not a control: nothing to focus,
 * nothing to submit, and none of the washed-out look of a disabled input.
 * Render inside a `<dl>`.
 */
export function ReadOnlyField({
  label,
  value,
  owner,
  description,
}: {
  label: string;
  value: string;
  owner: ProfileFieldOwner;
  description?: ReactNode;
}) {
  return (
    <div className="grid min-w-0 content-start gap-2">
      <dt className="flex flex-wrap items-center gap-2 text-xs font-semibold tracking-[0.02em]">
        {label}
        <OwnerBadge owner={owner} />
      </dt>
      <dd className="grid gap-1.5">
        <span className="bg-muted/60 border-border flex min-h-9 items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm">
          <Lock className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">{value || "Not provided"}</span>
        </span>
        {description ? <FormDescription>{description}</FormDescription> : null}
      </dd>
    </div>
  );
}

const FALLBACK_POLICY: Omit<OnboardingFieldPolicy, "label"> = {
  section: "identity",
  required: false,
  owner: "agent",
  readOnly: false,
  guidance: "",
};

/** The server's policy for a field, with a safe default if the catalog lacks it. */
export function policyFor(
  fields: Record<string, OnboardingFieldPolicy>,
  name: string,
): OnboardingFieldPolicy {
  return fields[name] ?? { ...FALLBACK_POLICY, label: name.replaceAll("_", " ") };
}
