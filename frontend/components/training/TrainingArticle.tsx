import { Download, ExternalLink, GraduationCap } from "lucide-react";
import { AnnouncementBody } from "@/components/announcements/AnnouncementBody";
import {
  EmptyState,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { TrainingVideoPlayer } from "@/components/training/TrainingVideoPlayer";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import {
  completionPresentation,
  contentTypePresentation,
  formatDuration,
} from "@/lib/training";
import type { TrainingDetail } from "@/types";

export function TrainingArticle({ content }: { content: TrainingDetail }) {
  const contentType = contentTypePresentation(content.contentType);
  const completion = completionPresentation(content.completion.status);
  const duration = formatDuration(content.estimatedMinutes);

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={contentType} />
        {content.isRequired ? (
          <StatusBadge status={{ label: "Required", tone: "warning" }} />
        ) : null}
        <StatusBadge status={completion} />
        {duration ? (
          <span className="text-muted-foreground text-xs">{duration}</span>
        ) : null}
      </div>

      {content.embed?.available ? (
        <TrainingVideoPlayer
          embed={content.embed}
          transcription={content.transcription}
        />
      ) : content.primaryMedia?.isReadable ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-3">
            <p className="text-sm font-medium">{content.primaryMedia.displayName}</p>
            {content.primaryMedia.mediaType.startsWith("video/") ? (
              <video
                controls
                className="aspect-video w-full rounded-lg bg-muted"
                src={content.primaryMedia.url}
              >
                <track kind="captions" />
              </video>
            ) : (
              <Button variant="outline" size="sm" asChild>
                <a href={content.primaryMedia.url} download>
                  <Download className="size-3.5" aria-hidden />
                  Download
                </a>
              </Button>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      ) : content.embed && !content.embed.available ? (
        <SurfaceCard>
          <EmptyState
            icon={GraduationCap}
            title="Video unavailable"
            description="This video cannot be embedded right now. Try again later or contact your office administrator."
          />
        </SurfaceCard>
      ) : null}

      {content.bodyBlocks.length > 0 ? (
        <AnnouncementBody blocks={content.bodyBlocks} />
      ) : null}

      {content.modules.length > 0 ? (
        <section aria-labelledby="training-modules" className="grid gap-3">
          <h2 id="training-modules" className="text-base font-semibold">
            Course modules
          </h2>
          <ol className="grid gap-2">
            {content.modules.map((module) => (
              <li key={module.id}>
                <Button
                  variant="outline"
                  className="h-auto w-full justify-start"
                  asChild
                >
                  <a href={routes.training_detail(module.id)}>
                    <span className="font-medium">{module.title}</span>
                    <span className="text-muted-foreground ml-2 text-xs">
                      {module.contentType.label}
                    </span>
                  </a>
                </Button>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {content.attachments.length > 0 ? (
        <section aria-labelledby="training-attachments" className="grid gap-3">
          <h2 id="training-attachments" className="text-base font-semibold">
            Downloads
          </h2>
          <ul className="grid gap-2">
            {content.attachments.map((file) => (
              <li key={file.id}>
                <Button variant="outline" size="sm" asChild>
                  <a href={file.url} download>
                    <Download className="size-3.5" aria-hidden />
                    {file.displayName}
                  </a>
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {content.externalUrl ? (
        <Button variant="outline" asChild>
          <a href={content.externalUrl.url} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="size-3.5" aria-hidden />
            {content.externalUrl.label}
          </a>
        </Button>
      ) : null}

      {content.interactivity === "unavailable" ? (
        <SurfaceCard>
          <EmptyState
            icon={GraduationCap}
            title="Interactive content coming soon"
            description="Quizzes, live sessions, and progress tracking will be available in a future update. You can still read the overview above."
          />
        </SurfaceCard>
      ) : null}
    </div>
  );
}
