import { router } from "@inertiajs/react";
import { useState } from "react";

import {
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { routes } from "@/lib/routes";
import { completionPresentation } from "@/lib/training";
import type { TrainingDetail } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

export function TrainingProgressPanel({
  content,
  errors,
}: {
  content: TrainingDetail;
  errors?: ValidationErrors;
}) {
  const [pending, setPending] = useState(false);
  const completion = completionPresentation(content.completion.status);
  const percent = content.completion.progressPercent ?? null;
  const formError = errors?.form?.[0] ?? errors?.fields?.action?.[0];

  function post(action: string) {
    setPending(true);
    router.post(
      routes.training_progress(content.id),
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
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold">Your progress</h2>
          <StatusBadge status={completion} />
        </div>
        {percent !== null ? (
          <div className="grid gap-2">
            <Progress value={percent} aria-label={`${percent} percent complete`} />
            <p className="text-muted-foreground text-xs tabular-nums">
              {percent}% complete
            </p>
          </div>
        ) : null}
        {formError ? (
          <p className="text-destructive text-sm" role="alert">
            {formError}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {content.canMarkStarted ? (
            <Button
              type="button"
              size="sm"
              disabled={pending}
              onClick={() => post("start")}
            >
              Start
            </Button>
          ) : null}
          {content.canMarkComplete ? (
            <Button
              type="button"
              size="sm"
              disabled={pending}
              onClick={() => post("complete")}
            >
              Mark complete
            </Button>
          ) : null}
        </div>
        {content.certificate?.available && content.certificate.downloadUrl ? (
          <Button variant="outline" size="sm" asChild>
            <a href={content.certificate.downloadUrl}>Download certificate</a>
          </Button>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
