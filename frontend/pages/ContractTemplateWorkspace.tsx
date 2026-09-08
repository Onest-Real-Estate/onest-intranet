import { Head, router, usePage } from "@inertiajs/react";
import {
  Archive,
  BadgeCheck,
  Eye,
  FileText,
  MoreHorizontal,
  Send,
  Sparkles,
} from "lucide-react";
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
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  const isDraft = versionDetail.status === "draft";
  const canEdit = Boolean(capabilities.canManage && isDraft);

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
          description={`${versionDetail.template.name} · ${versionDetail.versionLabel}`}
          meta={
            <StatusBadge
              status={{
                label: versionDetail.statusLabel,
                tone: toStatusTone(versionDetail.statusTone),
              }}
            />
          }
          actions={
            /*
             * One primary, and it is whichever move this version is actually
             * waiting for. This row previously held five outline buttons and a
             * destructive one, so nothing said which to press and the row wrapped
             * into three lines on a laptop. Retire moves out of the row entirely
             * — an irreversible action does not belong one pixel from "Publish".
             */
            <div className="flex flex-wrap items-center gap-2">
              {capabilities.canManage && versionDetail.fieldAiConfigured ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => postAction("suggest_fields")}
                  disabled={!versionDetail.sourcePdfUrl || suggesting}
                >
                  <Sparkles className="size-4" aria-hidden />
                  {suggesting ? "Suggesting…" : "Suggest fields"}
                </Button>
              ) : null}
              <Button
                type="button"
                variant={isDraft ? "default" : "outline"}
                onClick={() => postAction("preview")}
                disabled={!versionDetail.sourcePdfUrl || fieldLayout.length === 0}
              >
                <Eye className="size-4" aria-hidden />
                Generate preview
              </Button>
              {capabilities.canApprove && isDraft ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => postAction("publish")}
                >
                  <Send className="size-4" aria-hidden />
                  Publish
                </Button>
              ) : null}
              {capabilities.canApprove && !isDraft ? (
                <Button type="button" onClick={() => postAction("activate")}>
                  <BadgeCheck className="size-4" aria-hidden />
                  Activate
                </Button>
              ) : null}
              {capabilities.canApprove ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="More template actions"
                    >
                      <MoreHorizontal className="size-4" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {!isDraft ? (
                      <DropdownMenuItem onSelect={() => postAction("publish")}>
                        <Send className="size-4" aria-hidden />
                        Publish
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onSelect={() => postAction("activate")}>
                        <BadgeCheck className="size-4" aria-hidden />
                        Activate
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => postAction("retire")}
                    >
                      <Archive className="size-4" aria-hidden />
                      Retire this version
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
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
            {/*
              Six facts that were a stack of muted 11px spans, one of which was a
              64-character checksum sitting in the reading order between two
              sentences. They are a record, so they get a record's shape, and the
              checksum is monospace and truncated because nobody reads it — they
              compare it.
            */}
            <dl className="bg-muted/40 border-border/60 mb-5 grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
              <ReadOnlyValue label="Source format">
                {versionDetail.sourceFormat || (
                  <span className="text-muted-foreground">Not uploaded</span>
                )}
              </ReadOnlyValue>
              <ReadOnlyValue label="Contracts on this version">
                <span className="tabular-nums">
                  {versionDetail.contractsUsingVersion}
                </span>
              </ReadOnlyValue>
              <ReadOnlyValue label="Preview checksum">
                {versionDetail.previewChecksum ? (
                  <span
                    className="block truncate font-mono text-xs"
                    title={versionDetail.previewChecksum}
                  >
                    {versionDetail.previewChecksum}
                  </span>
                ) : (
                  <span className="text-muted-foreground">No preview generated</span>
                )}
              </ReadOnlyValue>
              <div className="grid gap-1 sm:col-span-3">
                <dt className="text-muted-foreground text-xs font-semibold">
                  Prefill fields
                </dt>
                <dd className="min-w-0 text-sm break-words">
                  {versionDetail.placeholderKeys.length ? (
                    <span className="flex flex-wrap gap-1">
                      {versionDetail.placeholderKeys.map((key) => (
                        <code
                          key={key}
                          className="bg-card border-border/60 rounded-sm border px-1.5 py-0.5 font-mono text-xs"
                        >
                          {key}
                        </code>
                      ))}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      None yet — place Prefill fields and save the layout.
                    </span>
                  )}
                </dd>
              </div>
              {versionDetail.sourcePdfUrl || versionDetail.previewUrl ? (
                <div className="flex flex-wrap gap-2 sm:col-span-3">
                  {versionDetail.sourcePdfUrl ? (
                    <Button type="button" variant="outline" size="sm" asChild>
                      <a
                        href={versionDetail.sourcePdfUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <FileText className="size-3.5" aria-hidden />
                        Open source PDF
                      </a>
                    </Button>
                  ) : null}
                  {versionDetail.previewUrl ? (
                    <Button type="button" variant="outline" size="sm" asChild>
                      <a
                        href={versionDetail.previewUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Eye className="size-3.5" aria-hidden />
                        Open stored preview
                      </a>
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </dl>
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
