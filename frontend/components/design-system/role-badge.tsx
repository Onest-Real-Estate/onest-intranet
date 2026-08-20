import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { roleDescription, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";

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
      className={cn(
        "max-w-full gap-1 border-border bg-muted/40 font-normal text-foreground",
        className,
      )}
      title={tip || undefined}
      {...props}
    >
      <span className="truncate">{resolvedLabel}</span>
      {scopeLabel ? (
        <span className="truncate text-muted-foreground">· {scopeLabel}</span>
      ) : null}
    </Badge>
  );
}
