import { Head, Link, usePage } from "@inertiajs/react";
import {
  CheckCircle2,
  ChevronRight,
  CircleDot,
  LifeBuoy,
  MessageSquare,
  Plus,
  Wrench,
} from "lucide-react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { IconWell } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { FeedbackMinePageProps, FeedbackRow } from "@/types";

/** A mark per status, so a glance answers "where has this got to". */
const STATUS_ICONS: Record<string, typeof LifeBuoy> = {
  new: CircleDot,
  triaged: CircleDot,
  in_progress: Wrench,
  needs_info: MessageSquare,
  resolved: CheckCircle2,
  closed: CheckCircle2,
};

function formatMoment(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}

/**
 * A report the reader sent.
 *
 * The tile carries the *status* tone rather than the category's: on your own
 * list the question is "where has this got to", and colour should answer the
 * question being asked.
 */
function TicketRow({ row }: { row: FeedbackRow }) {
  const waiting = row.status.code === "needs_info";
  return (
    <li
      className={cn(
        "bg-card hover:border-border-strong relative flex items-start gap-3 rounded-lg border p-4 transition-colors duration-(--motion-fast)",
        waiting ? "border-chip-warning-edge" : "border-border/70",
      )}
    >
      <IconWell
        icon={STATUS_ICONS[row.status.code] ?? MessageSquare}
        tone={row.status.tone}
        className="mt-0.5 hidden size-9 sm:grid"
      />
      <div className="grid min-w-0 flex-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={row.status} />
          <span className="text-muted-foreground text-xs">{row.category.label}</span>
        </div>
        <h2 className="text-sm leading-snug font-medium text-balance">
          <Link
            href={routes.feedback_detail(row.id)}
            className="focus-visible:outline-ring rounded-sm focus-visible:outline-2 focus-visible:-outline-offset-2"
          >
            {/* The whole row is the target; the title keeps the accessible
                name and the only tab stop. */}
            <span className="absolute inset-0" aria-hidden />
            {row.summary}
          </Link>
        </h2>
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <span className="font-medium tabular-nums">{row.reference}</span>
          <span aria-hidden>·</span>
          <span>Sent {formatMoment(row.createdAt)}</span>
          {waiting ? (
            // Said in words as well as in tone: this is the row that needs the
            // reader to do something.
            <>
              <span aria-hidden>·</span>
              <span className="text-warning-ink font-medium">Needs your reply</span>
            </>
          ) : null}
        </p>
      </div>
      <ChevronRight
        aria-hidden
        className="text-muted-foreground/60 mt-2 hidden size-4 shrink-0 sm:block"
      />
    </li>
  );
}

/**
 * The submitter's own reports.
 *
 * `for_reader` with `can_triage=false` returns their rows and nobody else's,
 * whatever office they are in — feedback is personal, and "who else
 * complained" is not a question the reporter gets to ask.
 */
export default function FeedbackMine() {
  const { tickets } = usePage<FeedbackMinePageProps>().props;

  return (
    <>
      <Head title="My reports" />
      <div className="grid gap-8">
        <PageHeader
          title="My reports"
          description="Everything you have sent to support, newest first."
          actions={
            <Button asChild>
              <Link href={routes.feedback_submit()}>
                <Plus aria-hidden />
                New report
              </Link>
            </Button>
          }
        />

        <SurfaceCard>
          <PanelHeader
            divided
            title="Your reports"
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {tickets.pagination.totalItems}{" "}
                {tickets.pagination.totalItems === 1 ? "report" : "reports"}
              </span>
            }
          />
          <SurfaceCardContent>
            {tickets.items.length > 0 ? (
              <ul className="grid gap-3">
                {tickets.items.map((row) => (
                  <TicketRow key={row.id} row={row} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={LifeBuoy}
                title="You have not sent anything yet"
                description="When something is broken or confusing, tell us — it goes straight to the people who can fix it."
                actions={
                  <Button asChild variant="outline">
                    <Link href={routes.feedback_submit()}>Get help</Link>
                  </Button>
                }
              />
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

FeedbackMine.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "My reports",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My reports", href: routes.feedback_mine() },
        ],
      },
      variant: "standard",
    },
  ] as const;
