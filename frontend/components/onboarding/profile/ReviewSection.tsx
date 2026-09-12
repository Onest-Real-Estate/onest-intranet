import { PencilLine } from "lucide-react";

import { Callout, FormFieldError } from "@/components/design-system";
import { OwnerBadge, policyFor } from "@/components/onboarding/profile/field-ownership";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { firstFieldError } from "@/lib/validation";
import type { OnboardingEditableSectionCode, OnboardingPageProps } from "@/types";

export const CONFIRMATION_FIELD = "confirm_review";

interface ProblemItem {
  field: string;
  label: string;
  message: string;
  section: OnboardingEditableSectionCode;
}

/**
 * Everything the review needs to send the agent back to: required values still
 * missing on the server, plus anything the finish request rejected against
 * today's rules (an office retired while the dialog was open, say).
 */
export function reviewProblems(page: OnboardingPageProps): ProblemItem[] {
  const { review, fields } = page.profileFlow;
  const problems = new Map<string, ProblemItem>();
  for (const item of review.missing) {
    problems.set(item.field, {
      field: item.field,
      label: item.label,
      message: "Required",
      section: item.section,
    });
  }
  for (const [field, messages] of Object.entries(page.validation.fields)) {
    if (field === CONFIRMATION_FIELD || messages.length === 0) {
      continue;
    }
    if (field === "confirm_office") {
      problems.set(field, {
        field,
        label: "Office confirmation",
        message: messages[0],
        section: "credentials",
      });
      continue;
    }
    const policy = policyFor(fields, field);
    problems.set(field, {
      field,
      label: policy.label,
      message: messages[0],
      section: policy.section,
    });
  }
  return [...problems.values()];
}

export function ReviewProblems({
  page,
  onNavigate,
}: {
  page: OnboardingPageProps;
  onNavigate: (section: OnboardingEditableSectionCode) => void;
}) {
  const problems = reviewProblems(page);
  if (problems.length === 0) {
    return page.validation.form.length > 0 ? (
      <Callout tone="destructive" role="alert" title="We could not finish yet">
        {page.validation.form.join(" ")}
      </Callout>
    ) : null;
  }
  return (
    <Callout tone="warning" role="alert" title="A few things need attention first">
      <ul className="mt-1 grid gap-1">
        {problems.map((problem) => (
          <li key={problem.field}>
            <button
              type="button"
              onClick={() => onNavigate(problem.section)}
              className="decoration-warning-ink/40 hover:decoration-warning-ink text-left underline underline-offset-2"
            >
              <span className="font-medium">{problem.label}:</span> {problem.message}
            </button>
          </li>
        ))}
      </ul>
      {page.validation.form.length > 0 ? (
        <p className="mt-2">{page.validation.form.join(" ")}</p>
      ) : null}
    </Callout>
  );
}

export function ReviewSection({
  page,
  confirmed,
  onConfirmedChange,
  onNavigate,
}: {
  page: OnboardingPageProps;
  confirmed: boolean;
  onConfirmedChange: (confirmed: boolean) => void;
  onNavigate: (section: OnboardingEditableSectionCode) => void;
}) {
  const { review } = page.profileFlow;
  const confirmationError = firstFieldError(page.validation, CONFIRMATION_FIELD);
  const invalid = new Set(Object.keys(page.validation.fields));

  return (
    <div className="grid gap-6">
      {review.ready && reviewProblems(page).length === 0 ? (
        <Callout tone="success" title="Everything required is here">
          These are the exact values we saved. Edit any section before you confirm.
        </Callout>
      ) : null}

      {review.groups.map((group) => (
        <section
          key={group.section}
          aria-labelledby={`review-${group.section}-heading`}
          className="grid gap-2"
        >
          <div className="flex items-center justify-between gap-3">
            <h3
              id={`review-${group.section}-heading`}
              className="text-sm font-semibold"
            >
              {group.label}
            </h3>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onNavigate(group.section)}
              aria-label={`Edit ${group.label}`}
            >
              <PencilLine aria-hidden />
              Edit
            </Button>
          </div>
          <dl className="divide-border/70 grid divide-y rounded-lg border">
            {group.rows.map((row) => (
              <div
                key={row.field}
                className={cn(
                  "grid gap-0.5 px-4 py-2.5 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4",
                  invalid.has(row.field) && "bg-chip-destructive",
                )}
              >
                <dt className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
                  {row.label}
                  {row.owner === "agent" ? null : <OwnerBadge owner={row.owner} />}
                </dt>
                <dd className="min-w-0 text-sm font-medium break-words whitespace-pre-line">
                  {row.display ? (
                    row.display
                  ) : row.required ? (
                    <span className="text-destructive font-semibold">Missing</span>
                  ) : (
                    <span className="text-muted-foreground font-normal">
                      Not provided
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}

      <div className="grid gap-2">
        <div
          id={CONFIRMATION_FIELD}
          className={cn(
            "flex items-start gap-3 rounded-lg border p-4",
            confirmationError ? "border-destructive/60" : "border-border",
          )}
        >
          <input
            type="hidden"
            name={CONFIRMATION_FIELD}
            value={confirmed ? "true" : "false"}
          />
          <Checkbox
            id="confirm_review_input"
            checked={confirmed}
            onCheckedChange={(next) => onConfirmedChange(next === true)}
            aria-invalid={Boolean(confirmationError) || undefined}
            aria-describedby={confirmationError ? "confirm_review_error" : undefined}
            className="mt-0.5"
          />
          <label
            htmlFor="confirm_review_input"
            className="grid cursor-pointer gap-1 text-sm"
          >
            <span className="font-medium">
              I confirm these details are accurate and belong to me.
            </span>
            <span className="text-muted-foreground">
              Optional details can still be updated from your profile later.
            </span>
          </label>
        </div>
        <FormFieldError id="confirm_review_error" message={confirmationError} />
      </div>
    </div>
  );
}
