import {
  CircleAlert,
  CircleCheck,
  Info,
  type LucideIcon,
  TriangleAlert,
} from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

type CalloutTone = "neutral" | "info" | "success" | "warning" | "destructive";

/**
 * A tinted surface behind a hairline of the same hue — the same vocabulary as
 * a status chip, one size up, and drawing on the same verified surface/ink
 * token pairs so a note and a chip beside it agree. `neutral` is the default
 * because most notes are orientation, not alarm: reserve the coloured tones
 * for something the reader has to do or decide.
 */
const toneClasses: Record<CalloutTone, string> = {
  neutral: "border-chip-neutral-edge bg-chip-neutral",
  info: "border-chip-info-edge bg-chip-info",
  success: "border-chip-success-edge bg-chip-success",
  warning: "border-chip-warning-edge bg-chip-warning",
  destructive: "border-chip-destructive-edge bg-chip-destructive",
};

/**
 * The mark's own ink, applied to the mark and nothing else. A descendant
 * selector would also repaint an icon inside the action button, which belongs
 * to the button's variant rather than to the note's tone.
 */
const toneInk: Record<CalloutTone, string> = {
  neutral: "text-muted-foreground",
  info: "text-info",
  success: "text-success",
  warning: "text-warning-ink",
  destructive: "text-destructive",
};

const toneIcons: Record<CalloutTone, LucideIcon> = {
  neutral: Info,
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  destructive: CircleAlert,
};

/**
 * One sentence of standing context about the page or a section of it: what a
 * reader is allowed to do here, what an edit will change, why a control is
 * unavailable.
 *
 * Not for validation — a field's error belongs under the field — and not for
 * a transient result. Those are different jobs, and a page that says
 * everything in banners says nothing.
 */
export function Callout({
  tone = "neutral",
  icon,
  title,
  action,
  children,
  className,
  ...props
}: Omit<React.ComponentProps<"div">, "title"> & {
  tone?: CalloutTone;
  /** Overrides the tone's default mark where a specific one says more. */
  icon?: LucideIcon;
  title?: React.ReactNode;
  /** At most one control, on the trailing edge. */
  action?: React.ReactNode;
}) {
  const Icon = icon ?? toneIcons[tone];
  return (
    // No live-region role by default: most notes render with the page, and a
    // status region announces every one of them on arrival. A caller whose
    // note appears in response to an action passes `role` itself.
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-4 py-3 text-sm",
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      <Icon className={cn("size-4 shrink-0", toneInk[tone])} aria-hidden />
      <div className="min-w-0 flex-1 leading-5">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
