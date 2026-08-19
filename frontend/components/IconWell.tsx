import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const TONES = {
  /** Gold-tinted: brand moments and the dashboard's headline stat row. */
  brand: "brand-well text-foreground",
  /** Neutral: the repeated tile in panel headers, where gold would be noise. */
  muted: "bg-muted text-muted-foreground",
} as const;

/** Tinted tile behind a Lucide mark, so icons stay legible on ivory surfaces. */
export function IconWell({
  icon: Icon,
  tone = "brand",
  className,
  iconClassName,
}: {
  icon: LucideIcon;
  tone?: keyof typeof TONES;
  className?: string;
  iconClassName?: string;
}) {
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-lg",
        TONES[tone],
        className,
      )}
    >
      <Icon className={cn("size-5", iconClassName)} strokeWidth={1.5} aria-hidden />
    </span>
  );
}
