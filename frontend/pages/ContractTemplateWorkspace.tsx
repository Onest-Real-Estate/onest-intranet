import { Head, router, usePage } from "@inertiajs/react";
import { useMemo, useState } from "react";
import { DocusealBuilderEmbed } from "@/components/DocusealBuilderEmbed";
import {
  Callout,
  FormErrorSummary,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
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
import type { ContractTemplateWorkspacePageProps } from "@/types";

const ACCESS = {
  any: ["contract.manage_contract_templates", "contract.approve_contract_templates"],
};

type MergeRow = {
  key: string;
  label: string;
  type: string;
  source: string;
};

function normalizeMergeSchema(schema: Array<Record<string, unknown>>): MergeRow[] {
  return schema.map((item) => ({
    key: String(item.key ?? "").trim(),
    label: String(item.label ?? item.key ?? "").trim(),
    type: String(item.type ?? "text").trim() || "text",
    source: String(item.source ?? "").trim(),
  }));
}

export default function ContractTemplateWorkspace() {
  const { versionDetail, capabilities, errors, csrfToken } =
    usePage<ContractTemplateWorkspacePageProps>().props;

  const [mergeRows, setMergeRows] = useState<MergeRow[]>(() =>
    normalizeMergeSchema(versionDetail.mergeSchema ?? []),
  );

  const mergeSchemaJson = useMemo(
    () => JSON.stringify(mergeRows, null, 2),
    [mergeRows],
  );

  const sourceOptions = versionDetail.mergeSourceOptions ?? [];
  const builder = versionDetail.builder;

  function postAction(
    action: "preview" | "sync_fields" | "publish" | "activate" | "retire",
  ) {
    router.post(
      routes.contract_template_action(versionDetail.id),
      { action },
      { preserveScroll: true },
    );
  }

  function updateRowSource(key: string, source: string) {
    setMergeRows((rows) =>
      rows.map((row) => (row.key === key ? { ...row, source } : row)),
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head
          title={`${versionDetail.displayName || versionDetail.versionLabel} Template`}
        />
        <PageHeader
          title={versionDetail.displayName || versionDetail.versionLabel}
          description={`${versionDetail.template.name} · ${versionDetail.versionLabel} · ${versionDetail.status}`}
          actions={
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => postAction("sync_fields")}
              >
                Sync DocuSeal fields
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => postAction("preview")}
              >
                Generate preview
              </Button>
              {capabilities.canApprove ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => postAction("publish")}
                  >
                    Publish
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => postAction("activate")}
                  >
                    Activate
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => postAction("retire")}
                  >
                    Retire
                  </Button>
                </>
              ) : null}
            </div>
          }
        />
        <FormErrorSummary errors={errors} />

        <SurfaceCard>
          <PanelHeader
            title="Draft workspace"
            description="Upload a blank PDF, place Prefill and Agent fields in DocuSeal, then map Prefill fields to hub sources."
          />
          <SurfaceCardContent>
            <div className="text-muted-foreground mb-4 grid gap-1 text-xs">
              <span>Source format: {versionDetail.sourceFormat || "Not uploaded"}</span>
              <span>
                DocuSeal template:{" "}
                {versionDetail.docusealTemplateId
                  ? `#${versionDetail.docusealTemplateId}`
                  : "Not linked yet"}
              </span>
              <span>
                Prefill fields:{" "}
                {versionDetail.placeholderKeys.length
                  ? versionDetail.placeholderKeys.join(", ")
                  : "None synced yet — place fields in the builder, then Sync"}
              </span>
              <span>
                Preview checksum:{" "}
                {versionDetail.previewChecksum || "No preview generated"}
              </span>
              {versionDetail.previewUrl ? (
                <a
                  href={versionDetail.previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Open stored preview
                </a>
              ) : null}
              <span>
                Contracts using this version: {versionDetail.contractsUsingVersion}
              </span>
            </div>
            {capabilities.canManage ? (
              <form
                method="post"
                action={routes.contract_template_update(versionDetail.id)}
                encType="multipart/form-data"
                className="grid gap-4"
              >
                <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                <input
                  type="hidden"
                  name="expected_version"
                  value={versionDetail.version}
                />
                <input type="hidden" name="merge_schema_json" value={mergeSchemaJson} />
                <div className="grid gap-2">
                  <Label htmlFor="display_name">Display name</Label>
                  <Input
                    id="display_name"
                    name="display_name"
                    defaultValue={versionDetail.displayName}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    name="description"
                    defaultValue={versionDetail.description}
                    rows={4}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="source_document">Source PDF</Label>
                  <Input
                    id="source_document"
                    name="source_document"
                    type="file"
                    accept="application/pdf,.pdf"
                  />
                  <p className="text-muted-foreground text-xs">
                    Upload creates or refreshes the DocuSeal template. Place fields with
                    Prefill (commercial terms) and Agent (signature/date) roles.
                  </p>
                </div>

                <div className="grid gap-3">
                  <Label>Merge field mapping</Label>
                  {mergeRows.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      No Prefill fields yet. Place fields in DocuSeal, click Sync
                      DocuSeal fields, then map each field to a hub source.
                    </p>
                  ) : (
                    <div className="grid gap-3">
                      {mergeRows.map((row) => (
                        <div
                          key={row.key}
                          className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] sm:items-center"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{row.key}</p>
                            <p className="text-muted-foreground truncate text-xs">
                              {row.label || row.type}
                            </p>
                          </div>
                          <Select
                            value={row.source || undefined}
                            onValueChange={(value) => updateRowSource(row.key, value)}
                          >
                            <SelectTrigger aria-label={`Source for ${row.key}`}>
                              <SelectValue placeholder="Select hub source" />
                            </SelectTrigger>
                            <SelectContent>
                              {sourceOptions.map((option) => (
                                <SelectItem key={option} value={option}>
                                  {option}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <Button type="submit">Save draft</Button>
              </form>
            ) : (
              <p className="text-muted-foreground text-sm">
                You can review, preview, publish, and activate this version, but draft
                edits stay restricted to template authors.
              </p>
            )}
          </SurfaceCardContent>
        </SurfaceCard>

        {builder?.token ? (
          <SurfaceCard>
            <PanelHeader
              title="DocuSeal field builder"
              description="Use Prefill for readonly commercial fields and Agent for signature and date."
            />
            <SurfaceCardContent>
              <div className="min-h-[40rem] overflow-hidden rounded-md border">
                <DocusealBuilderEmbed
                  token={builder.token}
                  host={builder.host || versionDetail.docusealHost}
                  protocol={
                    (builder.protocol as "http" | "https" | undefined) ??
                    (versionDetail.docusealOrigin.startsWith("http://")
                      ? "http"
                      : "https")
                  }
                  roles={["Prefill", "Agent"]}
                  withSendButton={false}
                  withSignYourselfButton={false}
                  withUploadButton={!builder.templateId}
                  requiredFields={[
                    {
                      name: "AgentSignature",
                      type: "signature",
                      role: "Agent",
                    },
                    {
                      name: "AgentSignedOn",
                      type: "date",
                      role: "Agent",
                    },
                  ]}
                  onSave={(data) => {
                    const templateId =
                      typeof data === "object" &&
                      data !== null &&
                      "id" in data &&
                      typeof (data as { id?: unknown }).id === "number"
                        ? (data as { id: number }).id
                        : null;
                    if (templateId == null) {
                      postAction("sync_fields");
                      return;
                    }
                    router.post(
                      routes.contract_template_builder_saved(versionDetail.id),
                      { docusealTemplateId: String(templateId) },
                      { preserveScroll: true },
                    );
                  }}
                />
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : versionDetail.status === "draft" ? (
          <SurfaceCard>
            <PanelHeader title="DocuSeal field builder" />
            <SurfaceCardContent className="space-y-4">
              {!versionDetail.builderReady ? (
                <p className="text-muted-foreground text-sm">
                  Configure DOCUSEAL_API_KEY, DOCUSEAL_BASE_URL, and DOCUSEAL_USER_EMAIL
                  to enable DocuSeal template linking.
                </p>
              ) : !versionDetail.docusealEmbedsAvailable ? (
                <>
                  <Callout tone="warning" title="Embedded builder needs DocuSeal Pro">
                    Community DocuSeal serves a stub for{" "}
                    <code className="text-xs">/js/builder.js</code>. Place Prefill and
                    Agent fields in the DocuSeal web UI, link the template id below,
                    then Sync DocuSeal fields.
                  </Callout>
                  {versionDetail.docusealAdminUrl ? (
                    <Button type="button" variant="outline" asChild>
                      <a
                        href={versionDetail.docusealAdminUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open DocuSeal templates
                      </a>
                    </Button>
                  ) : null}
                  {capabilities.canManage ? (
                    <form
                      className="grid max-w-md gap-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const form = event.currentTarget;
                        const value = new FormData(form)
                          .get("docusealTemplateId")
                          ?.toString()
                          .trim();
                        if (!value) return;
                        router.post(
                          routes.contract_template_builder_saved(versionDetail.id),
                          { docusealTemplateId: value },
                          { preserveScroll: true },
                        );
                      }}
                    >
                      <div className="grid gap-2">
                        <Label htmlFor="docuseal-template-id">
                          DocuSeal template id
                        </Label>
                        <Input
                          id="docuseal-template-id"
                          name="docusealTemplateId"
                          inputMode="numeric"
                          defaultValue={
                            versionDetail.docusealTemplateId != null
                              ? String(versionDetail.docusealTemplateId)
                              : ""
                          }
                          placeholder="e.g. 1"
                        />
                      </div>
                      <Button type="submit">Link DocuSeal template</Button>
                    </form>
                  ) : null}
                </>
              ) : (
                <p className="text-muted-foreground text-sm">
                  Upload a PDF and save the draft to open the DocuSeal builder.
                </p>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>
    </PermissionRequired>
  );
}

ContractTemplateWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Contract Template Workspace",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Contract Templates", href: routes.admin_contract_templates() },
        ],
      },
      variant: "standard",
    },
  ] as const;
