import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StatusPresentation, StatusTone } from "@/types/design-system";

const toneClasses: Record<StatusTone, string> = {
  neutral: "border-transparent bg-muted text-muted-foreground",
  info: "border-transparent bg-info/12 text-info",
  success: "border-transparent bg-success/12 text-success",
  warning: "border-transparent bg-warning/18 text-warning-ink",
  destructive: "border-transparent bg-destructive/10 text-destructive",
};

export interface StatusBadgeProps
  extends Omit<React.ComponentProps<typeof Badge>, "children"> {
  status: StatusPresentation;
}

/** Always carries explicit copy and, when supplied, an icon—never color alone. */
export function StatusBadge({ status, className, ...props }: StatusBadgeProps) {
  const Icon = status.icon;
  return (
    <Badge
      variant="outline"
      className={cn(toneClasses[status.tone], className)}
      {...props}
    >
      {Icon ? <Icon className="size-3" aria-hidden /> : null}
      <span>{status.label}</span>
    </Badge>
  );
}
