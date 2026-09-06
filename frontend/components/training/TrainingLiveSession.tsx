import { router } from "@inertiajs/react";
import { useState } from "react";

import {
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { TrainingSessionPayload } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

function formatWhen(iso: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone,
    }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleString();
  }
}

export function TrainingLiveSession({
  contentId,
  session,
  errors,
}: {
  contentId: number;
  session: TrainingSessionPayload;
  errors?: ValidationErrors;
}) {
  const [pending, setPending] = useState(false);
  const registration = session.registration;
  const isRegistered =
    registration?.status === "registered" || registration?.status === "attended";
  const formError =
    errors?.form?.[0] ??
    errors?.fields?.registration?.[0] ??
    errors?.fields?.capacity?.[0];

  function post(action: "register" | "cancel") {
    setPending(true);
    router.post(
      routes.training_session_register(contentId),
      { action },
      {
        preserveScroll: true,
        onFinish: () => setPending(false),
      },
    );
  }

  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-4">
        <div className="grid gap-1">
          <h2 className="text-sm font-semibold">Live session</h2>
          <p className="text-sm">
            {formatWhen(session.startsAt, session.timezone)} ({session.timezone})
          </p>
          <p className="text-muted-foreground text-sm">
            {session.durationMinutes} minutes
            {session.capacity !== null
              ? ` · ${session.seatsRemaining ?? 0} of ${session.capacity} seats left`
              : " · Open capacity"}
          </p>
          {registration ? (
            <div className="pt-1">
              <StatusBadge
                status={{
                  label: registration.status.replace("_", " "),
                  tone:
                    registration.status === "attended"
                      ? "success"
                      : registration.status === "cancelled"
                        ? "neutral"
                        : "info",
                }}
              />
            </div>
          ) : null}
        </div>

        {formError ? (
          <p className="text-destructive text-sm" role="alert">
            {formError}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {isRegistered ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={pending || registration?.status === "attended"}
              onClick={() => post("cancel")}
            >
              Cancel registration
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              disabled={
                pending ||
                (session.seatsRemaining !== null && session.seatsRemaining <= 0)
              }
              onClick={() => post("register")}
            >
              Register
            </Button>
          )}
          {isRegistered && session.meetingUrl ? (
            <Button variant="outline" size="sm" asChild>
              <a href={session.meetingUrl} target="_blank" rel="noreferrer">
                Open meeting
              </a>
            </Button>
          ) : null}
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
