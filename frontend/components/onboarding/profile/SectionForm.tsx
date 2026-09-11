import { router } from "@inertiajs/react";
import { ArrowLeft, ArrowRight, CheckCircle2, LoaderCircle } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { FormActionBar, FormErrorSummary } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { hasValidationErrors } from "@/lib/validation";
import type { ValidationErrors } from "@/types/design-system";

const FOCUSABLE =
  "input:not([type='hidden']),select,textarea,button,[tabindex]:not([tabindex='-1'])";

/** Focus the first control marked invalid, descending into groups. */
export function focusFirstInvalid(root: HTMLElement | null): boolean {
  if (!root) {
    return false;
  }
  for (const element of root.querySelectorAll<HTMLElement>('[aria-invalid="true"]')) {
    const target = element.matches(FOCUSABLE)
      ? element
      : element.querySelector<HTMLElement>(FOCUSABLE);
    if (target && !target.hasAttribute("disabled")) {
      target.focus();
      return true;
    }
  }
  return false;
}

/**
 * One section's form. It posts through the Inertia router (never a native
 * submit), guards against a second submit while one is in flight, and after a
 * server response with errors moves focus to the first invalid control — or to
 * the summary when the problem is not tied to a field.
 */
export function SectionForm({
  action,
  csrfToken,
  tokens,
  validation,
  labels,
  summary,
  dirty,
  onDirtyChange,
  onDraft,
  onBack,
  submitLabel,
  submittingLabel,
  children,
}: {
  action: string;
  csrfToken: string;
  tokens: Record<string, string>;
  validation: ValidationErrors;
  labels: Record<string, string>;
  /** Replaces the default linked error summary, e.g. on review. */
  summary?: ReactNode;
  dirty: boolean;
  onDirtyChange: (dirty: boolean) => void;
  /** Receives the unsaved field values whenever they change. */
  onDraft?: (values: Record<string, string[]>) => void;
  onBack?: () => void;
  submitLabel: string;
  submittingLabel: string;
  children: ReactNode;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const lastDraft = useRef("");
  const [submitting, setSubmitting] = useState(false);

  // Keyed on the payload itself so a second failed save focuses again.
  useEffect(() => {
    if (!hasValidationErrors(validation)) {
      return;
    }
    if (!focusFirstInvalid(formRef.current)) {
      summaryRef.current?.focus();
    }
  }, [validation]);

  function captureDraft() {
    const form = formRef.current;
    if (!form || !onDraft) {
      return;
    }
    const values: Record<string, string[]> = {};
    for (const [name, value] of new FormData(form)) {
      if (
        typeof value !== "string" ||
        name === "csrfmiddlewaretoken" ||
        name in tokens
      ) {
        continue;
      }
      values[name] = [...(values[name] ?? []), value];
    }
    const serialized = JSON.stringify(values);
    if (serialized !== lastDraft.current) {
      lastDraft.current = serialized;
      onDraft(values);
    }
  }

  // Selects, the date picker, and language chips change without an input
  // event, so unsaved values are also read back after every render.
  useEffect(() => {
    if (dirty) {
      captureDraft();
    }
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    router.post(action, new FormData(event.currentTarget), {
      preserveScroll: true,
      onSuccess: () => onDirtyChange(false),
      onFinish: () => {
        inFlight.current = false;
        setSubmitting(false);
      },
    });
  }

  return (
    <form
      ref={formRef}
      method="post"
      action={action}
      noValidate
      onSubmit={submit}
      onInput={() => {
        onDirtyChange(true);
        captureDraft();
      }}
      className="grid gap-6"
      aria-busy={submitting || undefined}
    >
      <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
      {Object.entries(tokens).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}

      <div ref={summaryRef} tabIndex={-1} className="outline-none empty:hidden">
        {summary ?? <FormErrorSummary errors={validation} labels={labels} />}
      </div>

      {children}

      <FormActionBar
        status={
          submitting ? (
            "Saving…"
          ) : dirty ? (
            <span className="flex items-center gap-2">
              <span className="bg-warning size-2 rounded-full" aria-hidden />
              Unsaved changes in this section
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <CheckCircle2 className="text-success size-4" aria-hidden />
              Progress is saved each time you continue
            </span>
          )
        }
      >
        {onBack ? (
          <Button
            type="button"
            variant="outline"
            onClick={onBack}
            disabled={submitting}
          >
            <ArrowLeft aria-hidden />
            Back
          </Button>
        ) : null}
        <Button type="submit" disabled={submitting} aria-busy={submitting || undefined}>
          {submitting ? (
            <>
              <LoaderCircle className="animate-spin" aria-hidden />
              {submittingLabel}
            </>
          ) : (
            <>
              {submitLabel}
              <ArrowRight aria-hidden />
            </>
          )}
        </Button>
      </FormActionBar>
    </form>
  );
}
