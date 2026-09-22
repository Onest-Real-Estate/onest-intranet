import { router } from "@inertiajs/react";
import {
  Download,
  FileText,
  Lock,
  MessageSquare,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  EmptyState,
  FileUploader,
  FormActionBar,
  FormFieldError,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type {
  TransactionDocumentPackage,
  TransactionDocumentSchema,
  TransactionDocumentVersionRow,
  TransactionWorkspacePageProps,
} from "@/types";

const NOTE_VISIBILITIES = [
  { value: "team", label: "Team" },
  { value: "broker_compliance", label: "Broker / compliance" },
  { value: "private_author", label: "Private (author only)" },
];

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function processingTone(
  state: string,
): "info" | "success" | "warning" | "destructive" | "neutral" {
  if (state === "ready") return "success";
  if (state === "pending") return "info";
  if (state === "quarantined" || state === "failed") return "destructive";
  return "neutral";
}

function postDocumentFile(
  url: string,
  file: globalThis.File,
  fields: Record<string, string>,
  { signal, onProgress }: { signal: AbortSignal; onProgress: (n: number) => void },
): Promise<{ name: string; size?: number; type?: string }> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    for (const [key, value] of Object.entries(fields)) {
      body.append(key, value);
    }
    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.setRequestHeader("X-XSRF-TOKEN", csrfToken());
    request.setRequestHeader("Accept", "application/json");
    request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
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
        resolve({ name: file.name, size: file.size, type: file.type });
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

function reloadDocuments(publicId: string) {
  router.get(
    `${routes.transaction_workspace(publicId)}?section=documents`,
    {},
    { preserveScroll: true, replace: true },
  );
}

function VersionActions({
  version,
  publicId,
  expectedVersion,
  canEdit,
  canLock,
}: {
  version: TransactionDocumentVersionRow;
  publicId: string;
  expectedVersion: string;
  canEdit: boolean;
  canLock: boolean;
}) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [visibility, setVisibility] = useState("team");
  const [busy, setBusy] = useState(false);

  return (
    <div className="grid gap-3 border-t border-border/60 pt-3">
      <div className="flex flex-wrap gap-2">
        {version.isReadable && version.previewUrl ? (
          <>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setPreviewOpen(true)}
            >
              Preview
            </Button>
            <Button asChild size="sm" variant="outline">
              <a href={version.downloadUrl} download>
                <Download className="size-3.5" aria-hidden />
                Download
              </a>
            </Button>
          </>
        ) : null}
        {canEdit &&
        (version.processingState === "failed" ||
          version.processingState === "quarantined") ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              router.post(
                routes.transaction_document_retry(publicId, version.publicId),
                {
                  expectedVersion,
                },
              )
            }
          >
            <RefreshCw className="size-3.5" aria-hidden />
            Retry processing
          </Button>
        ) : null}
        {canLock && version.isReadable && !version.isLocked ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              router.post(
                routes.transaction_document_lock(publicId, version.publicId),
                {
                  expectedVersion,
                  complianceStatus: "approved",
                },
              )
            }
          >
            <Lock className="size-3.5" aria-hidden />
            Mark approved
          </Button>
        ) : null}
      </div>

      {version.reviewComments.length > 0 ? (
        <ul className="grid gap-2">
          {version.reviewComments.map((comment) => (
            <li
              key={comment.publicId}
              className="rounded-md border border-border/60 px-3 py-2 text-sm"
            >
              <div className="text-muted-foreground mb-1 flex flex-wrap gap-2 text-xs">
                <span>{comment.visibilityLabel}</span>
                <span>{comment.resolutionLabel}</span>
                <span>{comment.author?.displayName || "Unknown"}</span>
              </div>
              <p className="whitespace-pre-wrap">{comment.body}</p>
              {canEdit ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {comment.resolutionState === "open" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        router.post(
                          routes.transaction_document_comment_resolve(
                            publicId,
                            comment.publicId,
                          ),
                          {
                            expectedVersion,
                            resolutionState: "resolved",
                          },
                        )
                      }
                    >
                      Resolve
                    </Button>
                  ) : null}
                  {comment.mine ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        router.post(
                          routes.transaction_document_comment_end(
                            publicId,
                            comment.publicId,
                          ),
                          { expectedVersion },
                        )
                      }
                    >
                      Remove
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {canEdit ? (
        <div className="grid gap-2">
          <Label htmlFor={`review-${version.publicId}`}>Review comment</Label>
          <Select value={visibility} onValueChange={setVisibility}>
            <SelectTrigger id={`review-vis-${version.publicId}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {NOTE_VISIBILITIES.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Textarea
            id={`review-${version.publicId}`}
            value={commentBody}
            onChange={(event) => setCommentBody(event.target.value)}
            rows={2}
          />
          <Button
            type="button"
            size="sm"
            disabled={busy || !commentBody.trim()}
            onClick={() => {
              setBusy(true);
              router.post(
                routes.transaction_document_comment_save(publicId, version.publicId),
                {
                  expectedVersion,
                  body: commentBody,
                  visibility,
                },
                {
                  onFinish: () => setBusy(false),
                  onSuccess: () => setCommentBody(""),
                },
              );
            }}
          >
            <MessageSquare className="size-3.5" aria-hidden />
            Add comment
          </Button>
        </div>
      ) : null}

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{version.displayName}</DialogTitle>
          </DialogHeader>
          {version.mediaType.startsWith("image/") ? (
            <img
              src={version.previewUrl}
              alt={version.displayName}
              className="max-h-[70vh] w-full object-contain"
            />
          ) : (
            <iframe
              title={version.displayName}
              src={version.previewUrl}
              className="h-[70vh] w-full rounded-md border"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DocumentCard({
  package: row,
  publicId,
  expectedVersion,
  canEdit,
  canLock,
  schema,
  errors,
}: {
  package: TransactionDocumentPackage;
  publicId: string;
  expectedVersion: string;
  canEdit: boolean;
  canLock: boolean;
  schema: TransactionDocumentSchema;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const [title, setTitle] = useState(row.title);
  const [category, setCategory] = useState(row.category);
  const [requirement, setRequirement] = useState(row.requirement);
  const [retentionPolicy, setRetentionPolicy] = useState(row.retentionPolicy);
  const [busy, setBusy] = useState(false);
  const current = row.currentVersion;

  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-4 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-medium">{row.title}</h3>
            <p className="text-muted-foreground text-sm">
              {row.categoryLabel} · {row.requirementLabel}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {current ? (
              <StatusBadge
                status={{
                  label: current.processingState,
                  tone: processingTone(current.processingState),
                }}
              />
            ) : null}
            {current?.isLocked ? (
              <StatusBadge status={{ label: "Locked", tone: "warning" }} />
            ) : null}
          </div>
        </div>

        {current ? (
          <div className="text-sm">
            <p>
              Current: v{current.versionNumber} · {current.displayName}
              {current.isLocked ? ` · ${current.lockReason || "locked"}` : ""}
            </p>
            <VersionActions
              version={current}
              publicId={publicId}
              expectedVersion={expectedVersion}
              canEdit={canEdit}
              canLock={canLock}
            />
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            No ready version yet. Processing may still be running.
          </p>
        )}

        {row.versions.length > 1 ? (
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Version history</summary>
            <ul className="mt-2 grid gap-2">
              {row.versions.map((version) => (
                <li
                  key={version.publicId}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/60 px-3 py-2"
                >
                  <span>
                    v{version.versionNumber} · {version.displayName}
                    {version.isCurrent ? " (current)" : ""}
                    {version.isLocked ? " · locked" : ""}
                  </span>
                  <StatusBadge
                    status={{
                      label: version.processingState,
                      tone: processingTone(version.processingState),
                    }}
                  />
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        {canEdit ? (
          <div className="grid gap-3 border-t border-border/60 pt-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor={`title-${row.publicId}`}>Title</Label>
                <Input
                  id={`title-${row.publicId}`}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`category-${row.publicId}`}>Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger id={`category-${row.publicId}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.categories.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`req-${row.publicId}`}>Requirement</Label>
                <Select value={requirement} onValueChange={setRequirement}>
                  <SelectTrigger id={`req-${row.publicId}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.requirements.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`ret-${row.publicId}`}>Retention</Label>
                <Select value={retentionPolicy} onValueChange={setRetentionPolicy}>
                  <SelectTrigger id={`ret-${row.publicId}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.retentionPolicies.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <FormFieldError messages={errors?.fields?.title} />
            <FormActionBar status="Classification applies to the package, not a single version.">
              <Button
                type="button"
                disabled={busy || !title.trim()}
                onClick={() => {
                  setBusy(true);
                  router.post(
                    routes.transaction_document_classify(publicId, row.publicId),
                    {
                      expectedVersion,
                      title,
                      category,
                      requirement,
                      retentionPolicy,
                    },
                    { onFinish: () => setBusy(false) },
                  );
                }}
              >
                Save classification
              </Button>
              {!current?.isLocked ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    router.post(
                      routes.transaction_document_retire(publicId, row.publicId),
                      { expectedVersion },
                    )
                  }
                >
                  <Trash2 className="size-3.5" aria-hidden />
                  Retire
                </Button>
              ) : null}
            </FormActionBar>
            <div className="grid gap-1.5">
              <Label>Upload new version</Label>
              <FileUploader
                label="Replace with a new revision"
                description="Creates an immutable new version. Locked versions stay retained."
                accept={schema.matrix.extensions.join(",")}
                maxSize={schema.matrix.maxBytes}
                upload={(file, context) =>
                  postDocumentFile(
                    routes.transaction_document_revision(publicId, row.publicId),
                    file,
                    { expectedVersion },
                    context,
                  ).then((result) => {
                    reloadDocuments(publicId);
                    return result;
                  })
                }
              />
            </div>
          </div>
        ) : null}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function DocumentsPanel({
  documents = [],
  documentSchema,
  expectedVersion,
  publicId,
  canEdit,
  canLock,
  errors,
}: {
  documents?: TransactionDocumentPackage[];
  documentSchema?: TransactionDocumentSchema | null;
  expectedVersion: string;
  publicId: string;
  canEdit: boolean;
  canLock: boolean;
  errors?: TransactionWorkspacePageProps["errors"];
}) {
  const schema = documentSchema;
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState(schema?.categories[0]?.value || "other");
  const [requirement, setRequirement] = useState("optional");

  if (!schema) {
    return (
      <EmptyState
        icon={FileText}
        title="Documents loading"
        description="Document controls will appear when this section finishes loading."
        compact
      />
    );
  }

  const accept = schema.matrix.extensions.join(",");

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-medium">Documents</h2>
        <p className="text-muted-foreground text-sm">
          Protected deal files with versioning, classification, and review comments.
        </p>
      </div>

      {documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload PDFs or images for this transaction. Unsafe files stay quarantined."
          compact
        />
      ) : (
        <div className="grid gap-4">
          {documents.map((row) => (
            <DocumentCard
              key={row.publicId}
              package={row}
              publicId={publicId}
              expectedVersion={expectedVersion}
              canEdit={canEdit}
              canLock={canLock}
              schema={schema}
              errors={errors}
            />
          ))}
        </div>
      )}

      {canEdit ? (
        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4 py-5">
            <h3 className="text-base font-medium">Upload document</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5 sm:col-span-1">
                <Label htmlFor="new-doc-title">Title</Label>
                <Input
                  id="new-doc-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Optional — defaults to file name"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="new-doc-category">Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger id="new-doc-category">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.categories.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="new-doc-requirement">Requirement</Label>
                <Select value={requirement} onValueChange={setRequirement}>
                  <SelectTrigger id="new-doc-requirement">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.requirements.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <FileUploader
              label="Choose files"
              description={`Allowed: ${accept}. Max ${Math.round(schema.matrix.maxBytes / (1024 * 1024))} MB.`}
              accept={accept}
              maxSize={schema.matrix.maxBytes}
              upload={(file, context) =>
                postDocumentFile(
                  routes.transaction_document_upload(publicId),
                  file,
                  {
                    expectedVersion,
                    title: title || file.name.replace(/\.[^.]+$/, ""),
                    category,
                    requirement,
                  },
                  context,
                ).then((result) => {
                  setTitle("");
                  reloadDocuments(publicId);
                  return result;
                })
              }
            />
            <FormFieldError messages={errors?.fields?.file} />
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}
