import { TriangleAlert } from "lucide-react";

import { Callout } from "@/components/design-system";
import { cn } from "@/lib/utils";

/**
 * Merge keys that do not survive naive title-casing.
 *
 * Everything else reads correctly once the underscores are gone, so this stays
 * a short list of genuine exceptions rather than a translation table nobody
 * maintains.
 */
const LABEL_OVERRIDES: Record<string, string> = {
  agent_split_percent: "Agent split",
  office_split_percent: "Office split",
  transaction_fee_amount: "Transaction fee (amount)",
  transaction_fee_percent: "Transaction fee (percent)",
  annual_cap_amount: "Annual cap",
  mentor_percent: "Mentor percent",
  mentor_fixed_amount: "Mentor fixed amount",
  mentor_cap_amount: "Mentor cap",
  referral_percent: "Referral percent",
  referral_fixed_amount: "Referral fixed amount",
  referral_cap_amount: "Referral cap",
  effective_on: "Effective on",
  expires_on: "Expires on",
  office_name: "Office",
  agent_name: "Agent",
  agent_email: "Agent email",
  brokerage_name: "Brokerage",
  license_state: "License state",
};

export function humanizeMergeKey(key: string): string {
  const override = LABEL_OVERRIDES[key];
  if (override) return override;
  const words = key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
  if (!words) return key;
  return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}

/**
 * The values that will be merged into the agreement PDF.
 *
 * This used to be `Object.entries(mergeValues)` printed with the raw keys as
 * the labels — `agent_split_percent` as a term, on the last screen anyone sees
 * before a legal document is issued and frozen. Two changes carry the weight:
 * the label is now the human name with the merge key kept underneath for
 * whoever maintains the template, and an empty value is called out rather than
 * rendered as a quiet dash, because an empty merge value is a blank line in
 * the signed agreement.
 */
export function MergeValuePreview({ values }: { values: Record<string, string> }) {
  const rows = Object.entries(values).sort(([a], [b]) =>
    humanizeMergeKey(a).localeCompare(humanizeMergeKey(b)),
  );
  const empty = rows.filter(([, value]) => !value?.trim());

  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        This template declares no merge fields.
      </p>
    );
  }

  return (
    <div className="grid gap-4">
      {empty.length > 0 ? (
        <Callout
          tone="warning"
          title={`${empty.length} field${empty.length === 1 ? "" : "s"} will render blank`}
        >
          The agreement is issued with these left empty. Fill them in above, or confirm
          the template expects a blank.
        </Callout>
      ) : null}

      <dl className="border-border/60 grid divide-y divide-border/60 overflow-hidden rounded-lg border">
        {rows.map(([key, value]) => {
          const blank = !value?.trim();
          return (
            <div
              key={key}
              className={cn(
                "grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] sm:items-baseline sm:gap-4",
                blank && "bg-chip-warning/40",
              )}
            >
              <dt className="grid gap-0.5">
                <span className="text-sm font-medium">{humanizeMergeKey(key)}</span>
                <span className="text-muted-foreground font-mono text-xs">{key}</span>
              </dt>
              <dd
                className={cn(
                  "min-w-0 text-sm break-words",
                  blank && "text-warning-ink flex items-center gap-1.5",
                )}
              >
                {blank ? (
                  <>
                    <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
                    Empty
                  </>
                ) : (
                  value
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
