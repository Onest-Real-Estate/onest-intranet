import { AlertCircle, LoaderCircle } from "lucide-react";
import type * as React from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface SurfaceCardProps extends React.ComponentProps<typeof Card> {
  state?: "default" | "loading" | "error" | "success" | "read-only";
  interactive?: boolean;
}

/** Product-neutral card surface with consistent state treatment. */
export function SurfaceCard({
  state = "default",
  interactive = false,
  className,
  children,
  ...props
}: SurfaceCardProps) {
  return (
    <Card
      data-state={state}
      aria-busy={state === "loading" || undefined}
      className={cn(
        "shadow-card gap-5 overflow-hidden py-5",
        interactive &&
          "hover:border-primary/30 hover:shadow-card-hover focus-within:border-ring transition-[transform,box-shadow,border-color] duration-(--motion-fast) hover:-translate-y-px",
        state === "error" && "border-destructive/40",
        state === "success" && "border-success/35",
        state === "read-only" && "bg-muted/30 shadow-none",
        className,
      )}
      {...props}
    >
      {children}
    </Card>
  );
}

export function SurfaceCardHeader({
  className,
  ...props
}: React.ComponentProps<typeof CardHeader>) {
  return <CardHeader className={cn("gap-2 px-5", className)} {...props} />;
}

export function SurfaceCardTitle(props: React.ComponentProps<typeof CardTitle>) {
  return <CardTitle {...props} />;
}

export function SurfaceCardDescription(
  props: React.ComponentProps<typeof CardDescription>,
) {
  return <CardDescription {...props} />;
}

export function SurfaceCardContent({
  className,
  ...props
}: React.ComponentProps<typeof CardContent>) {
  return <CardContent className={cn("px-5", className)} {...props} />;
}

export function SurfaceCardFooter({
  className,
  ...props
}: React.ComponentProps<typeof CardFooter>) {
  return <CardFooter className={cn("gap-2 px-5", className)} {...props} />;
}

/**
 * A static fact in a panel header — a date, a count, a ratio. Deliberately
 * plain text: anything with a border or a chevron reads as a control, and a
 * header fact is never clickable.
 */
export function SurfaceCardMeta({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "text-muted-foreground shrink-0 text-xs font-medium tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

/**
 * The standard panel header: a real heading on the left, and at most one quiet
 * fact or one control on the right. Panels carry no decorative icon tile — the
 * heading is the identifier, and a repeated tile beside every title is noise
 * that competes with the data underneath it.
 */
export function PanelHeader({
  title,
  headingLevel: Heading = "h2",
  description,
  meta,
  action,
  className,
  ...props
}: Omit<React.ComponentProps<typeof CardHeader>, "title"> & {
  title: React.ReactNode;
  /** Match the surrounding document outline; panels under an `h1` use `h2`. */
  headingLevel?: "h2" | "h3";
  description?: React.ReactNode;
  meta?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <SurfaceCardHeader
      className={cn("flex flex-row items-start justify-between gap-3", className)}
      {...props}
    >
      <div className="min-w-0">
        <CardTitle asChild>
          <Heading className="text-base leading-6 font-semibold tracking-[-0.01em]">
            {title}
          </Heading>
        </CardTitle>
        {description ? (
          <p className="text-muted-foreground mt-1 text-sm leading-5">{description}</p>
        ) : null}
      </div>
      {meta || action ? (
        <div className="flex shrink-0 items-center gap-2">
          {meta}
          {action}
        </div>
      ) : null}
    </SurfaceCardHeader>
  );
}

export function CardStateMessage({
  state,
  children,
}: {
  state: "loading" | "error";
  children: React.ReactNode;
}) {
  const Icon = state === "loading" ? LoaderCircle : AlertCircle;
  return (
    <div
      role={state === "error" ? "alert" : "status"}
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
        state === "loading" && "bg-muted/50 text-muted-foreground",
        state === "error" && "border-destructive/25 bg-destructive/5 text-destructive",
      )}
    >
      <Icon
        className={cn("size-4", state === "loading" && "animate-spin")}
        aria-hidden
      />
      {children}
    </div>
  );
}
