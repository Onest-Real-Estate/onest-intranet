import { AlertCircle } from "lucide-react";
import type * as React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { firstFieldError, validationEntries } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

export function FormField({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("grid min-w-0 gap-2", className)} {...props} />;
}

export function FormLabel({
  required,
  optional,
  children,
  className,
  ...props
}: React.ComponentProps<typeof Label> & {
  required?: boolean;
  optional?: boolean;
}) {
  return (
    <Label
      className={cn("gap-1 text-xs font-semibold tracking-[0.02em]", className)}
      {...props}
    >
      {children}
      {required ? (
        <span className="text-destructive" aria-hidden>
          *
        </span>
      ) : null}
      {required ? <span className="sr-only"> (required)</span> : null}
      {optional ? (
        <span className="text-muted-foreground ml-auto text-xs font-normal">
          Optional
        </span>
      ) : null}
    </Label>
  );
}

export function FormDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      className={cn(
        "text-muted-foreground min-w-0 break-words text-sm leading-5",
        className,
      )}
      {...props}
    />
  );
}

export function FormFieldError({
  message,
  messages,
  className,
  ...props
}: Omit<React.ComponentProps<"p">, "children"> & {
  message?: string;
  messages?: string[];
}) {
  const content = messages?.length ? messages.join(" ") : message;
  if (!content) {
    return null;
  }
  return (
    <p
      role="alert"
      className={cn("text-destructive flex items-start gap-1.5 text-sm", className)}
      {...props}
    >
      <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{content}</span>
    </p>
  );
}

export function fieldA11yProps(
  field: string,
  errors: ValidationErrors | undefined,
  descriptionId?: string,
  controlId: string = field,
) {
  const error = firstFieldError(errors, field);
  const errorId = error ? `${controlId}_error` : undefined;
  return {
    "aria-invalid": Boolean(error) || undefined,
    "aria-describedby": [descriptionId, errorId].filter(Boolean).join(" ") || undefined,
  } as const;
}

export function FormErrorSummary({
  errors,
  labels,
  title = "Check the highlighted fields",
  className,
}: {
  errors: ValidationErrors;
  labels?: Record<string, string>;
  title?: string;
  className?: string;
}) {
  const entries = validationEntries(errors, labels);
  if (entries.length === 0) {
    return null;
  }
  return (
    <section
      role="alert"
      aria-labelledby="form-error-summary-title"
      className={cn(
        "border-chip-destructive-edge bg-chip-destructive rounded-lg border p-4",
        className,
      )}
    >
      <h2
        id="form-error-summary-title"
        className="text-destructive flex items-center gap-2 text-sm font-semibold"
      >
        <AlertCircle className="size-4" aria-hidden />
        {title}
      </h2>
      <ul className="mt-2 grid gap-1 pl-6 text-sm">
        {entries.map((entry) => (
          <li key={entry.id}>
            {entry.field ? (
              <a
                className="decoration-destructive/40 hover:decoration-destructive underline underline-offset-2"
                href={`#${entry.field}`}
              >
                <span className="font-medium capitalize">{entry.label}:</span>{" "}
                {entry.message}
              </a>
            ) : (
              entry.message
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReadOnlyValue({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-1", className)}>
      <dt className="text-muted-foreground text-xs font-semibold">{label}</dt>
      <dd className="min-w-0 text-sm break-words">{children}</dd>
    </div>
  );
}

/**
 * Where a long form ends: what saving will do on the left, the one control that
 * does it on the right.
 *
 * Deliberately not another `SurfaceCard`. Every panel above it is a group of
 * fields, and giving the closing action the same white surface and border makes
 * it read as one more group to fill in. The recessed tint and the absence of a
 * heading say the form is over.
 */
export function FormActionBar({
  status,
  children,
  className,
  ...props
}: Omit<React.ComponentProps<"div">, "children"> & {
  /** What saving does right now — announced, so a submit is not silent. */
  status: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "bg-muted/40 border-border/60 flex flex-wrap items-center justify-between gap-4 rounded-lg border px-5 py-4",
        className,
      )}
      {...props}
    >
      <p className="text-muted-foreground min-w-0 text-sm" aria-live="polite">
        {status}
      </p>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  );
}
