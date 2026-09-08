import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StatusPresentation, StatusTone } from "@/types/design-system";

/**
 * Each tone is a tinted surface behind a hairline of the same hue. The outline
 * is what lets a status read as a discrete chip in a dense table row rather
 * than as a smudge of colour behind the words.
 *
 * Surface and ink are separate tokens rather than an alpha of the ink: tinting
 * a dark card with the ink colour lifts the background toward the text, and
 * the pair that cleared AA in light mode failed it in dark.
 */
const toneClasses: Record<StatusTone, string> = {
  neutral: "border-chip-neutral-edge bg-chip-neutral text-muted-foreground",
  info: "border-chip-info-edge bg-chip-info text-info",
  success: "border-chip-success-edge bg-chip-success text-success",
  warning: "border-chip-warning-edge bg-chip-warning text-warning-ink",
  destructive: "border-chip-destructive-edge bg-chip-destructive text-destructive",
};

/**
 * Narrow a server tone string to a tone this component can paint.
 *
 * The backend catalogues `danger` where the design system says `destructive`,
 * and both vocabularies are load-bearing where they live — so the translation
 * happens once, here, instead of in a copy of this function on every page that
 * renders a status. Anything unrecognised falls back to neutral rather than
 * throwing: an unknown status should still render, just without a claim about
 * how alarming it is.
 */
export function toStatusTone(raw: string): StatusTone {
  if (raw === "danger") return "destructive";
  if (
    raw === "neutral" ||
    raw === "info" ||
    raw === "success" ||
    raw === "warning" ||
    raw === "destructive"
  ) {
    return raw;
  }
  return "neutral";
}

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
      {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
      <span>{status.label}</span>
    </Badge>
  );
}
