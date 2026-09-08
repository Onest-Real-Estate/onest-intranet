import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import {
  getRoleCatalogEntry,
  type RoleScopeType,
  roleDescription,
  roleLabel,
} from "@/lib/roles";
import { cn } from "@/lib/utils";

/**
 * Role chips are colored by the breadth of authority a role carries, not by an
 * arbitrary per-code palette: a reader scanning a permission column sees
 * company-wide roles separate themselves from office roles before they read a
 * single word.
 *
 * Hue carries the category and lightness carries the ordering — broadest reads
 * darkest — because lightness is the one channel every colour-vision
 * deficiency preserves. The role name is always present as text, so colour is
 * never the only code.
 *
 * `assigned_record` takes the neutral chip on purpose. It is the narrowest
 * scope, "no organizational breadth" is honestly a neutral fact, and the gold
 * it would otherwise claim belongs to actions — a gold badge beside a gold
 * button splits the one colour the page uses to say "press this".
 */
const scopeToneClasses: Record<RoleScopeType, string> = {
  company: "border-chip-role-company-edge bg-chip-role-company text-role-company-ink",
  region: "border-chip-role-region-edge bg-chip-role-region text-role-region-ink",
  office: "border-chip-role-office-edge bg-chip-role-office text-role-office-ink",
  assigned_record: "border-chip-neutral-edge bg-chip-neutral text-muted-foreground",
};

const PROTECTED_TONE =
  "border-chip-role-protected-edge bg-chip-role-protected text-role-protected-ink";
const UNKNOWN_TONE = "border-chip-neutral-edge bg-chip-neutral text-muted-foreground";

/** Broadest scope first: a role valid company-wide is a company-wide role. */
const SCOPE_BREADTH: readonly RoleScopeType[] = [
  "company",
  "region",
  "office",
  "assigned_record",
];

function roleToneClass(code: string): string {
  const entry = getRoleCatalogEntry(code);
  if (!entry) {
    return UNKNOWN_TONE;
  }
  if (entry.protected) {
    return PROTECTED_TONE;
  }
  const broadest = SCOPE_BREADTH.find((scope) => entry.validScopeTypes.includes(scope));
  return broadest ? scopeToneClasses[broadest] : UNKNOWN_TONE;
}

export interface RoleBadgeProps
  extends Omit<React.ComponentProps<typeof Badge>, "children"> {
  /** Stable role code from the brokerage catalog. */
  code: string;
  /** Optional override when the server already resolved a label. */
  label?: string;
  /** Organizational scope shown beside the name (region/office/company). */
  scopeLabel?: string;
  /** Explain why this role cannot be assigned by the current actor. */
  blockReason?: string | null;
}

/**
 * Presentational role chip. Never treat visibility of this badge as proof of
 * authorization — enforce permissions on the server and with
 * ``hasPermission`` / ``PermissionRequired``.
 */
export function RoleBadge({
  code,
  label,
  scopeLabel,
  blockReason,
  className,
  title,
  ...props
}: RoleBadgeProps) {
  const resolvedLabel = label ?? roleLabel(code);
  const description = roleDescription(code);
  const tip =
    title ??
    [description, scopeLabel ? `Scope: ${scopeLabel}` : null, blockReason]
      .filter(Boolean)
      .join(" · ");

  return (
    <Badge
      variant="outline"
      // Capped rather than `max-w-full`: an office path is a sentence, and a
      // chip that grows to hold one stops being a chip and takes the column
      // with it. The full scope stays reachable in the title.
      className={cn(
        "max-w-64 gap-1 overflow-hidden font-medium",
        roleToneClass(code),
        className,
      )}
      title={tip || undefined}
      {...props}
    >
      {/* The role is the fact; the scope qualifies it. Only the qualifier
          gives way when the chip runs out of room. */}
      <span className="shrink-0">{resolvedLabel}</span>
      {scopeLabel ? <span className="truncate opacity-70">· {scopeLabel}</span> : null}
    </Badge>
  );
}
