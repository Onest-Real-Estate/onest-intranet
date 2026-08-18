import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** Gold-tinted icon well so Lucide marks stay visible on ivory surfaces. */
export function IconWell({
  icon: Icon,
  className,
  iconClassName,
}: {
  icon: LucideIcon;
  className?: string;
  iconClassName?: string;
}) {
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-lg bg-[color-mix(in_oklab,var(--brand-gold)_18%,transparent)] text-foreground",
        className,
      )}
    >
      <Icon className={cn("size-5", iconClassName)} strokeWidth={1.5} aria-hidden />
    </span>
  );
}
