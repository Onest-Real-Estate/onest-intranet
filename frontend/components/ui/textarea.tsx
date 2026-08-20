import type * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:bg-input/30 flex field-sizing-content min-h-24 w-full rounded-lg border bg-transparent px-3.5 py-2.5 text-base leading-6 shadow-xs transition-[color,background-color,border-color,box-shadow] duration-(--motion-fast) outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-70 md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
