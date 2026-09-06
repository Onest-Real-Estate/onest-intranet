import { Head, router, usePage } from "@inertiajs/react";
import { useEffect, useMemo, useState } from "react";
import {
  ContractTemplateFieldPlacer,
  type TemplateFieldLayoutItem,
} from "@/components/ContractTemplateFieldPlacer";
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

function normalizeLayout(
  layout: Array<{
    id?: string;
    name?: string;
    type?: string;
    role?: string;
    page?: number;
    x?: number;
    y?: number;
    w?: number;
    h?: number;
  }>,
): TemplateFieldLayoutItem[] {
  return layout.map((item) => ({
    id: String(item.id ?? crypto.randomUUID()),
    name: String(item.name ?? "").trim(),
    type: (String(item.type ?? "text") as TemplateFieldLayoutItem["type"]) || "text",
    role:
      (String(item.role ?? "Prefill") as TemplateFieldLayoutItem["role"]) || "Prefill",
    page: Number(item.page) || 1,
    x: Number(item.x) || 0,
    y: Number(item.y) || 0,
    w: Number(item.w) || 120,
    h: Number(item.h) || 24,
  }));
}

export default function ContractTemplateWorkspace() {
  const { versionDetail, capabilities, errors, posted, csrfToken } =
    usePage<ContractTemplateWorkspacePageProps>().props;

  const [mergeRows, setMergeRows] = useState<MergeRow[]>(() =>
    normalizeMergeSchema(versionDetail.mergeSchema ?? []),
  );
  const [fieldLayout, setFieldLayout] = useState<TemplateFieldLayoutItem[]>(() =>
    normalizeLayout(versionDetail.fieldLayout ?? []),
  );
  const [suggesting, setSuggesting] = useState(false);

  useEffect(() => {
    setMergeRows(normalizeMergeSchema(versionDetail.mergeSchema ?? []));
    setFieldLayout(normalizeLayout(versionDetail.fieldLayout ?? []));
  }, [versionDetail.mergeSchema, versionDetail.fieldLayout]);

  const mergeSchemaJson = useMemo(
    () => JSON.stringify(mergeRows, null, 2),
    [mergeRows],
  );

  const prefillFieldsInLayout = useMemo(
    () => [
      ...new Set(
        fieldLayout
          .filter((field) => field.role === "Prefill")
          .map((field) => field.name.trim())
          .filter(Boolean),
      ),
    ],
    [fieldLayout],
  );

  const prefillAwaitingSave = prefillFieldsInLayout.filter(
    (name) => !versionDetail.placeholderKeys.includes(name),
  );

  const prefillNeedsSource = mergeRows.filter((row) => !row.source);

  const sourceOptions = versionDetail.mergeSourceOptions ?? [];
  const canEdit = Boolean(capabilities.canManage && versionDetail.status === "draft");

  const [savingFields, setSavingFields] = useState(false);

  function postAction(
    action: "preview" | "suggest_fields" | "publish" | "activate" | "retire",
  ) {
    if (action === "suggest_fields") setSuggesting(true);
    router.post(
      routes.contract_template_action(versionDetail.id),
      { action },
      {
        preserveScroll: true,
        onFinish: () => setSuggesting(false),
      },
    );
  }

  function saveFieldLayout() {
    setSavingFields(true);
    router.post(
      routes.contract_template_field_layout(versionDetail.id),
      {
        fieldLayoutJson: JSON.stringify(fieldLayout),
        expectedVersion: versionDetail.version,
      },
      {
        preserveScroll: true,
        onFinish: () => setSavingFields(false),
      },
    );
  }

  useEffect(() => {
    const suggestions = posted?.fieldSuggestions;
    if (!Array.isArray(suggestions) || suggestions.length === 0) return;
    setFieldLayout(
      normalizeLayout(suggestions as unknown as TemplateFieldLayoutItem[]),
    );
  }, [posted]);

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
              {capabilities.canManage && versionDetail.fieldAiConfigured ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => postAction("suggest_fields")}
                  disabled={!versionDetail.sourcePdfUrl || suggesting}
                >
                  {suggesting ? "Suggesting…" : "Suggest fields (AI)"}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="outline"
                onClick={() => postAction("preview")}
                disabled={!versionDetail.sourcePdfUrl || fieldLayout.length === 0}
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
            description="Upload a blank PDF, place Prefill and Agent fields in the Hub placer, map merge sources, then preview and publish."
          />
          <SurfaceCardContent>
            <div className="text-muted-foreground mb-4 grid gap-1 text-xs">
              <span>Source format: {versionDetail.sourceFormat || "Not uploaded"}</span>
              <span>
                Prefill fields:{" "}
                {versionDetail.placeholderKeys.length
                  ? versionDetail.placeholderKeys.join(", ")
                  : "None yet — place Prefill fields and save layout"}
              </span>
              <span>
                Preview checksum:{" "}
                {versionDetail.previewChecksum || "No preview generated"}
              </span>
              {versionDetail.sourcePdfUrl ? (
                <a
                  href={versionDetail.sourcePdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  Open source PDF
                </a>
              ) : null}
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
                    Upload a blank PDF, then place Prefill (commercial terms) and Agent
                    (signature/date) fields below.
                  </p>
                </div>

                <div className="grid gap-3">
                  <div className="grid gap-1">
                    <Label>Prefill mapping</Label>
                    <p className="text-muted-foreground text-sm leading-6">
                      Prefill fields are text boxes you place on the PDF. At contract
                      generation time the Hub writes agent, office, and terms data into
                      those boxes using the hub source you choose here.
                    </p>
                  </div>
                  {prefillAwaitingSave.length > 0 ? (
                    <Callout tone="info" title="Save fields first">
                      These Prefill fields are on the PDF but not saved yet:{" "}
                      {prefillAwaitingSave.join(", ")}. Click{" "}
                      <strong>Save fields</strong> in the placer, then map each name
                      below.
                    </Callout>
                  ) : null}
                  {mergeRows.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      No Prefill fields yet. In the field placer, choose the Prefill
                      role, add Text fields on the contract, click Save fields, then map
                      each field name here.
                    </p>
                  ) : (
                    <div className="grid gap-3">
                      {prefillNeedsSource.length > 0 ? (
                        <Callout tone="warning" title="Map every Prefill field">
                          Select a hub source for:{" "}
                          {prefillNeedsSource.map((row) => row.key).join(", ")}. Publish
                          requires all Prefill fields to be mapped.
                        </Callout>
                      ) : null}
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
                            <SelectTrigger aria-label={`Hub source for ${row.key}`}>
                              <SelectValue placeholder="Choose hub data source" />
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

        <SurfaceCard>
          <PanelHeader
            title="Field placer"
            description="Drag fields from the palette onto the PDF. Prefill for commercial terms, Agent for signature and date. AI suggestions must be reviewed before save."
          />
          <SurfaceCardContent className="space-y-4">
            {!versionDetail.sourcePdfUrl ? (
              <p className="text-muted-foreground text-sm">
                Upload a PDF and save the draft to open the field placer.
              </p>
            ) : (
              <>
                {!versionDetail.fieldAiConfigured ? (
                  <Callout tone="warning" title="Field AI optional">
                    Configure CONTRACT_FIELD_AI_ENDPOINT and CONTRACT_FIELD_AI_API_KEY
                    to suggest field boxes from the PDF. Manual placement always works.
                  </Callout>
                ) : null}
                <ContractTemplateFieldPlacer
                  pdfUrl={versionDetail.sourcePdfUrl}
                  value={fieldLayout}
                  onChange={setFieldLayout}
                  readOnly={!canEdit}
                  onSave={canEdit ? saveFieldLayout : undefined}
                  saving={savingFields}
                />
              </>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
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
      variant: "wide",
    },
  ] as const;
