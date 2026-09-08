import { Head, Link, router, usePage } from "@inertiajs/react";
import { Archive, ArrowLeft, CheckCircle2, Eye, PauseCircle } from "lucide-react";
import { useState } from "react";

import {
  type AccessChange,
  AccessChangeDialog,
} from "@/components/administration/AccessChangeDialog";
import {
  FormActionBar,
  FormErrorSummary,
  FormLabel,
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { ResourceFormFields } from "@/components/office/ResourceFormFields";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { routes } from "@/lib/routes";
import type { OfficeResourceWorkspacePageProps } from "@/types";

const VIEW = { all: ["web.view_office_resources_admin"] };

const ERROR_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  slug: "Slug",
  title: "Title",
  summary: "Summary",
  category: "Category",
  resource_type: "Type",
  body: "Content",
  url: "Destination URL",
  sort_order: "Sort order",
  starts_at: "Publishes on",
  ends_at: "Expires after",
  file: "File",
};

function ResourcePreview({
  preview,
}: {
  preview: NonNullable<OfficeResourceWorkspacePageProps["preview"]>;
}) {
  return (
    <SurfaceCard>
      <SurfaceCardContent className="grid gap-3 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
            <Eye className="text-muted-foreground size-4" aria-hidden />
            Library preview · {preview.officeLabel}
          </h2>
          <p className="text-muted-foreground text-xs tabular-nums">
            {preview.localCount} local · {preview.inheritedCount} inherited
          </p>
        </div>
        <p className="text-muted-foreground text-xs">
          Exactly what agents assigned to this office see on Office Resources.
        </p>
        <ul className="grid gap-2">
          {preview.items.map((item) => (
            <li
              key={`${item.origin}-${item.slug}`}
              className="border-border grid min-w-0 gap-1 rounded-lg border p-3"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="text-foreground min-w-0 text-sm font-medium">
                  {item.title}
                </span>
                <StatusBadge
                  status={
                    item.origin === "local"
                      ? { label: `Local · ${item.sourceLabel}`, tone: "success" }
                      : {
                          label: `Inherited · ${item.sourceLabel}`,
                          tone: "neutral",
                        }
                  }
                />
              </div>
              {item.summary ? (
                <p className="text-muted-foreground text-xs">{item.summary}</p>
              ) : null}
            </li>
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

function Workspace() {
  const {
    csrfToken,
    resource,
    version,
    preview,
    writableOffices,
    capabilities,
    categories,
    types,
    validation,
  } = usePage<OfficeResourceWorkspacePageProps>().props;
  const [submitting, setSubmitting] = useState(false);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const isEdit = resource !== null;

  function transition(action: string) {
    if (!resource) return;
    setSubmitting(true);
    router.post(
      routes.admin_office_resource_transition(resource.id),
      { action, expected_version: version },
      { onFinish: () => setSubmitting(false) },
    );
  }

  function archiveConfirmed() {
    transition("archive");
    setConfirmingArchive(false);
  }

  const archiveChanges: AccessChange[] = resource
    ? [
        {
          label: "Visibility to agents",
          from: resource.isArchived || !resource.isActive ? "Hidden" : "Visible",
          to: "Hidden",
          impact: "The row is kept for audit and can be restored later with Unarchive.",
        },
      ]
    : [];

  return (
    <>
      <Head
        title={resource ? `${resource.title} · Office Resources` : "New resource"}
      />
      <div className="grid gap-8">
        <PageHeader
          title={resource ? resource.title : "New resource"}
          description={
            isEdit
              ? "Content, schedule, ownership, and lifecycle for one resource."
              : "Publish a new instruction, link, or file to a branch."
          }
          meta={
            <span className="flex flex-wrap items-center gap-2">
              {resource ? (
                <>
                  <StatusBadge
                    status={{
                      label: resource.isArchived
                        ? "Archived"
                        : resource.isActive
                          ? "Active"
                          : "Inactive",
                      tone:
                        !resource.isArchived && resource.isActive
                          ? "success"
                          : "neutral",
                    }}
                  />
                  {resource.processingState === "quarantined" ? (
                    <StatusBadge
                      status={{ label: "File quarantined", tone: "destructive" }}
                    />
                  ) : null}
                </>
              ) : null}
              <Link
                href={routes.admin_office_resources()}
                className="text-primary inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline"
              >
                <ArrowLeft className="size-3.5" aria-hidden />
                All resources
              </Link>
            </span>
          }
          actions={
            !capabilities.canManage ? (
              <span className="text-muted-foreground text-sm">Read-only</span>
            ) : undefined
          }
        />

        <FormErrorSummary errors={validation} labels={ERROR_LABELS} />

        {capabilities.canManage ? (
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
            <form
              method="post"
              action={
                isEdit
                  ? routes.admin_office_resource_update(resource.id)
                  : routes.admin_office_resource_create()
              }
              encType="multipart/form-data"
              className="grid gap-6"
              onSubmit={() => setSubmitting(true)}
            >
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <input type="hidden" name="expected_version" value={version} />

              <SurfaceCard>
                <SurfaceCardContent className="grid gap-4 pt-5">
                  <ResourceFormFields
                    defaults={{
                      slug: resource?.slug,
                      title: resource?.title,
                      summary: resource?.summary,
                      category: resource?.category,
                      resourceType: resource?.resourceType,
                      body: resource?.body,
                      url: resource?.url,
                      ownerId: resource?.ownerId ?? null,
                      sortOrder: resource?.sortOrder,
                      isActive: resource?.isActive,
                      startsAt: resource?.startsAt,
                      endsAt: resource?.endsAt,
                    }}
                    categories={categories}
                    types={types}
                    writableOffices={writableOffices}
                  />
                </SurfaceCardContent>
              </SurfaceCard>

              <FormActionBar
                status={
                  submitting ? "Saving…" : "Changes are recorded in the audit trail."
                }
              >
                <Button type="submit" disabled={submitting}>
                  {isEdit ? "Save changes" : "Create resource"}
                </Button>
              </FormActionBar>
            </form>

            <aside className="grid content-start gap-6">
              {resource && capabilities.canManage ? (
                <SurfaceCard>
                  <SurfaceCardContent className="grid gap-3 pt-5">
                    <h2 className="text-foreground text-sm font-semibold">Lifecycle</h2>
                    {resource.fileName ? (
                      <a
                        href={resource.downloadUrl}
                        download
                        className="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-2 hover:underline"
                      >
                        Download current file ({resource.fileName})
                      </a>
                    ) : null}
                    <form
                      method="post"
                      action={routes.admin_office_resource_transition(resource.id)}
                      className="grid gap-2"
                    >
                      <input
                        type="hidden"
                        name="csrfmiddlewaretoken"
                        value={csrfToken}
                      />
                      <input type="hidden" name="expected_version" value={version} />
                      {resource.isArchived ? (
                        <Button
                          type="submit"
                          name="action"
                          value="unarchive"
                          variant="outline"
                          size="sm"
                          disabled={submitting}
                        >
                          Unarchive
                        </Button>
                      ) : null}
                      {resource.isActive && !resource.isArchived ? (
                        <Button
                          type="submit"
                          name="action"
                          value="deactivate"
                          variant="outline"
                          size="sm"
                          disabled={submitting}
                        >
                          <PauseCircle className="size-3.5" aria-hidden />
                          Deactivate
                        </Button>
                      ) : null}
                      {!resource.isActive && !resource.isArchived ? (
                        <Button
                          type="submit"
                          name="action"
                          value="activate"
                          variant="outline"
                          size="sm"
                          disabled={submitting}
                        >
                          <CheckCircle2 className="size-3.5" aria-hidden />
                          Activate
                        </Button>
                      ) : null}
                      {!resource.isArchived ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setConfirmingArchive(true)}
                          disabled={submitting}
                        >
                          <Archive className="size-3.5" aria-hidden />
                          Archive
                        </Button>
                      ) : null}
                    </form>

                    <form
                      method="post"
                      action={routes.admin_office_resource_file(resource.id)}
                      encType="multipart/form-data"
                      className="border-border grid gap-2 rounded-lg border p-3"
                    >
                      <input
                        type="hidden"
                        name="csrfmiddlewaretoken"
                        value={csrfToken}
                      />
                      <input type="hidden" name="expected_version" value={version} />
                      <FormLabel htmlFor="replacement-file">Replace file</FormLabel>
                      <Input
                        id="replacement-file"
                        type="file"
                        name="file"
                        required
                        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt,.csv"
                      />
                      <Button
                        type="submit"
                        variant="secondary"
                        size="sm"
                        disabled={submitting}
                      >
                        Upload replacement
                      </Button>
                    </form>
                  </SurfaceCardContent>
                </SurfaceCard>
              ) : null}

              {preview ? (
                <ResourcePreview preview={preview} />
              ) : resource ? (
                <SurfaceCard>
                  <SurfaceCardContent className="grid gap-2 pt-5">
                    <h2 className="text-foreground text-sm font-semibold">
                      Library preview
                    </h2>
                    <p className="text-muted-foreground text-sm">
                      Compare inherited versus local resources for this resource's
                      owning office.
                    </p>
                    <a
                      href={`?preview=${resource.ownerId}`}
                      className="text-primary text-sm underline-offset-2 hover:underline"
                    >
                      Preview the {resource.ownerPathLabel} library →
                    </a>
                  </SurfaceCardContent>
                </SurfaceCard>
              ) : null}
            </aside>
          </div>
        ) : (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-2 pt-5">
              <p className="text-muted-foreground text-sm">
                You can view resources in your scope but not edit them. Ask a company
                administrator if you need publishing rights.
              </p>
            </SurfaceCardContent>
          </SurfaceCard>
        )}
      </div>

      <AccessChangeDialog
        open={confirmingArchive}
        onOpenChange={setConfirmingArchive}
        title="Archive this resource?"
        description="Archiving hides it everywhere but keeps history. You can unarchive later."
        changes={archiveChanges}
        confirmLabel="Archive resource"
        submitting={submitting}
        onConfirm={archiveConfirmed}
      />
    </>
  );
}

/**
 * Create/edit workspace for one office resource, with an in-scope library
 * preview that mirrors the agent-facing module one-to-one.
 */
export default function OfficeResourceWorkspace() {
  return (
    <PermissionRequired permission={VIEW}>
      <Workspace />
    </PermissionRequired>
  );
}

OfficeResourceWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Office Resources",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Office Resources",
            href: routes.admin_office_resources(),
          },
          { label: "Resource" },
        ],
      },
    },
  ] as const;
