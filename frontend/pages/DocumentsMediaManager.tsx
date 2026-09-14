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
import type { DocumentsAdminFileItem, DocumentsMediaManagerPageProps } from "@/types";

const MANAGE = { all: ["web.manage_documents"] };

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function postFile(
  url: string,
  file: globalThis.File,
  { signal, onProgress }: { signal: AbortSignal; onProgress: (n: number) => void },
): Promise<{ id: number; displayName: string }> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);

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
  locked,
  onMove,
}: {
  item: DocumentsAdminFileItem;
  index: number;
  total: number;
  locked: boolean;
  onMove: (from: number, to: number) => void;
}) {
  const presentation = processingPresentation(item.processingState);
  return (
    <li className="flex items-center gap-2 border-b py-2 last:border-b-0">
      <div className="grid min-w-0 flex-1 gap-0.5">
        <span className="truncate text-sm font-medium">{item.displayName}</span>
        <span className="text-muted-foreground text-xs">
          {formatBytes(item.byteSize)}
        </span>
      </div>
      <StatusBadge status={{ label: presentation.label, tone: presentation.tone }} />
      {item.url ? (
        <Button variant="ghost" size="sm" asChild>
          <a href={`${item.url}?preview=1`} target="_blank" rel="noreferrer">
            <Download className="size-3.5" aria-hidden />
            <span className="sr-only">Preview {item.displayName}</span>
          </a>
        </Button>
      ) : null}
      {!locked ? (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={index === 0}
            onClick={() => onMove(index, index - 1)}
            aria-label={`Move ${item.displayName} up`}
          >
            <ArrowUp className="size-3.5" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={index === total - 1}
            onClick={() => onMove(index, index + 1)}
            aria-label={`Move ${item.displayName} down`}
          >
            <ArrowDown className="size-3.5" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              router.post(routes.document_admin_media_remove(item.id), undefined, {
                preserveScroll: true,
              })
            }
            aria-label={`Remove ${item.displayName}`}
          >
            <Trash2 className="size-3.5" aria-hidden />
          </Button>
        </>
      ) : null}
    </li>
  );
}

export default function DocumentsMediaManager() {
  const { document, files, limits, validation } =
    usePage<DocumentsMediaManagerPageProps>().props;
  const [notice, setNotice] = useState<string | null>(
    validation.form[0] ?? validation.fields.file?.[0] ?? null,
  );
  const locked = document.status !== "draft";

  function reload() {
    router.reload({ only: ["files", "document", "validation"] });
  }

  function move(from: number, to: number) {
    const next = [...files];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    router.post(
      routes.document_admin_media_reorder(document.id),
      { order: next.map((row) => String(row.id)) },
      { preserveScroll: true },
    );
  }

  return (
    <PermissionRequired permission={MANAGE}>
      <div className="grid gap-8">
        <Head title={`${document.name} files`} />
        <PageHeader
          title="Document files"
          description={
            locked
              ? "Published files are immutable. Duplicate as a new version to replace them."
              : "Uploads are inspected before they are stored. Removing a file deactivates it; bytes stay for audit."
          }
          actions={
            <Button variant="outline" asChild>
              <Link href={routes.document_admin_edit(document.id)}>
                Back to document
              </Link>
            </Button>
          }
        />

        {notice ? (
          <p className="text-destructive text-sm" role="alert">
            {notice}
          </p>
        ) : null}

        <section aria-labelledby="files-heading" className="grid gap-3">
          <h2 id="files-heading" className="text-sm font-semibold">
            Files
          </h2>
          <FileUploader
            label="Add file"
            description={`${limits.document.extensions.join(", ")} · up to ${formatBytes(limits.document.maxBytes)} · ${limits.document.maxCount} files maximum`}
            accept={limits.document.extensions.join(",")}
            maxSize={limits.document.maxBytes}
            value={null}
            removable={false}
            preview={false}
            disabled={locked || files.length >= limits.document.maxCount}
            validate={(file) => fileRejectionReason(file, limits.document)}
            upload={async (file, context) => {
              setNotice(null);
              try {
                const result = await postFile(
                  routes.document_admin_media_upload(document.id),
                  file,
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
              {files.length === 0 ? (
                <EmptyState
                  icon={Paperclip}
                  compact
                  title="No files yet"
                  description="Upload at least one ready PDF, DOCX, or text file before publishing."
                />
              ) : (
                <ul aria-label="Document files">
                  {files.map((item, index) => (
                    <MediaRow
                      key={item.id}
                      item={item}
                      index={index}
                      total={files.length}
                      locked={locked}
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

DocumentsMediaManager.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Document files",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Documents", href: routes.admin_documents() },
          { label: "Files" },
        ],
      },
    },
  ] as const;
