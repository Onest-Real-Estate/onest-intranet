import { router } from "@inertiajs/react";
import { Plus, Trash2 } from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import {
  FormActionBar,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type { TrainingAdminDetail, TrainingQuizChoice } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

const FEEDBACK_OPTIONS = [
  { value: "score_only", label: "Score only" },
  { value: "review", label: "Score and review" },
  { value: "none", label: "No feedback" },
] as const;

type DraftChoice = TrainingQuizChoice;
type DraftQuestion = {
  key: string;
  prompt: string;
  choices: DraftChoice[];
  correctChoiceIds: string[];
};

function newChoiceId(): string {
  return `c_${Math.random().toString(36).slice(2, 10)}`;
}

function newQuestionKey(): string {
  return `q_${Math.random().toString(36).slice(2, 10)}`;
}

function emptyQuestion(): DraftQuestion {
  const a = newChoiceId();
  const b = newChoiceId();
  return {
    key: newQuestionKey(),
    prompt: "",
    choices: [
      { id: a, label: "" },
      { id: b, label: "" },
    ],
    correctChoiceIds: [a],
  };
}

function initialQuestions(
  quiz: NonNullable<TrainingAdminDetail["quiz"]> | null | undefined,
): DraftQuestion[] {
  if (!quiz?.questions.length) {
    return [emptyQuestion()];
  }
  return quiz.questions.map((question) => ({
    key: `existing_${question.id}`,
    prompt: question.prompt,
    choices: question.choices.map((choice) => ({ ...choice })),
    correctChoiceIds: [...question.correctChoiceIds],
  }));
}

/**
 * Draft-only quiz definition editor. Posts to `training_quiz_save` separately
 * from the main content form so authors can configure questions after the
 * content type is saved as quiz.
 */
export function TrainingQuizEditor({
  contentId,
  quiz,
  isDraft,
  canAuthor,
  errors,
}: {
  contentId: number;
  quiz: TrainingAdminDetail["quiz"];
  isDraft: boolean;
  canAuthor: boolean;
  errors?: ValidationErrors;
}) {
  const formId = useId();
  const [passThresholdPercent, setPassThresholdPercent] = useState(
    String(quiz?.passThresholdPercent ?? 80),
  );
  const [maxAttempts, setMaxAttempts] = useState(
    quiz?.maxAttempts != null ? String(quiz.maxAttempts) : "",
  );
  const [feedbackPolicy, setFeedbackPolicy] = useState(
    quiz?.feedbackPolicy ?? "score_only",
  );
  const [questions, setQuestions] = useState<DraftQuestion[]>(() =>
    initialQuestions(quiz),
  );
  const [submitting, setSubmitting] = useState(false);

  const readOnly = !isDraft || !canAuthor;

  function updateQuestion(key: string, patch: Partial<DraftQuestion>) {
    setQuestions((rows) =>
      rows.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      return;
    }
    setSubmitting(true);
    const payload = questions.map((question, index) => ({
      prompt: question.prompt,
      choices: question.choices,
      correctChoiceIds: question.correctChoiceIds,
      sortOrder: index,
    }));
    router.post(
      routes.training_quiz_save(contentId),
      toFormData({
        passThresholdPercent,
        maxAttempts,
        feedbackPolicy,
        questions: JSON.stringify(payload),
      }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  return (
    <SurfaceCard>
      <PanelHeader
        divided
        title="Quiz"
        description={
          isDraft
            ? "Save questions on this draft. Learners only see the quiz after you publish."
            : "Quiz questions can only change on drafts. Duplicate as a new version to edit."
        }
      />
      <SurfaceCardContent>
        <form className="grid gap-6" onSubmit={submit} noValidate>
          <div className="grid gap-5 sm:grid-cols-3">
            <FormField>
              <FormLabel htmlFor={`${formId}-threshold`} required>
                Pass threshold %
              </FormLabel>
              <Input
                id={`${formId}-threshold`}
                type="number"
                min={0}
                max={100}
                value={passThresholdPercent}
                disabled={readOnly}
                onChange={(event) => setPassThresholdPercent(event.target.value)}
                {...fieldA11yProps("pass_threshold_percent", errors)}
              />
              <FormFieldError
                message={firstFieldError(errors, "pass_threshold_percent")}
              />
            </FormField>

            <FormField>
              <FormLabel htmlFor={`${formId}-attempts`} optional>
                Max attempts
              </FormLabel>
              <Input
                id={`${formId}-attempts`}
                type="number"
                min={1}
                value={maxAttempts}
                disabled={readOnly}
                onChange={(event) => setMaxAttempts(event.target.value)}
                {...fieldA11yProps("max_attempts", errors, `${formId}-attempts-help`)}
              />
              <FormDescription id={`${formId}-attempts-help`}>
                Leave empty for unlimited attempts.
              </FormDescription>
              <FormFieldError message={firstFieldError(errors, "max_attempts")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor={`${formId}-feedback`} required>
                Feedback policy
              </FormLabel>
              <Select
                value={feedbackPolicy}
                disabled={readOnly}
                onValueChange={setFeedbackPolicy}
              >
                <SelectTrigger id={`${formId}-feedback`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FEEDBACK_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormFieldError message={firstFieldError(errors, "feedback_policy")} />
            </FormField>
          </div>

          <FormFieldError message={firstFieldError(errors, "questions")} />
          <FormFieldError message={firstFieldError(errors, "content")} />
          <FormFieldError message={firstFieldError(errors, "quiz")} />

          <div className="grid gap-4">
            {questions.map((question, questionIndex) => (
              <fieldset
                key={question.key}
                className="grid gap-4 rounded-lg border p-4"
                disabled={readOnly}
              >
                <legend className="px-1 text-sm font-semibold">
                  Question {questionIndex + 1}
                </legend>
                <FormField>
                  <FormLabel htmlFor={`${formId}-q-${question.key}`} required>
                    Prompt
                  </FormLabel>
                  <Textarea
                    id={`${formId}-q-${question.key}`}
                    rows={2}
                    value={question.prompt}
                    onChange={(event) =>
                      updateQuestion(question.key, { prompt: event.target.value })
                    }
                  />
                </FormField>

                <div className="grid gap-3">
                  <p className="text-sm font-medium">Choices</p>
                  {question.choices.map((choice) => {
                    const correct = question.correctChoiceIds.includes(choice.id);
                    return (
                      <div
                        key={choice.id}
                        className="flex flex-wrap items-center gap-2"
                      >
                        <input
                          type="radio"
                          name={`${formId}-correct-${question.key}`}
                          checked={correct}
                          aria-label={`Mark choice as correct for question ${questionIndex + 1}`}
                          onChange={() =>
                            updateQuestion(question.key, {
                              correctChoiceIds: [choice.id],
                            })
                          }
                          className="accent-primary size-4"
                        />
                        <Input
                          className="min-w-0 flex-1"
                          value={choice.label}
                          placeholder="Choice text"
                          onChange={(event) =>
                            updateQuestion(question.key, {
                              choices: question.choices.map((row) =>
                                row.id === choice.id
                                  ? { ...row, label: event.target.value }
                                  : row,
                              ),
                            })
                          }
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={question.choices.length <= 2}
                          onClick={() => {
                            const nextChoices = question.choices.filter(
                              (row) => row.id !== choice.id,
                            );
                            const nextCorrect = question.correctChoiceIds.includes(
                              choice.id,
                            )
                              ? [nextChoices[0]?.id].filter(Boolean)
                              : question.correctChoiceIds;
                            updateQuestion(question.key, {
                              choices: nextChoices,
                              correctChoiceIds: nextCorrect as string[],
                            });
                          }}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                          <span className="sr-only">Remove choice</span>
                        </Button>
                      </div>
                    );
                  })}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-fit"
                    onClick={() =>
                      updateQuestion(question.key, {
                        choices: [
                          ...question.choices,
                          { id: newChoiceId(), label: "" },
                        ],
                      })
                    }
                  >
                    <Plus className="size-3.5" aria-hidden />
                    Add choice
                  </Button>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={questions.length <= 1}
                    onClick={() =>
                      setQuestions((rows) =>
                        rows.filter((row) => row.key !== question.key),
                      )
                    }
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                    Remove question
                  </Button>
                </div>
              </fieldset>
            ))}

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              disabled={readOnly}
              onClick={() => setQuestions((rows) => [...rows, emptyQuestion()])}
            >
              <Plus className="size-3.5" aria-hidden />
              Add question
            </Button>
          </div>

          {!readOnly ? (
            <FormActionBar status="Quiz changes save separately from the content draft above.">
              <Button
                type="submit"
                disabled={submitting}
                aria-busy={submitting || undefined}
              >
                {submitting ? "Saving quiz…" : "Save quiz"}
              </Button>
            </FormActionBar>
          ) : null}
        </form>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
