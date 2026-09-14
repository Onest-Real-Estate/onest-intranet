import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Download, FileText, Info } from "lucide-react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/announcements";
import { routes } from "@/lib/routes";
import type { DocumentDetailPageProps, DocumentsFileItem } from "@/types";

function FileRow({ file }: { file: DocumentsFileItem }) {
  const href = file.url || routes.document_file(file.id);
  return (
    <li className="border-border grid gap-2 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="bg-muted text-muted-foreground flex size-14 shrink-0 items-center justify-center rounded-md">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="grid min-w-0 gap-0.5">
          <span className="text-foreground truncate text-sm font-medium">
            {file.displayName}
          </span>
          <span className="text-muted-foreground text-xs">
            {formatBytes(file.byteSize)} · {file.mediaType}
          </span>
        </div>
      </div>
      <Button type="button" variant="outline" size="sm" asChild>
        {/* Plain anchor: an Inertia visit would XHR the bytes instead of
            triggering the browser's download flow. */}
        <a href={href} download>
          <Download className="size-3.5 shrink-0" aria-hidden />
          Download
        </a>
      </Button>
    </li>
  );
}

export default function DocumentDetail() {
  const { document } = usePage<DocumentDetailPageProps>().props;

  return (
    <>
      <Head title={document.name} />
      <div className="grid gap-8">
        <PageHeader
          title={document.name}
          description={document.description || undefined}
          meta={
            <span className="flex flex-wrap items-center gap-2">
              {document.category ? (
                <StatusBadge
                  status={{
                    label: document.category.label,
                    tone: toStatusTone(document.category.tone),
                  }}
                />
              ) : null}
              <span className="text-muted-foreground text-sm">
                {document.versionLabel}
                {document.effectiveAt
                  ? ` · Effective ${new Date(document.effectiveAt).toLocaleDateString()}`
                  : ""}
              </span>
            </span>
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.documents_forms()}>
                <ArrowLeft className="size-4" aria-hidden />
                All documents
              </Link>
            </Button>
          }
        />

        {document.superseded ? (
          <p
            role="status"
            className="border-border bg-muted text-foreground flex items-start gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            This bookmark pointed at a superseded version. You are viewing the current
            approved file.
          </p>
        ) : null}

        {(document.jurisdictionStateCodes.length > 0 || document.expiresAt) && (
          <SurfaceCard>
            <PanelHeader divided title="Applicability" />
            <SurfaceCardContent className="grid gap-2 text-sm">
              {document.jurisdictionStateCodes.length > 0 ? (
                <p>
                  <span className="text-foreground font-medium">States: </span>
                  <span className="text-muted-foreground">
                    {document.jurisdictionStateCodes.join(", ")}
                  </span>
                </p>
              ) : null}
              <p>
                <span className="text-foreground font-medium">Scope: </span>
                <span className="text-muted-foreground">
                  {document.scope.label} · {document.scope.officeName}
                </span>
              </p>
              {document.expiresAt ? (
                <p>
                  <span className="text-foreground font-medium">Expires: </span>
                  <span className="text-muted-foreground">
                    {new Date(document.expiresAt).toLocaleDateString()}
                  </span>
                </p>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        )}

        <SurfaceCard>
          <PanelHeader
            divided
            title="Downloads"
            description="The current approved file for your role and office."
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {document.files.length} {document.files.length === 1 ? "file" : "files"}
              </span>
            }
          />
          <SurfaceCardContent>
            {document.files.length === 0 ? (
              <EmptyState
                icon={FileText}
                compact
                title="No files yet"
                description="Files for this form will appear here when they are ready."
              />
            ) : (
              <ul className="grid gap-3" aria-label="Document downloads">
                {document.files.map((file) => (
                  <FileRow key={file.id} file={file} />
                ))}
              </ul>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

DocumentDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Documents & forms",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Documents & forms",
            href: routes.documents_forms(),
          },
        ],
      },
    },
  ] as const;
