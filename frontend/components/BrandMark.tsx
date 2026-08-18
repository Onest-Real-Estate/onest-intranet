import type { SVGProps } from "react";

import { cn } from "@/lib/utils";

interface BrandMarkProps extends SVGProps<SVGSVGElement> {
  label?: string;
}

/** Compact roof-and-key mark derived from the Onest Real Estate logo. */
export function BrandMark({ className, label, ...props }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      role={label ? "img" : undefined}
      aria-hidden={label ? undefined : true}
      className={cn("brand-text", className)}
      {...props}
    >
      <title>{label ?? "Onest"}</title>
      <path
        d="M4 24.5 19.4 7.8a1.6 1.6 0 0 1 2.3 0L31 18h6.2l2.8 3.2H29.6L20.5 11 7.8 25.5H4Z"
        fill="currentColor"
      />
      <path
        d="M29.2 20.7H40l-2.7 3.2h-2l-1 1.7-1.2-1.7h-2.2l-1.7-3.2Z"
        fill="currentColor"
      />
      <path
        d="M17.2 20.5h2.6v2.6h-2.6zm3.6 0h2.6v2.6h-2.6zm-3.6 3.6h2.6v2.6h-2.6zm3.6 0h2.6v2.6h-2.6z"
        fill="currentColor"
      />
    </svg>
  );
}
