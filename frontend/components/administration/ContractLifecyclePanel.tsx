import { Check } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  Timeline,
  type TimelineItem,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  type ContractStamps,
  isLifecycleActionCode,
  LIFECYCLE_ACTION_ORDER,
  LIFECYCLE_ACTIONS,
  type LifecycleActionCode,
  type LifecycleIntent,
  lifecycleSteps,
} from "./contract-lifecycle";

function stampLabel(iso: string | null): string | undefined {
  if (!iso) return undefined;
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
      new Date(iso),
    );
  } catch {
    return undefined;
  }
}

/**
 * One button per lifecycle move, full width so the group reads as a column of
 * decisions rather than a wrapped toolbar. The hint sits under the label
 * because these moves are irreversible often enough that "Supersede" alone is
 * not a description of what happens.
 */
function ActionButton({
  code,
  emphasis,
  onRun,
}: {
  code: LifecycleActionCode;
  emphasis: "primary" | "secondary" | "destructive";
  onRun: (code: LifecycleActionCode) => void;
}) {
  const spec = LIFECYCLE_ACTIONS[code];
  const Icon = spec.icon;
  return (
    <div className="grid gap-1">
      <Button
        type="button"
        variant={
          emphasis === "primary"
            ? "default"
            : emphasis === "destructive"
              ? "destructive"
              : "outline"
        }
        className="w-full justify-start"
        onClick={() => onRun(code)}
      >
        <Icon className="size-4" aria-hidden />
        {spec.label}
      </Button>
      {spec.hint ? (
        <p className="text-muted-foreground px-1 text-xs leading-4">{spec.hint}</p>
      ) : null}
    </div>
  );
}

function Group({
  title,
  className,
  children,
}: {
  title?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-3", className)}>
      {title ? (
        <p className="text-muted-foreground text-xs font-semibold tracking-[0.06em] uppercase">
          {title}
        </p>
      ) : null}
      {children}
    </div>
  );
}

/**
 * Where the agreement is, and the moves available from here.
 *
 * The panel this replaced was eleven identically-shaped buttons in one box —
 * "Submit for review" sat two rows above "Terminate" with nothing between
 * them, and the page never said which of the ten statuses the contract was
 * actually in. Position comes first now, then the moves, grouped by what they
 * do to the agreement and separated by a rule before the ones that end it.
 */
export function ContractLifecyclePanel({
  status,
  statusLabel,
  stamps,
  allowedActions,
  onRun,
  footer,
}: {
  status: string;
  statusLabel: string;
  stamps: ContractStamps;
  allowedActions: string[];
  onRun: (code: LifecycleActionCode) => void;
  /** Generation notices and anything else that qualifies the moves above. */
  footer?: React.ReactNode;
}) {
  const steps = lifecycleSteps(status, stamps);
  const items: TimelineItem[] = steps.map((step) => ({
    id: step.id,
    title: step.label,
    meta: stampLabel(step.at),
    tone: step.tone,
    current: step.state === "current",
    icon: step.state === "done" ? Check : undefined,
  }));

  const available = LIFECYCLE_ACTION_ORDER.filter(
    (code) => allowedActions.includes(code) && isLifecycleActionCode(code),
  );
  const byIntent = (intent: LifecycleIntent) =>
    available.filter((code) => LIFECYCLE_ACTIONS[code].intent === intent);
  const advance = byIntent("advance");
  const revise = byIntent("revise");
  const end = byIntent("end");

  return (
    <SurfaceCard>
      <PanelHeader title="Lifecycle" description={statusLabel} />
      <SurfaceCardContent className="grid gap-5">
        <Timeline items={items} />

        {advance.length > 0 || revise.length > 0 ? (
          <Group className="border-border/70 border-t pt-5">
            {advance.map((code, index) => (
              <ActionButton
                key={code}
                code={code}
                // Exactly one gold button in this region: the earliest forward
                // move. A second one would split the only signal the page has
                // for "this is the step".
                emphasis={index === 0 ? "primary" : "secondary"}
                onRun={onRun}
              />
            ))}
            {revise.map((code) => (
              <ActionButton key={code} code={code} emphasis="secondary" onRun={onRun} />
            ))}
          </Group>
        ) : null}

        {end.length > 0 ? (
          <Group title="End this version" className="border-border/70 border-t pt-5">
            {end.map((code) => (
              <ActionButton
                key={code}
                code={code}
                emphasis={code === "terminate" ? "destructive" : "secondary"}
                onRun={onRun}
              />
            ))}
          </Group>
        ) : null}

        {advance.length === 0 && revise.length === 0 && end.length === 0 ? (
          <p className="border-border/70 text-muted-foreground border-t pt-5 text-sm">
            No lifecycle moves are available from this status.
          </p>
        ) : null}

        {footer ? (
          <div className="border-border/70 grid gap-2 border-t pt-5">{footer}</div>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
