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
import type { MarketingFileItem, MarketingMediaManagerPageProps } from "@/types";

const MANAGE = { all: ["web.manage_marketing_resources"] };

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
        resolve(payload.file as { id: number; displayName: string });
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
  canDownload,
}: {
  item: MarketingFileItem;
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
  canDownload: boolean;
}) {
  const state = processingPresentation(
    (item.processingState ?? "pending") as
      | "pending"
      | "ready"
      | "quarantined"
      | "failed",
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
        {canDownload && item.url ? (
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
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Remove ${item.displayName}`}
          onClick={() =>
            router.post(
              routes.marketing_media_remove(item.id),
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

export default function MarketingMediaManager() {
  const { asset, files, limits, capabilities } =
    usePage<MarketingMediaManagerPageProps>().props;
  const [notice, setNotice] = useState<string | null>(null);
  const exports = files.exports;
  const sources = capabilities.canDownloadSources ? files.sources : [];
  const blocking = exports.some((item) => item.processingState !== "ready");

  function reload() {
    router.reload({ only: ["files"] });
  }

  function move(role: "export" | "source", from: number, to: number) {
    const list = role === "export" ? [...exports] : [...sources];
    const [moved] = list.splice(from, 1);
    list.splice(to, 0, moved);
    router.post(
      routes.marketing_media_reorder(asset.id),
      {
        order: list.map((item) => String(item.id)),
        role,
      },
      { preserveScroll: true },
    );
  }

  return (
    <PermissionRequired permission={MANAGE}>
      <Head title={`Files — ${asset.title}`} />
      <div className="grid gap-8">
        <PageHeader
          title="Marketing files"
          description={asset.title}
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.marketing_edit(asset.id)}>Back to workspace</Link>
            </Button>
          }
        />

        {blocking ? (
          <p role="status" className="text-warning-ink text-sm">
            This asset cannot be published until every export finishes its checks.
            Quarantined files must be removed or replaced.
          </p>
        ) : null}

        {notice ? (
          <p role="alert" className="text-destructive text-sm">
            {notice}
          </p>
        ) : null}

        <section aria-labelledby="exports-heading" className="grid gap-3">
          <h2 id="exports-heading" className="text-sm font-semibold">
            Export files
          </h2>
          <FileUploader
            label="Add export"
            description={`${limits.export.extensions.join(", ")} · up to ${formatBytes(limits.export.maxBytes)} · ${limits.export.maxCount} files maximum`}
            accept={limits.export.extensions.join(",")}
            maxSize={limits.export.maxBytes}
            value={null}
            removable={false}
            preview={false}
            disabled={exports.length >= limits.export.maxCount}
            validate={(file) => fileRejectionReason(file, limits.export)}
            upload={async (file, context) => {
              setNotice(null);
              try {
                const result = await postFile(
                  routes.marketing_media_upload(asset.id),
                  file,
                  "export",
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
              {exports.length === 0 ? (
                <EmptyState
                  icon={Paperclip}
                  compact
                  title="No export files yet"
                  description="Files recipients can download appear here in order."
                />
              ) : (
                <ul aria-label="Export files">
                  {exports.map((item, index) => (
                    <MediaRow
                      key={item.id}
                      item={item}
                      index={index}
                      total={exports.length}
                      canDownload
                      onMove={(from, to) => move("export", from, to)}
                    />
                  ))}
                </ul>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        </section>

        {capabilities.canDownloadSources ? (
          <section aria-labelledby="sources-heading" className="grid gap-3">
            <h2 id="sources-heading" className="text-sm font-semibold">
              Source files
            </h2>
            <p className="text-muted-foreground text-sm">
              Working files for the marketing team. Never shown to library consumers.
            </p>
            <FileUploader
              label="Add source"
              description={`${limits.source.extensions.join(", ")} · up to ${formatBytes(limits.source.maxBytes)} · ${limits.source.maxCount} files maximum`}
              accept={limits.source.extensions.join(",")}
              maxSize={limits.source.maxBytes}
              value={null}
              removable={false}
              preview={false}
              disabled={sources.length >= limits.source.maxCount}
              validate={(file) => fileRejectionReason(file, limits.source)}
              upload={async (file, context) => {
                setNotice(null);
                try {
                  const result = await postFile(
                    routes.marketing_media_upload(asset.id),
                    file,
                    "source",
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
                {sources.length === 0 ? (
                  <EmptyState
                    icon={Paperclip}
                    compact
                    title="No source files yet"
                    description="Editable working files stay here for people with the source download grant."
                  />
                ) : (
                  <ul aria-label="Source files">
                    {sources.map((item, index) => (
                      <MediaRow
                        key={item.id}
                        item={item}
                        index={index}
                        total={sources.length}
                        canDownload={Boolean(item.url)}
                        onMove={(from, to) => move("source", from, to)}
                      />
                    ))}
                  </ul>
                )}
              </SurfaceCardContent>
            </SurfaceCard>
          </section>
        ) : (
          <p className="text-muted-foreground text-sm">
            Source working files are hidden. You need the download marketing sources
            grant to upload or download them.
          </p>
        )}
      </div>
    </PermissionRequired>
  );
}

MarketingMediaManager.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Marketing files",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Marketing resources",
            href: routes.admin_marketing_resources(),
          },
          { label: "Files" },
        ],
      },
    },
  ] as const;
