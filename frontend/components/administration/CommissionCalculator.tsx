import { Calculator, ChevronRight, LoaderCircle, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { AgentContractCommercialPreview } from "@/types";

/**
 * What a deal actually pays, at a gross the reader chooses.
 *
 * Every figure here is calculated **server-side** by the contract engine and
 * echoed back — this component never multiplies anything. That matters twice
 * over: the split rules live in one place, and a broker quoting a number to an
 * agent is quoting the same number the contract will pay.
 */

/** Money arrives as a decimal string and must stay one — floats lose cents. */
function money(value: string | null | undefined, currency: string): string {
  if (value == null || value === "") return "—";
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return parsed.toLocaleString(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2,
  });
}

type LoadState = "idle" | "loading" | "error";

export function CommissionCalculator({
  contractPublicId,
  initial,
}: {
  contractPublicId: string;
  /** The server's own preview, already on the page. The panel opens with it. */
  initial: AgentContractCommercialPreview;
}) {
  const inputId = useId();
  const [preview, setPreview] = useState(initial);
  const [gross, setGross] = useState(initial.breakdown?.grossCommission ?? "10000");
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  // Only the newest request may write. Out-of-order replies would otherwise
  // show a figure for a gross the reader has already typed past.
  const requestRef = useRef(0);

  const load = useCallback(
    (amount: string) => {
      const trimmed = amount.trim();
      if (trimmed === "") {
        return;
      }
      const request = ++requestRef.current;
      setState("loading");
      void fetch(
        `${routes.agent_contract_validate(contractPublicId)}?gross_commission=${encodeURIComponent(trimmed)}`,
        { headers: { Accept: "application/json" }, credentials: "same-origin" },
      )
        .then(async (response) => {
          const payload = await response.json();
          if (request !== requestRef.current) return;
          if (!response.ok) {
            setState("error");
            setMessage(
              typeof payload?.error === "string"
                ? payload.error
                : "That gross commission could not be calculated.",
            );
            return;
          }
          setPreview(payload as AgentContractCommercialPreview);
          setState("idle");
          setMessage(null);
        })
        .catch(() => {
          if (request !== requestRef.current) return;
          setState("error");
          setMessage("The calculation could not be reached. Check your connection.");
        });
    },
    [contractPublicId],
  );

  // Debounced so a typed figure settles before it is priced, and so holding a
  // key down does not queue a request per keystroke.
  useEffect(() => {
    if (gross === (initial.breakdown?.grossCommission ?? "10000")) {
      return;
    }
    const handle = window.setTimeout(() => load(gross), 400);
    return () => window.clearTimeout(handle);
  }, [gross, initial.breakdown?.grossCommission, load]);

  const breakdown = preview.breakdown;
  const currency = breakdown?.currency ?? "USD";
  const deductions = [
    { label: "Transaction fee", value: breakdown?.transactionFee },
    { label: "Mentor", value: breakdown?.mentorAmount },
    { label: "Referral", value: breakdown?.referralAmount },
  ].filter((row) => row.value != null && row.value !== "" && row.value !== "0.00");

  return (
    <SurfaceCard>
      <PanelHeader
        title="What this pays"
        description="Enter a gross commission to price this agreement. Calculated by the contract engine, not in the browser."
      />
      <SurfaceCardContent className="grid gap-4">
        <form
          className="grid gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            load(gross);
          }}
        >
          <Label htmlFor={inputId}>Gross commission</Label>
          <div className="relative">
            <Input
              id={inputId}
              inputMode="decimal"
              value={gross}
              onChange={(event) => setGross(event.target.value)}
              aria-describedby={message ? `${inputId}-message` : undefined}
              aria-invalid={state === "error" || undefined}
              className="pr-9 tabular-nums"
            />
            {state === "loading" ? (
              <LoaderCircle
                className="text-muted-foreground absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin"
                aria-hidden
              />
            ) : (
              <Calculator
                className="text-muted-foreground absolute top-1/2 right-3 size-4 -translate-y-1/2"
                aria-hidden
              />
            )}
          </div>
        </form>

        {message ? (
          <p
            id={`${inputId}-message`}
            role="alert"
            className="text-destructive flex items-start gap-1.5 text-sm"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {message}
          </p>
        ) : null}

        {breakdown ? (
          <div
            // The figures dim while a newer one is in flight, so a reader never
            // mistakes a stale number for the answer to what they just typed.
            className={cn(
              "grid gap-4 transition-opacity duration-(--motion-fast)",
              state === "loading" && "opacity-60",
            )}
            aria-busy={state === "loading" || undefined}
          >
            <div className="grid gap-2 sm:grid-cols-2">
              <Figure
                label="Agent net"
                value={money(breakdown.agentNet, currency)}
                emphasis
              />
              <Figure label="Office net" value={money(breakdown.officeNet, currency)} />
            </div>

            {deductions.length > 0 ? (
              <dl className="grid gap-1.5 border-t pt-3 text-sm">
                {deductions.map((row) => (
                  <div key={row.label} className="flex justify-between gap-3">
                    <dt className="text-muted-foreground">{row.label}</dt>
                    <dd className="tabular-nums">{money(row.value, currency)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            {breakdown.explanation.length > 0 ? (
              <details className="group border-t pt-3">
                <summary className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md text-sm font-medium outline-none focus-visible:ring-2">
                  How this was worked out
                  <ChevronRight
                    aria-hidden
                    className="size-4 transition-transform duration-(--motion-fast) group-open:rotate-90"
                  />
                </summary>
                {/* The engine's own words, in its own order. */}
                <ol className="text-muted-foreground mt-2 grid gap-1 text-sm leading-5">
                  {breakdown.explanation.map((step, index) => (
                    <li key={step} className="flex gap-2">
                      <span className="text-micro mt-0.5 tabular-nums opacity-60">
                        {index + 1}
                      </span>
                      <span className="min-w-0">{step}</span>
                    </li>
                  ))}
                </ol>
              </details>
            ) : null}

            <p className="text-muted-foreground text-micro">
              Rule {breakdown.ruleVersion}
            </p>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            This agreement has no commercial terms to price yet.
          </p>
        )}

        {preview.summaryLines.length > 0 ? (
          <ul className="text-muted-foreground grid gap-1 border-t pt-3 text-sm">
            {preview.summaryLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function Figure({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-0.5 rounded-lg border px-3 py-2.5",
        emphasis ? "border-chip-primary-edge bg-chip-primary" : "bg-muted/40",
      )}
    >
      <span className="text-muted-foreground text-xs font-semibold">{label}</span>
      <span
        className={cn(
          "text-lg font-bold tracking-[-0.02em] tabular-nums",
          emphasis && "text-primary",
        )}
      >
        {value}
      </span>
    </div>
  );
}
