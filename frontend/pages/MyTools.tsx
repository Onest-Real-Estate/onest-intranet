import { Head, Link, router, usePage } from "@inertiajs/react";
import type { LucideIcon } from "lucide-react";
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  CircleAlert,
  CircleDashed,
  LifeBuoy,
  Loader,
  MinusCircle,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NativeSelect,
  PageHeader,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { IconWell, type IconWellTone } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { AgentTool, AgentToolGroup, MyToolsPageProps } from "@/types";

/**
 * Each state gets a mark and a tone, so a card says where it stands twice —
 * once in a shape, once in a word. Colour alone fails exactly the reader who
 * most needs to spot the blocked one.
 */
const STATE_MARK: Record<string, { icon: LucideIcon; tone: IconWellTone }> = {
  ready: { icon: Check, tone: "success" },
  in_progress: { icon: Loader, tone: "info" },
  blocked: { icon: CircleAlert, tone: "destructive" },
  not_applicable: { icon: MinusCircle, tone: "muted" },
  not_started: { icon: CircleDashed, tone: "muted" },
};

/**
 * The readiness figure.
 *
 * The count leads in words and the bar sits under it: a progress ring would
 * make the *number* the subject, and the subject is the work left.
 */
function ReadinessBar({
  ready,
  total,
  percent,
  complete,
  yourMove,
  waiting,
}: {
  ready: number;
  total: number;
  percent: number;
  complete: boolean;
  /** Outstanding tools this reader can set up themselves right now. */
  yourMove: number;
  /** Outstanding tools somebody else has to action. */
  waiting: number;
}) {
  return (
    <div className="grid gap-2.5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm font-medium">
          {complete ? (
            <span className="text-success inline-flex items-center gap-1.5">
              <Check className="size-4" aria-hidden />
              Everything is set up
            </span>
          ) : (
            <>
              <span className="text-foreground tabular-nums">{ready}</span>
              <span className="text-muted-foreground"> of </span>
              <span className="text-foreground tabular-nums">{total}</span>
              <span className="text-muted-foreground"> ready</span>
            </>
          )}
        </p>
        <p className="text-muted-foreground text-xs tabular-nums">{percent}%</p>
      </div>

      {/* What the tint on the cards below actually means, said once in words.
          An accent nobody can name is decoration; this is the sentence that
          turns it into a filter the reader can apply by eye. */}
      {complete ? null : (
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          {yourMove > 0 ? (
            <span className="text-info inline-flex items-center gap-1.5 font-medium">
              <UserRound className="size-3.5" aria-hidden />
              {yourMove} you can set up now
            </span>
          ) : null}
          {yourMove > 0 && waiting > 0 ? <span aria-hidden>·</span> : null}
          {waiting > 0 ? <span>{waiting} waiting on oNEST</span> : null}
        </p>
      )}
      <div
        className="bg-muted h-1.5 w-full overflow-hidden rounded-full"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${ready} of ${total} tools ready`}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700 ease-out",
            complete ? "bg-success" : "bg-primary",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/**
 * The guide, in a dialog rather than an inline disclosure.
 *
 * A card that expands in place shoves every card after it down the grid, so
 * opening one answer costs the reader the position of every other. A dialog
 * gives the steps room, keeps the grid still, and is where a "how do I do
 * this" answer belongs once it is longer than a line.
 */
function GuideDialog({
  tool,
  supportPath,
  open,
  onOpenChange,
}: {
  tool: AgentTool;
  supportPath: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{tool.name}</DialogTitle>
          <DialogDescription>{tool.provisioningLabel}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-5">
          {tool.note ? (
            // The reason you are stuck leads, because it is why you opened this.
            <p className="text-warning-ink bg-chip-warning border-chip-warning-edge rounded-md border px-3 py-2 text-sm">
              {tool.note}
            </p>
          ) : null}

          {tool.steps.length > 0 ? (
            <ol className="grid gap-3">
              {tool.steps.map((step, index) => (
                <li key={step} className="flex gap-3 text-sm leading-6">
                  <span className="bg-muted text-muted-foreground mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-micro font-semibold tabular-nums">
                    {index + 1}
                  </span>
                  <span className="max-w-measure">{step}</span>
                </li>
              ))}
            </ol>
          ) : null}

          {tool.contact ? (
            <div className="border-border/70 grid gap-1 border-t pt-4">
              <p className="text-muted-foreground text-xs font-semibold tracking-[0.02em] uppercase">
                Who to ask
              </p>
              <p className="max-w-measure text-sm">{tool.contact}</p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          {tool.helpUrl ? (
            <Button asChild variant="ghost">
              <a href={tool.helpUrl} target="_blank" rel="noopener noreferrer">
                Vendor help
                <ArrowUpRight aria-hidden />
              </a>
            </Button>
          ) : null}
          <Button asChild variant="outline">
            <Link href={tool.requestPath || supportPath}>
              <LifeBuoy aria-hidden />
              Ask IT
            </Link>
          </Button>
          {tool.openUrl ? (
            <Button asChild>
              <a href={tool.openUrl} target="_blank" rel="noopener noreferrer">
                Open {tool.name}
                <ArrowUpRight aria-hidden />
              </a>
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * One tool, as a card that is its own object rather than a box inside a panel.
 *
 * The cards sit directly on the page — not nested in a `SurfaceCard` — because
 * a bordered box inside a bordered box is an outline drawn for no reason. Each
 * carries a state mark, so the grid can be read by scanning marks alone, and
 * at most one primary action, so there is never a question of what to press.
 */
function ToolCard({
  tool,
  agentId,
  canManage,
  stateOptions,
  supportPath,
}: {
  tool: AgentTool;
  agentId: number;
  canManage: boolean;
  stateOptions: { value: string; label: string }[];
  supportPath: string;
}) {
  const [guideOpen, setGuideOpen] = useState(false);
  const mark = STATE_MARK[tool.state.code] ?? STATE_MARK.not_started;
  const hasGuide = tool.steps.length > 0 || Boolean(tool.contact);
  const yourMove = tool.selfServe && !tool.complete;

  return (
    <article
      className={cn(
        // A column, not a grid: `mt-auto` on the footer is what lands every
        // card's action on the same line across a row, and it is inert under
        // `grid content-start`. Uneven buttons make a grid read as a pile.
        "bg-card shadow-card flex flex-col gap-3 rounded-(--radius-card) border p-4",
        "transition-[border-color,box-shadow,translate] duration-(--motion-fast)",
        // Elevation answers a state change; it never decorates a resting surface.
        "hover:border-border-strong hover:shadow-card-hover hover:-translate-y-px",
        tool.complete && "border-success/25",
        tool.state.tone === "destructive" && "border-destructive/30",
      )}
      aria-label={`${tool.name} — ${tool.state.label}`}
    >
      <div className="flex items-start gap-3">
        <IconWell
          icon={mark.icon}
          tone={mark.tone}
          className="size-9"
          iconClassName="size-4"
        />
        <div className="grid min-w-0 flex-1 gap-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-sm font-semibold">{tool.name}</h3>
            {tool.required ? null : (
              <span className="text-muted-foreground text-micro font-semibold tracking-[0.02em] uppercase">
                Optional
              </span>
            )}
          </div>
          <p
            className={cn(
              "text-xs font-medium",
              tool.complete
                ? "text-success"
                : tool.state.tone === "destructive"
                  ? "text-destructive"
                  : "text-muted-foreground",
            )}
          >
            {tool.state.label}
          </p>
        </div>
      </div>

      <p className="text-muted-foreground line-clamp-2 text-sm leading-6">
        {tool.description}
      </p>

      {/* Whose move it is, in words and a mark — but deliberately *not* in
          colour. Most of this catalog is self-serve, so tinting it lit up two
          thirds of the page: an accent carried by the majority is the
          background, and it drowned the handful of states that genuinely need
          finding. The count in the header says it once, where it is rare
          enough to read. */}
      <div className="text-muted-foreground border-border/70 mt-auto flex items-center gap-1.5 border-t pt-3 text-xs">
        {yourMove ? <UserRound className="size-3 shrink-0" aria-hidden /> : null}
        {tool.provisioningLabel}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {hasGuide ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setGuideOpen(true)}
          >
            <BookOpen aria-hidden />
            How to set it up
          </Button>
        ) : null}
        {tool.openUrl ? (
          <Button asChild variant="ghost" size="sm">
            <a href={tool.openUrl} target="_blank" rel="noopener noreferrer">
              Open
              <ArrowUpRight aria-hidden />
            </a>
          </Button>
        ) : null}
      </div>

      {canManage ? (
        <div className="border-border/70 grid gap-1.5 border-t pt-3">
          <label
            className="text-muted-foreground text-micro font-semibold tracking-[0.02em] uppercase"
            htmlFor={`state-${tool.slug}`}
          >
            Mark as
          </label>
          <NativeSelect
            id={`state-${tool.slug}`}
            className="h-8 text-xs"
            value={tool.state.code}
            onChange={(event) =>
              router.post(
                routes.agent_tool_state(agentId),
                { tool: tool.slug, state: event.target.value },
                { preserveScroll: true },
              )
            }
          >
            {stateOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </div>
      ) : null}

      {hasGuide ? (
        <GuideDialog
          tool={tool}
          supportPath={supportPath}
          open={guideOpen}
          onOpenChange={setGuideOpen}
        />
      ) : null}
    </article>
  );
}

/**
 * One shelf: a heading with its own progress, then its cards.
 *
 * The heading is a plain section header rather than a panel, so the cards are
 * the only boxes on the page. Nesting them inside a `SurfaceCard` would draw a
 * second outline around every group for nothing.
 */
function ToolGroupSection({
  group,
  agentId,
  canManage,
  stateOptions,
  supportPath,
}: {
  group: AgentToolGroup;
  agentId: number;
  canManage: boolean;
  stateOptions: { value: string; label: string }[];
  supportPath: string;
}) {
  const complete = group.total > 0 && group.ready === group.total;
  const percent =
    group.total === 0 ? 100 : Math.round((group.ready / group.total) * 100);

  return (
    <section className="grid gap-4" aria-label={group.label}>
      <div className="grid gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-base font-semibold tracking-[-0.01em]">{group.label}</h2>
          <p
            className={cn(
              "text-xs tabular-nums",
              complete ? "text-success font-medium" : "text-muted-foreground",
            )}
          >
            {group.ready} of {group.total} ready
          </p>
        </div>
        {/* A rule per shelf, filled to that shelf's own progress. It is the same
            hairline the system separates everything else with, doing one more
            job — not a second widget. */}
        <div className="bg-border h-px w-full overflow-hidden" aria-hidden>
          <div
            className={cn(
              "h-full transition-[width] duration-700 ease-out",
              complete ? "bg-success" : "bg-primary",
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <div className="grid gap-3 @2xl:grid-cols-2 @5xl:grid-cols-3">
        {group.tools.map((tool) => (
          <ToolCard
            key={tool.slug}
            tool={tool}
            agentId={agentId}
            canManage={canManage}
            stateOptions={stateOptions}
            supportPath={supportPath}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Everything an agent needs set up, and how to get each one.
 *
 * The same page serves the agent reading their own list and somebody who
 * covers them: what differs is `canManage`, which the server decides and which
 * is false for an administrator looking at their own rows, because
 * self-attestation would make the figure meaningless.
 */
export default function MyTools() {
  const { agent, groups, readiness, canManage, stateOptions, supportPath } =
    usePage<MyToolsPageProps>().props;

  // Derived from what the server already sent rather than asked for again:
  // the split is a reading of the same rows the cards render, so the sentence
  // and the tints beneath it cannot disagree.
  const outstanding = groups
    .flatMap((group) => group.tools)
    .filter((tool) => tool.required && !tool.complete);
  const yourMove = outstanding.filter((tool) => tool.selfServe).length;
  const waiting = outstanding.length - yourMove;

  return (
    <div className="@container grid gap-10">
      <Head title={agent.isSelf ? "My tools" : `${agent.name} · tools`} />
      <PageHeader
        title={agent.isSelf ? "My tools" : agent.name}
        description={
          agent.isSelf
            ? "The accounts and apps you need, and how to get each one."
            : `Tool setup for ${agent.office ?? "this agent"}.`
        }
        actions={
          agent.isSelf ? null : (
            <Button asChild variant="outline">
              <Link href={routes.team_tool_readiness()}>
                <ArrowLeft aria-hidden />
                All agents
              </Link>
            </Button>
          )
        }
      />

      <ReadinessBar {...readiness} yourMove={yourMove} waiting={waiting} />

      {groups.map((group) => (
        <ToolGroupSection
          key={group.code}
          group={group}
          agentId={agent.id}
          canManage={canManage}
          stateOptions={stateOptions}
          supportPath={supportPath}
        />
      ))}
    </div>
  );
}

MyTools.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "My tools",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My tools" },
        ],
      },
      variant: "wide",
    },
  ] as const;
