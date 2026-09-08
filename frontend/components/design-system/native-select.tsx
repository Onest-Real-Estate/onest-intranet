import { ChevronDownIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A real `<select>` wearing the system's field styling.
 *
 * Forms that post natively (see `CreateSheet`) cannot use the Radix `Select`
 * without adding a second code path for the submitted value, so those pages
 * reach for a bare `<select>` — and a bare `<select>` sitting beside an
 * `<Input>` in the same form is visibly not the same control: different
 * radius, different padding, no focus ring. This keeps the native element and
 * gives it the field contract, so the two agree.
 *
 * Reach for the Radix `Select` when the control is client-state driven and
 * needs styled options; reach for this when the form posts to Django.
 */
export function NativeSelect({
  className,
  children,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <div className="relative w-full">
      <select
        data-slot="native-select"
        className={cn(
          // Deliberately the same recipe as `Input`, minus the file:/placeholder
          // parts a select cannot have. `pr-10` leaves room for the chevron.
          "border-input dark:bg-input/30 flex h-9 w-full min-w-0 appearance-none rounded-md border bg-transparent py-1 pr-10 pl-3 text-base shadow-xs transition-[color,background-color,border-color,box-shadow] duration-(--motion-fast) outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-70 md:text-sm",
          // Native option menus ignore most CSS; color-scheme + option colors
          // reduce light-on-white popup text when the OS list stays light.
          "scheme-light dark:scheme-dark",
          "[&_option]:bg-popover [&_option]:text-popover-foreground",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2"
      />
    </div>
  );
}
