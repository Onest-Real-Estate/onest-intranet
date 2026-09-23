import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  ArrowLeft,
  ArrowUpRight,
  BadgeCheck,
  CircleAlert,
  CircleCheck,
  Clock,
  LifeBuoy,
  ListChecks,
  Loader,
  Mail,
  MinusCircle,
  PlayCircle,
  Wrench,
} from "lucide-react";
import { useCallback, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  NativeSelect,
  PageHeader,
  StatusBadge,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { AgentTool, AgentToolGroup, MyToolsPageProps } from "@/types";
import type { StatusPresentation } from "@/types/design-system";

type Toggle = (tool: AgentTool, have: boolean) => void;

const shortDate = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

/** Tools that count toward "do you have everything": required, and not
 *  excused by the office. An optional tool left alone is not work left. */
function counts(tool: AgentTool): boolean {
  return tool.required && tool.state.code !== "not_applicable";
}

/**
 * What oNEST has done about this tool, as one chip — or nothing.
 *
 * A self-serve tool nobody has touched has nothing to say: the checkbox is
 * the whole story. Everything else is the office's side, said in a word and
 * an icon so it never rests on colour alone.
 */
function officeStatus(tool: AgentTool): StatusPresentation | null {
  switch (tool.state.code) {
    case "ready":
      return { label: "Confirmed by oNEST", tone: "success", icon: BadgeCheck };
    case "blocked":
      return { label: "Blocked", tone: "destructive", icon: CircleAlert };
    case "not_applicable":
      return { label: "Not needed", tone: "neutral", icon: MinusCircle };
    case "in_progress":
      return { label: "In progress", tone: "info", icon: Loader };
    case "invitation_sent":
      return {
        label: tool.invitation.sentAt
          ? `Invitation sent ${shortDate.format(new Date(tool.invitation.sentAt))}`
          : "Invitation sent",
        tone: "info",
        icon: Mail,
      };
    case "requested":
      return { label: "Requested", tone: "neutral", icon: Clock };
    default:
      if (tool.selfServe) return null;
      // Ticked but not yet confirmed: the agent has done their part, so the
      // chip says what is left rather than repeating "waiting on you".
      return tool.haveIt
        ? { label: "Awaiting oNEST check", tone: "neutral", icon: Clock }
        : { label: "Waiting on your office", tone: "neutral", icon: Clock };
  }
}

/**
 * The figure, as one ruled strip.
 *
 * One segment per tool that counts, in catalog order, so ticking a box fills
 * *its* segment rather than nudging an anonymous bar. The row beneath keeps
 * the office's confirmation apart from the agent's own claim: the two are
 * different facts and a single number would blur them.
 */
function ChecklistSummary({
  tools,
  isSelf,
  confirmed,
  confirmedTotal,
}: {
  tools: AgentTool[];
  isSelf: boolean;
  confirmed: number;
  confirmedTotal: number;
}) {
  const counted = tools.filter(counts);
  const have = counted.filter((tool) => tool.haveIt).length;
  const left = counted.length - have;
  const complete = counted.length > 0 && left === 0;
  const waiting = counted.filter(
    (tool) => !tool.selfServe && !tool.complete && tool.state.code !== "blocked",
  ).length;
  const blocked = counted.filter((tool) => tool.state.code === "blocked").length;
  const training = tools.filter((tool) => tool.training);
  const watched = training.filter((tool) => tool.training?.completed).length;

  return (
    <section
      aria-label="Checklist progress"
      className="bg-card shadow-card @container/summary rounded-(--radius-card) border"
    >
      <div className="grid gap-3 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <p className="text-base font-semibold tracking-[-0.01em]">
            {complete ? (
              <span className="text-success inline-flex items-center gap-2">
                <CircleCheck className="size-5" aria-hidden />
                {isSelf ? "You have every tool you need" : "Every tool is checked off"}
              </span>
            ) : (
              <>
                <span className="tabular-nums">{have}</span>
                <span className="text-muted-foreground font-normal"> of </span>
                <span className="tabular-nums">{counted.length}</span>
                <span className="text-muted-foreground font-normal">
                  {isSelf ? " tools checked off" : " checked off by the agent"}
                </span>
              </>
            )}
          </p>
          {complete ? null : (
            <p className="text-muted-foreground text-sm tabular-nums">{left} to go</p>
          )}
        </div>

        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={counted.length}
          aria-valuenow={have}
          aria-label={`${have} of ${counted.length} tools checked off`}
          className="flex h-2 gap-0.5"
        >
          {counted.map((tool) => (
            <span
              key={tool.slug}
              title={tool.name}
              className={cn(
                "h-full flex-1 rounded-[2px] transition-colors duration-(--motion-base)",
                tool.haveIt ? "bg-success" : "bg-border",
              )}
            />
          ))}
        </div>
      </div>

      <dl className="grid border-t @xl/summary:grid-cols-3 @xl/summary:divide-x @max-xl/summary:divide-y">
        <SummaryCell label="Confirmed by oNEST">
          <span className="tabular-nums">{confirmed}</span>
          <span className="text-muted-foreground font-normal">
            {" "}
            of {confirmedTotal}
          </span>
        </SummaryCell>
        <SummaryCell
          label={
            blocked > 0
              ? "Blocked"
              : isSelf
                ? "Waiting on your office"
                : "Waiting on the office"
          }
        >
          <span className={cn("tabular-nums", blocked > 0 && "text-destructive")}>
            {blocked > 0 ? blocked : waiting}
          </span>
        </SummaryCell>
        <SummaryCell label="Training watched">
          {training.length === 0 ? (
            <span className="text-muted-foreground font-normal">None linked</span>
          ) : (
            <>
              <span className="tabular-nums">{watched}</span>
              <span className="text-muted-foreground font-normal">
                {" "}
                of {training.length}
              </span>
            </>
          )}
        </SummaryCell>
      </dl>
    </section>
  );
}

function SummaryCell({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-5 py-3">
      <dt className="text-muted-foreground text-xs font-semibold tracking-[0.02em]">
        {label}
      </dt>
      <dd className="text-sm font-semibold">{children}</dd>
    </div>
  );
}

/**
 * The setup steps, in a dialog.
 *
 * Steps are the one thing on a card too long to show inline; opening them in
 * place would shove every card after it down the grid.
 */
function SetupDialog({
  tool,
  open,
  onOpenChange,
}: {
  tool: AgentTool;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Set up {tool.name}</DialogTitle>
          <DialogDescription>{tool.provisioningLabel}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-5">
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
            <div className="grid gap-1 border-t pt-4">
              <p className="text-muted-foreground text-xs font-semibold tracking-[0.02em]">
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
            <Link href={tool.supportHref}>
              <LifeBuoy aria-hidden />
              Get support
            </Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * One tool: a box to tick, what the office has done, and the three ways to
 * get unstuck — training, support, and the steps.
 *
 * The checkbox leads because checking off is the job of this page. Its label
 * is the tool name, so the whole title is a target, not just the 20px box.
 */
function ToolCard({
  tool,
  canCheck,
  onToggle,
  agentId,
  canManage,
  stateOptions,
}: {
  tool: AgentTool;
  canCheck: boolean;
  onToggle: Toggle;
  agentId: number;
  canManage: boolean;
  stateOptions: { value: string; label: string }[];
}) {
  const [setupOpen, setSetupOpen] = useState(false);
  const status = officeStatus(tool);
  const excused = tool.state.code === "not_applicable";
  const blocked = tool.state.code === "blocked";
  const hasSetup = tool.steps.length > 0 || Boolean(tool.contact);
  const checkboxId = `have-${tool.slug}`;
  const descriptionId = `about-${tool.slug}`;

  return (
    <article
      aria-label={tool.name}
      className={cn(
        "bg-card shadow-card flex flex-col rounded-(--radius-card) border",
        "transition-[border-color,background-color] duration-(--motion-fast)",
        tool.haveIt && !blocked && "border-chip-success-edge",
        blocked && "border-chip-destructive-edge",
        excused && "bg-muted/40",
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <Checkbox
          id={checkboxId}
          checked={tool.haveIt}
          disabled={!canCheck || excused}
          onCheckedChange={(next) => onToggle(tool, next === true)}
          aria-label={
            canCheck ? `I have ${tool.name}` : `${tool.name}, checked off by agent`
          }
          aria-describedby={descriptionId}
          className={cn(
            "mt-0.5 size-5 rounded-sm",
            "data-[state=checked]:bg-success data-[state=checked]:border-success data-[state=checked]:text-success-foreground",
            "disabled:opacity-60",
          )}
        />
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex items-start justify-between gap-2">
            <label
              htmlFor={checkboxId}
              className={cn(
                "text-sm leading-5 font-semibold",
                canCheck && !excused && "cursor-pointer",
              )}
            >
              {tool.name}
              {tool.required ? null : (
                <span className="text-muted-foreground ml-2 text-xs font-medium">
                  Optional
                </span>
              )}
            </label>
            {tool.openUrl ? (
              <Button
                asChild
                variant="ghost"
                size="icon"
                className="text-muted-foreground -mt-1.5 -mr-1.5 size-7"
              >
                <a
                  href={tool.openUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open ${tool.name} in a new tab`}
                  title={`Open ${tool.name}`}
                >
                  <ArrowUpRight aria-hidden />
                </a>
              </Button>
            ) : null}
          </div>
          <p
            id={descriptionId}
            className="text-muted-foreground line-clamp-2 text-sm leading-5"
          >
            {tool.description}
          </p>
          {status || (!canCheck && tool.haveItAt) ? (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              {status ? <StatusBadge status={status} /> : null}
              {!canCheck && tool.haveItAt ? (
                <span className="text-muted-foreground text-xs">
                  Agent checked off {shortDate.format(new Date(tool.haveItAt))}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {/* The reason you are stuck is the one thing you most need to read, so a
          blocked card says it on its face rather than behind a button. */}
      {blocked && tool.note ? (
        <p className="text-destructive bg-chip-destructive border-chip-destructive-edge mx-4 mb-4 rounded-md border px-3 py-2 text-sm">
          {tool.note}
        </p>
      ) : null}

      <div className="mt-auto flex flex-wrap items-center gap-1 border-t px-2.5 py-2">
        {tool.training ? (
          <Button asChild variant="ghost" size="sm">
            <Link
              href={tool.training.href}
              aria-label={`Training for ${tool.name}: ${tool.training.title}${
                tool.training.completed ? " (watched)" : ""
              }`}
            >
              {tool.training.completed ? (
                <CircleCheck className="text-success" aria-hidden />
              ) : (
                <PlayCircle aria-hidden />
              )}
              Training
              {tool.training.minutes && !tool.training.completed ? (
                <span className="text-muted-foreground font-normal tabular-nums">
                  {tool.training.minutes} min
                </span>
              ) : null}
            </Link>
          </Button>
        ) : null}
        <Button asChild variant="ghost" size="sm">
          <Link href={tool.supportHref} aria-label={`Get support with ${tool.name}`}>
            <LifeBuoy aria-hidden />
            Support
          </Link>
        </Button>
        {hasSetup ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSetupOpen(true)}
            aria-label={`Setup steps for ${tool.name}`}
          >
            <ListChecks aria-hidden />
            Setup
          </Button>
        ) : null}
      </div>

      {canManage ? (
        <div className="grid gap-1.5 border-t px-4 py-3">
          {tool.haveIt && !tool.complete ? (
            // The agent says they have it and nobody has checked yet: the
            // one move worth a button rather than a trip through the select.
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mb-1 justify-self-start"
              onClick={() =>
                router.post(
                  routes.agent_tool_state(agentId),
                  { tool: tool.slug, state: "ready" },
                  { preserveScroll: true },
                )
              }
            >
              <BadgeCheck aria-hidden />
              Confirm ready
            </Button>
          ) : null}
          <label
            className="text-muted-foreground text-xs font-semibold tracking-[0.02em]"
            htmlFor={`state-${tool.slug}`}
          >
            oNEST status
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

      {hasSetup ? (
        <SetupDialog tool={tool} open={setupOpen} onOpenChange={setSetupOpen} />
      ) : null}
    </article>
  );
}

function ToolGroupSection({
  group,
  canCheck,
  onToggle,
  agentId,
  canManage,
  stateOptions,
}: {
  group: AgentToolGroup;
  canCheck: boolean;
  onToggle: Toggle;
  agentId: number;
  canManage: boolean;
  stateOptions: { value: string; label: string }[];
}) {
  const counted = group.tools.filter(counts);
  const have = counted.filter((tool) => tool.haveIt).length;
  const headingId = `group-${group.code}`;

  return (
    <section className="grid gap-3" aria-labelledby={headingId}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={headingId} className="text-base font-semibold tracking-[-0.01em]">
          {group.label}
        </h2>
        {counted.length > 0 ? (
          <p
            className={cn(
              "text-xs tabular-nums",
              have === counted.length
                ? "text-success font-medium"
                : "text-muted-foreground",
            )}
          >
            {have} of {counted.length} checked off
          </p>
        ) : null}
      </div>

      <div className="grid gap-3 @2xl:grid-cols-2 @6xl:grid-cols-3">
        {group.tools.map((tool) => (
          <ToolCard
            key={tool.slug}
            tool={tool}
            canCheck={canCheck}
            onToggle={onToggle}
            agentId={agentId}
            canManage={canManage}
            stateOptions={stateOptions}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Every tool an agent needs, a box to tick for each, and a way to get help.
 *
 * Two facts sit side by side and never merge: the agent's own "I have this"
 * (the checkbox, theirs to set) and what oNEST confirmed (the chip, staff's to
 * set). Readiness counts only the second, so ticking a box can never make an
 * account look working when IT has not seen it.
 */
export default function MyTools() {
  const { agent, groups, readiness, canManage, stateOptions } =
    usePage<MyToolsPageProps>().props;
  const canCheck = agent.isSelf;

  // Ticks land before the server answers, so the box and its segment move
  // under the pointer. Each override clears when the visit settles and the
  // server's own value takes over — including when the write was refused.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const onToggle = useCallback<Toggle>((tool, have) => {
    setPending((current) => ({ ...current, [tool.slug]: have }));
    router.post(
      routes.my_tool_have(tool.slug),
      { have },
      {
        preserveScroll: true,
        preserveState: true,
        onFinish: () => setPending(({ [tool.slug]: _settled, ...rest }) => rest),
      },
    );
  }, []);

  const shown = groups.map((group) => ({
    ...group,
    tools: group.tools.map((tool) =>
      tool.slug in pending ? { ...tool, haveIt: pending[tool.slug] } : tool,
    ),
  }));
  const tools = shown.flatMap((group) => group.tools);

  return (
    <div className="@container grid gap-8">
      <Head title={agent.isSelf ? "My tools" : `${agent.name} · tools`} />
      <PageHeader
        title={agent.isSelf ? "My tools" : agent.name}
        description={
          agent.isSelf
            ? "Tick each tool once you have it. Stuck? Every card has training and support."
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

      {tools.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title="No tools to set up"
          description={
            agent.office
              ? "Nothing in the catalog applies to your office yet."
              : "Tools depend on your office, and none is set on your profile."
          }
          actions={
            <Button asChild variant="outline">
              <Link href={routes.it_support()}>
                <LifeBuoy aria-hidden />
                Get support
              </Link>
            </Button>
          }
        />
      ) : (
        <>
          <ChecklistSummary
            tools={tools}
            isSelf={agent.isSelf}
            confirmed={readiness.ready}
            confirmedTotal={readiness.total}
          />
          {shown.map((group) => (
            <ToolGroupSection
              key={group.code}
              group={group}
              canCheck={canCheck}
              onToggle={onToggle}
              agentId={agent.id}
              canManage={canManage}
              stateOptions={stateOptions}
            />
          ))}
        </>
      )}
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
