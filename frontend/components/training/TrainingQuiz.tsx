import { router } from "@inertiajs/react";
import { GraduationCap } from "lucide-react";
import { useMemo, useState } from "react";

import {
  EmptyState,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { TrainingQuizPayload } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

export function TrainingQuiz({
  contentId,
  quiz,
  errors,
}: {
  contentId: number;
  quiz: TrainingQuizPayload;
  errors?: ValidationErrors;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const allAnswered = useMemo(
    () => quiz.questions.every((question) => Boolean(answers[String(question.id)])),
    [answers, quiz.questions],
  );
  const formError =
    errors?.form?.[0] ?? errors?.fields?.answers?.[0] ?? errors?.fields?.attempts?.[0];

  function submit() {
    setPending(true);
    router.post(
      routes.training_quiz_submit(contentId),
      { answers },
      {
        preserveScroll: true,
        onFinish: () => setPending(false),
      },
    );
  }

  if (quiz.questions.length === 0) {
    return (
      <SurfaceCard>
        <EmptyState
          icon={GraduationCap}
          title="Quiz not ready"
          description="Questions have not been published for this quiz yet."
        />
      </SurfaceCard>
    );
  }

  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-5">
        <div className="grid gap-1">
          <h2 className="text-sm font-semibold">Quiz</h2>
          <p className="text-muted-foreground text-sm">
            Pass threshold {quiz.passThresholdPercent}%.
            {quiz.attemptsRemaining !== null
              ? ` ${quiz.attemptsRemaining} attempt(s) remaining.`
              : " Unlimited attempts."}
          </p>
          {quiz.latestAttempt ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <StatusBadge
                status={{
                  label: quiz.latestAttempt.passed ? "Passed" : "Not passed",
                  tone: quiz.latestAttempt.passed ? "success" : "warning",
                }}
              />
              <span className="text-muted-foreground text-xs tabular-nums">
                Latest score {quiz.latestAttempt.scorePercent}%
              </span>
            </div>
          ) : null}
        </div>

        {formError ? (
          <p className="text-destructive text-sm" role="alert">
            {formError}
          </p>
        ) : null}

        <fieldset className="grid gap-6" disabled={!quiz.canAttempt || pending}>
          <legend className="sr-only">Quiz questions</legend>
          {quiz.questions.map((question, index) => (
            <fieldset key={question.id} className="grid gap-3">
              <legend className="text-sm font-medium">
                {index + 1}. {question.prompt}
              </legend>
              <div
                className="grid gap-2"
                role="radiogroup"
                aria-label={`Question ${index + 1}`}
              >
                {question.choices.map((choice) => {
                  const inputId = `q-${question.id}-${choice.id}`;
                  return (
                    <label
                      key={choice.id}
                      htmlFor={inputId}
                      className="flex cursor-pointer items-center gap-2 text-sm"
                    >
                      <input
                        id={inputId}
                        type="radio"
                        name={`question-${question.id}`}
                        value={choice.id}
                        checked={answers[String(question.id)] === choice.id}
                        onChange={() =>
                          setAnswers((current) => ({
                            ...current,
                            [String(question.id)]: choice.id,
                          }))
                        }
                        className="accent-primary size-4"
                      />
                      {choice.label}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}
        </fieldset>

        <Button
          type="button"
          disabled={!quiz.canAttempt || !allAnswered || pending}
          onClick={submit}
        >
          {pending ? "Submitting…" : "Submit answers"}
        </Button>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
