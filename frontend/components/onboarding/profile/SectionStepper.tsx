import { Check, Circle, CircleDashed, ClipboardCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import type { OnboardingProfileSection, OnboardingProfileSectionCode } from "@/types";

const STATUS_WORDS = {
  complete: "complete",
  in_progress: "in progress",
  not_started: "not started",
} as const;

function StepMark({
  section,
  active,
}: {
  section: OnboardingProfileSection;
  active: boolean;
}) {
  if (section.status === "complete") {
    return (
      <Check className="text-success size-3.5 shrink-0" strokeWidth={2.5} aria-hidden />
    );
  }
  if (section.code === "review") {
    return (
      <ClipboardCheck
        className={cn(
          "size-3.5 shrink-0",
          active ? "text-primary" : "text-muted-foreground",
        )}
        aria-hidden
      />
    );
  }
  if (section.status === "in_progress") {
    return <CircleDashed className="text-warning-ink size-3.5 shrink-0" aria-hidden />;
  }
  return (
    <Circle
      className={cn(
        "size-3.5 shrink-0",
        active ? "text-primary" : "text-muted-foreground",
      )}
      aria-hidden
    />
  );
}

/**
 * Four short sections, each a button that visits its own URL, so refresh and
 * the browser's Back button land where the agent expects. Status comes from
 * the server; the stepper never infers progress.
 */
export function SectionStepper({
  sections,
  current,
  onNavigate,
}: {
  sections: OnboardingProfileSection[];
  current: OnboardingProfileSectionCode;
  onNavigate: (code: OnboardingProfileSectionCode) => void;
}) {
  return (
    <nav aria-label="Profile setup steps">
      <ol className="grid grid-cols-4 gap-1.5 sm:gap-3">
        {sections.map((section, index) => {
          const active = section.code === current;
          const status = section.status ? STATUS_WORDS[section.status] : null;
          return (
            <li key={section.code} className="min-w-0">
              <button
                type="button"
                onClick={() => onNavigate(section.code)}
                aria-current={active ? "step" : undefined}
                className="focus-visible:ring-ring/50 hover:bg-muted/50 grid w-full min-w-0 gap-2 rounded-md p-1.5 text-left outline-none transition-colors duration-(--motion-fast) focus-visible:ring-3"
              >
                <span
                  aria-hidden
                  className={cn(
                    "h-1 rounded-full transition-colors duration-(--motion-fast)",
                    active
                      ? "bg-brand-gold"
                      : section.status === "complete"
                        ? "bg-primary"
                        : "bg-muted",
                  )}
                />
                <span className="flex min-w-0 items-center gap-1.5">
                  <StepMark section={section} active={active} />
                  <span
                    className={cn(
                      "truncate text-xs font-semibold",
                      active
                        ? "text-foreground"
                        : "text-muted-foreground max-sm:sr-only",
                    )}
                  >
                    {section.label}
                  </span>
                  <span className="sr-only">
                    , step {index + 1} of {sections.length}
                    {status ? `, ${status}` : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
