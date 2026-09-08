import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowDown, ArrowUp, Download, Paperclip, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FileUploader,
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import {
  fileRejectionReason,
  formatBytes,
  processingPresentation,
} from "@/lib/announcements";
import { routes } from "@/lib/routes";
import type { TrainingMediaAdmin, TrainingMediaManagerPageProps } from "@/types";

const MANAGE = { all: ["web.manage_training"] };

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function postFile(
  url: string,
  file: globalThis.File,
  role: string,
  { signal, onProgress }: { signal: AbortSignal; onProgress: (n: number) => void },
): Promise<{ id: number; displayName: string }> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    body.append("role", role);

    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.setRequestHeader("X-XSRF-TOKEN", csrfToken());
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    signal.addEventListener("abort", () => request.abort());
    request.addEventListener("abort", () => reject(new Error("Upload cancelled")));
    request.addEventListener("error", () => reject(new Error("Upload failed")));
    request.addEventListener("load", () => {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(request.responseText);
      } catch {
        payload = {};
      }
      if (request.status >= 200 && request.status < 300) {
        resolve(payload.media as { id: number; displayName: string });
        return;
      }
      const validation = payload.validation as
        | { fields?: Record<string, string[]>; form?: string[] }
        | undefined;
      const message =
        validation?.fields?.file?.[0] ??
        validation?.form?.[0] ??
        "That file could not be uploaded.";
      reject(new Error(message));
    });
    request.send(body);
  });
}

function MediaRow({
  item,
  index,
  total,
  onMove,
}: {
  item: TrainingMediaAdmin;
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
}) {
  const state = processingPresentation(
    item.processingState as "pending" | "ready" | "quarantined" | "failed",
  );
  return (
    <li className="flex flex-wrap items-center gap-3 border-b py-3 last:border-b-0">
      <Paperclip className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.displayName}</p>
        <p className="text-muted-foreground text-xs">
          {formatBytes(item.byteSize)} · {item.mediaType}
        </p>
      </div>
      <StatusBadge status={state} />
      {item.processingNote ? (
        <p className="text-destructive w-full text-xs">{item.processingNote}</p>
      ) : null}
      <div className="flex shrink-0 items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Move ${item.displayName} up`}
          disabled={index === 0}
          onClick={() => onMove(index, index - 1)}
        >
          <ArrowUp className="size-4" aria-hidden />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Move ${item.displayName} down`}
          disabled={index === total - 1}
          onClick={() => onMove(index, index + 1)}
        >
          <ArrowDown className="size-4" aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Download ${item.displayName}`}
          asChild
        >
          <a href={item.url} download>
            <Download className="size-4" aria-hidden />
          </a>
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Remove ${item.displayName}`}
          onClick={() =>
            router.post(
              routes.training_media_remove(item.id),
              {},
              { preserveScroll: true },
            )
          }
        >
          <Trash2 className="size-4" aria-hidden />
        </Button>
      </div>
    </li>
  );
}

export default function TrainingMediaManager() {
  const { content, media, limits } = usePage<TrainingMediaManagerPageProps>().props;
  const [notice, setNotice] = useState<string | null>(null);
  const attachments = media.attachments;
  const allMedia = [...(media.primary ? [media.primary] : []), ...attachments];
  const blocking = allMedia.some((item) => item.processingState !== "ready");

  function reload() {
    router.reload({ only: ["media"] });
  }

  function move(from: number, to: number) {
    const next = [...attachments];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    router.post(
      routes.training_media_reorder(content.id),
      { order: next.map((item) => String(item.id)) },
      { preserveScroll: true },
    );
  }

  const primaryLimits = limits.primary;

  return (
    <PermissionRequired permission={MANAGE}>
      <Head title={`Files — ${content.title}`} />
      <div className="grid gap-8">
        <PageHeader
          title="Training files"
          description={content.title}
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.training_edit(content.id)}>Back to workspace</Link>
            </Button>
          }
        />

        {blocking ? (
          <p role="status" className="text-warning-ink text-sm">
            This training cannot be published until every file finishes its checks.
            Quarantined files must be removed or replaced.
          </p>
        ) : null}

        {notice ? (
          <p role="alert" className="text-destructive text-sm">
            {notice}
          </p>
        ) : null}

        <section aria-labelledby="primary-heading" className="grid gap-3">
          <h2 id="primary-heading" className="text-sm font-semibold">
            Primary media
          </h2>
          <FileUploader
            label="Upload primary media"
            description={`${primaryLimits.extensions.join(", ")} · up to ${formatBytes(primaryLimits.maxBytes)}`}
            accept={primaryLimits.extensions.join(",")}
            maxSize={primaryLimits.maxBytes}
            value={
              media.primary
                ? {
                    id: String(media.primary.id),
                    name: media.primary.displayName,
                    url: media.primary.variants.thumb ?? media.primary.url,
                    size: media.primary.byteSize,
                    type: media.primary.mediaType,
                  }
                : null
            }
            validate={(file) => fileRejectionReason(file, primaryLimits)}
            upload={async (file, context) => {
              setNotice(null);
              try {
                const result = await postFile(
                  routes.training_media_upload(content.id),
                  file,
                  "primary",
                  context,
                );
                reload();
                return { id: String(result.id), name: result.displayName };
              } catch (error) {
                setNotice((error as Error).message);
                throw error;
              }
            }}
            onChange={(next) => {
              if (next === null && media.primary) {
                router.post(
                  routes.training_media_remove(media.primary.id),
                  {},
                  { preserveScroll: true },
                );
              }
            }}
          />
          {media.primary ? (
            <p className="text-muted-foreground text-xs">
              <StatusBadge
                status={processingPresentation(
                  media.primary.processingState as
                    | "pending"
                    | "ready"
                    | "quarantined"
                    | "failed",
                )}
              />
            </p>
          ) : null}
        </section>

        <section aria-labelledby="files-heading" className="grid gap-3">
          <h2 id="files-heading" className="text-sm font-semibold">
            Attachments
          </h2>
          <FileUploader
            label="Add attachment"
            description={`${limits.attachment.extensions.join(", ")} · up to ${formatBytes(limits.attachment.maxBytes)} · ${limits.attachment.maxCount} files maximum`}
            accept={limits.attachment.extensions.join(",")}
            maxSize={limits.attachment.maxBytes}
            value={null}
            removable={false}
            preview={false}
            disabled={attachments.length >= limits.attachment.maxCount}
            validate={(file) => fileRejectionReason(file, limits.attachment)}
            upload={async (file, context) => {
              setNotice(null);
              try {
                const result = await postFile(
                  routes.training_media_upload(content.id),
                  file,
                  "attachment",
                  context,
                );
                reload();
                return { id: String(result.id), name: result.displayName };
              } catch (error) {
                setNotice((error as Error).message);
                throw error;
              }
            }}
          />

          <SurfaceCard>
            <SurfaceCardContent>
              {attachments.length === 0 ? (
                <EmptyState
                  icon={Paperclip}
                  compact
                  title="No attachments yet"
                  description="Files you add appear here in the order learners will see them."
                />
              ) : (
                <ul aria-label="Attachments">
                  {attachments.map((item, index) => (
                    <MediaRow
                      key={item.id}
                      item={item}
                      index={index}
                      total={attachments.length}
                      onMove={move}
                    />
                  ))}
                </ul>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        </section>
      </div>
    </PermissionRequired>
  );
}

TrainingMediaManager.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Training files",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Training", href: routes.admin_training() },
          { label: "Files" },
        ],
      },
    },
  ] as const;
