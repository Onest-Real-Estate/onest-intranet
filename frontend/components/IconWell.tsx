import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * One tile, six tones.
 *
 * `brand` and `muted` are the chrome tones. The five semantic tones are the
 * *same* verified surface/edge/ink triples the status chips use, so a tile
 * that classifies something — a contact's role, an announcement's category —
 * carries colour that means exactly what the chip beside it means, and clears
 * 4.5:1 on both themes for free.
 *
 * A tone is not decoration. If the tile's colour is not encoding something a
 * reader could act on, it is `muted`.
 */
const TONES = {
  /** Gold-tinted: brand moments and the dashboard's headline stat row. */
  brand: "brand-well text-foreground",
  /** Neutral: the repeated tile in panel headers, where gold would be noise. */
  muted: "bg-muted text-muted-foreground",
  info: "bg-chip-info text-info",
  success: "bg-chip-success text-success",
  warning: "bg-chip-warning text-warning-ink",
  destructive: "bg-chip-destructive text-destructive",
  neutral: "bg-chip-neutral text-muted-foreground",
} as const;

export type IconWellTone = keyof typeof TONES;

/** Tinted tile behind a Lucide mark, so icons stay legible on ivory surfaces. */
export function IconWell({
  icon: Icon,
  tone = "brand",
  className,
  iconClassName,
  children,
}: {
  icon?: LucideIcon;
  tone?: keyof typeof TONES;
  className?: string;
  iconClassName?: string;
  /**
   * A non-Lucide mark to sit in the well — a vendor logo, for instance. Keeps
   * third-party brands inside the one tile vocabulary instead of letting them
   * introduce a second tile shape beside it. Ignored when `icon` is given.
   */
  children?: ReactNode;
}) {
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-md",
        TONES[tone],
        className,
      )}
    >
      {Icon ? (
        <Icon className={cn("size-5", iconClassName)} strokeWidth={1.5} aria-hidden />
      ) : (
        children
      )}
    </span>
  );
}
