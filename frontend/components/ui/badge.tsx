import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center justify-center rounded-full border px-2.5 py-1 text-xs font-semibold tracking-[0.02em] w-fit whitespace-nowrap shrink-0 [&>svg]:size-3.5 gap-1.5 [&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive transition-[color,box-shadow] overflow-visible",
  {
    variants: {
      variant: {
        default: "border-chip-primary-edge bg-chip-primary text-primary",
        secondary:
          "border-chip-neutral-edge bg-chip-neutral text-muted-foreground [a&]:hover:bg-secondary",
        destructive:
          "border-chip-destructive-edge bg-chip-destructive text-destructive",
        // The one variant with no fill: a hairline pill for a category label
        // that should not read as a state. The hairline is still the system's,
        // not `currentColor` — an unset border-color draws the full-strength
        // text colour and out-weighs every filled chip beside it.
        outline:
          "border-chip-neutral-edge text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        success: "border-chip-success-edge bg-chip-success text-success",
        warning: "border-chip-warning-edge bg-chip-warning text-warning-ink",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";

  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
