import { router } from "@inertiajs/react";
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
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type { TrainingAdminDetail } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

function localDateTime(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * Draft-only live session schedule editor. Posts to `training_session_save`
 * separately from the main content form.
 */
export function TrainingLiveSessionEditor({
  contentId,
  session,
  isDraft,
  canAuthor,
  errors,
}: {
  contentId: number;
  session: TrainingAdminDetail["liveSession"];
  isDraft: boolean;
  canAuthor: boolean;
  errors?: ValidationErrors;
}) {
  const formId = useId();
  const [startsAt, setStartsAt] = useState(localDateTime(session?.startsAt));
  const [timezone, setTimezone] = useState(session?.timezone ?? "America/New_York");
  const [durationMinutes, setDurationMinutes] = useState(
    String(session?.durationMinutes ?? 60),
  );
  const [capacity, setCapacity] = useState(
    session?.capacity != null ? String(session.capacity) : "",
  );
  const [meetingUrl, setMeetingUrl] = useState(session?.meetingUrl ?? "");
  const [registrationOpensAt, setRegistrationOpensAt] = useState(
    localDateTime(session?.registrationOpensAt),
  );
  const [registrationClosesAt, setRegistrationClosesAt] = useState(
    localDateTime(session?.registrationClosesAt),
  );
  const [submitting, setSubmitting] = useState(false);

  const readOnly = !isDraft || !canAuthor;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      return;
    }
    setSubmitting(true);
    router.post(
      routes.training_session_save(contentId),
      toFormData({
        startsAt,
        timezone,
        durationMinutes,
        capacity,
        meetingUrl,
        registrationOpensAt,
        registrationClosesAt,
      }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  return (
    <SurfaceCard>
      <PanelHeader
        divided
        title="Live session"
        description={
          isDraft
            ? "Save the schedule on this draft. Registration opens for learners after publish."
            : "Session schedule can only change on drafts. Duplicate as a new version to edit."
        }
      />
      <SurfaceCardContent>
        <form className="grid gap-5 sm:grid-cols-2" onSubmit={submit} noValidate>
          <FormField>
            <FormLabel htmlFor={`${formId}-starts`} required>
              Starts at
            </FormLabel>
            <Input
              id={`${formId}-starts`}
              type="datetime-local"
              value={startsAt}
              disabled={readOnly}
              onChange={(event) => setStartsAt(event.target.value)}
              {...fieldA11yProps("starts_at", errors)}
            />
            <FormFieldError message={firstFieldError(errors, "starts_at")} />
          </FormField>

          <FormField>
            <FormLabel htmlFor={`${formId}-timezone`} required>
              Timezone
            </FormLabel>
            <Input
              id={`${formId}-timezone`}
              value={timezone}
              disabled={readOnly}
              onChange={(event) => setTimezone(event.target.value)}
              placeholder="America/New_York"
              {...fieldA11yProps("timezone", errors, `${formId}-timezone-help`)}
            />
            <FormDescription id={`${formId}-timezone-help`}>
              IANA name shown to learners (for example America/New_York).
            </FormDescription>
            <FormFieldError message={firstFieldError(errors, "timezone")} />
          </FormField>

          <FormField>
            <FormLabel htmlFor={`${formId}-duration`} required>
              Duration (minutes)
            </FormLabel>
            <Input
              id={`${formId}-duration`}
              type="number"
              min={1}
              value={durationMinutes}
              disabled={readOnly}
              onChange={(event) => setDurationMinutes(event.target.value)}
              {...fieldA11yProps("duration_minutes", errors)}
            />
            <FormFieldError message={firstFieldError(errors, "duration_minutes")} />
          </FormField>

          <FormField>
            <FormLabel htmlFor={`${formId}-capacity`} optional>
              Capacity
            </FormLabel>
            <Input
              id={`${formId}-capacity`}
              type="number"
              min={1}
              value={capacity}
              disabled={readOnly}
              onChange={(event) => setCapacity(event.target.value)}
              {...fieldA11yProps("capacity", errors, `${formId}-capacity-help`)}
            />
            <FormDescription id={`${formId}-capacity-help`}>
              Leave empty for unlimited seats.
            </FormDescription>
            <FormFieldError message={firstFieldError(errors, "capacity")} />
          </FormField>

          <FormField className="sm:col-span-2">
            <FormLabel htmlFor={`${formId}-meeting`} optional>
              Meeting URL
            </FormLabel>
            <Input
              id={`${formId}-meeting`}
              type="url"
              inputMode="url"
              value={meetingUrl}
              disabled={readOnly}
              onChange={(event) => setMeetingUrl(event.target.value)}
              {...fieldA11yProps("meeting_url", errors)}
            />
            <FormFieldError message={firstFieldError(errors, "meeting_url")} />
          </FormField>

          <FormField>
            <FormLabel htmlFor={`${formId}-opens`} optional>
              Registration opens
            </FormLabel>
            <Input
              id={`${formId}-opens`}
              type="datetime-local"
              value={registrationOpensAt}
              disabled={readOnly}
              onChange={(event) => setRegistrationOpensAt(event.target.value)}
              {...fieldA11yProps("registration_opens_at", errors)}
            />
            <FormFieldError
              message={firstFieldError(errors, "registration_opens_at")}
            />
          </FormField>

          <FormField>
            <FormLabel htmlFor={`${formId}-closes`} optional>
              Registration closes
            </FormLabel>
            <Input
              id={`${formId}-closes`}
              type="datetime-local"
              value={registrationClosesAt}
              disabled={readOnly}
              onChange={(event) => setRegistrationClosesAt(event.target.value)}
              {...fieldA11yProps("registration_closes_at", errors)}
            />
            <FormFieldError
              message={firstFieldError(errors, "registration_closes_at")}
            />
          </FormField>

          <FormFieldError message={firstFieldError(errors, "content")} />
          <FormFieldError message={firstFieldError(errors, "session")} />

          {!readOnly ? (
            <div className="sm:col-span-2">
              <FormActionBar status="Session changes save separately from the content draft above.">
                <Button
                  type="submit"
                  disabled={submitting}
                  aria-busy={submitting || undefined}
                >
                  {submitting ? "Saving session…" : "Save session"}
                </Button>
              </FormActionBar>
            </div>
          ) : null}
        </form>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
