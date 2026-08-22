import type * as React from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

/**
 * The standard slide-over for forms and focused flows.
 *
 * Opens from the right over a dimmed page, keeps the page context visible on
 * the left, and carries the form chrome once instead of per-field: a real
 * heading with description up top, one scrollable body, and a sticky action
 * footer so primary buttons never scroll away. Forms that benefit from full
 * width or a persistent side panel (previews, inheritance hints) belong on
 * their own page — the sheet is for focused, single-object work.
 */
export function FormSheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: Omit<React.ComponentProps<typeof Sheet>, "className"> & {
  className?: string;
  title: string;
  description?: string;
  /** Scrollable form body; render your own <form> inside. */
  children: React.ReactNode;
  /** Sticky actions rendered at the bottom edge of the sheet. */
  footer?: React.ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn("flex w-full flex-col gap-0 p-0 sm:max-w-xl", className)}
      >
        <SheetHeader className="gap-1 border-b px-6 py-5">
          <div className="pr-8">
            <SheetTitle className="text-base leading-6 font-semibold tracking-[-0.01em]">
              {title}
            </SheetTitle>
          </div>
          {description ? (
            <SheetDescription className="text-muted-foreground text-sm leading-5">
              {description}
            </SheetDescription>
          ) : null}
        </SheetHeader>
        {children}
        {footer ? (
          <div className="border-border bg-background sticky bottom-0 border-t px-6 py-4">
            {footer}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

export function FormSheetBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("min-h-0 flex-1 overflow-y-auto px-6 py-5", className)}
      {...props}
    />
  );
}
