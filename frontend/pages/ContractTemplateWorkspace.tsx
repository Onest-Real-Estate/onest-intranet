import { Head, router, usePage } from "@inertiajs/react";
import {
  Archive,
  BadgeCheck,
  Check,
  CircleDashed,
  Eye,
  FileText,
  Link2,
  MapPin,
  MoreHorizontal,
  PenSquare,
  Save,
  Send,
  Sparkles,
  TriangleAlert,
  Upload,
} from "lucide-react";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ContractTemplateFieldPlacer,
  type TemplateFieldLayoutItem,
} from "@/components/ContractTemplateFieldPlacer";
import {
  Callout,
  EmptyState,
  FileUploader,
  FormActionBar,
  FormErrorSummary,
  PageHeader,
  PanelHeader,
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
import {
  buildReadiness,
  publishBlockReason,
  type WorkbenchStep,
  type WorkbenchStepState,
  type WorkbenchTabId,
} from "@/lib/contract-template-workbench";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { hasValidationErrors } from "@/lib/validation";
import type { ContractTemplateWorkspacePageProps } from "@/types";

const ACCESS = {
  any: ["contract.manage_contract_templates", "contract.approve_contract_templates"],
};

const TABS: Array<{ id: WorkbenchTabId; label: string }> = [
  { id: "document", label: "Document" },
  { id: "mapping", label: "Data mapping" },
  { id: "details", label: "Template details" },
];

const TIMESTAMP = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatTimestamp(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : TIMESTAMP.format(parsed);
}

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

function hasRequiredSignerFields(
  layout: TemplateFieldLayoutItem[],
  role: TemplateFieldLayoutItem["role"],
): boolean {
  let hasSignature = false;
  let hasDate = false;
  for (const field of layout) {
    if (field.role !== role) continue;
    if (field.type === "signature") hasSignature = true;
    if (field.type === "date") hasDate = true;
  }
  return hasSignature && hasDate;
}

/** Position and identity only — a rename or a nudge is a change, a reorder is not. */
function layoutFingerprint(layout: TemplateFieldLayoutItem[]): string {
  return JSON.stringify(
    [...layout]
      .map((item) => [
        item.name,
        item.type,
        item.role,
        item.page,
        Math.round(item.x),
        Math.round(item.y),
        Math.round(item.w),
        Math.round(item.h),
      ])
      .sort((a, b) => String(a).localeCompare(String(b))),
  );
}

export default function ContractTemplateWorkspace() {
  const { versionDetail, capabilities, errors, posted } =
    usePage<ContractTemplateWorkspacePageProps>().props;

  const [activeTab, setActiveTab] = useState<WorkbenchTabId>(
    versionDetail.sourcePdfUrl ? "document" : "details",
  );
  const [mergeRows, setMergeRows] = useState<MergeRow[]>(() =>
    normalizeMergeSchema(versionDetail.mergeSchema ?? []),
  );
  const [fieldLayout, setFieldLayout] = useState<TemplateFieldLayoutItem[]>(() =>
    normalizeLayout(versionDetail.fieldLayout ?? []),
  );
  const [displayName, setDisplayName] = useState(versionDetail.displayName);
  const [description, setDescription] = useState(versionDetail.description);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [savingFields, setSavingFields] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  useEffect(() => {
    setMergeRows(normalizeMergeSchema(versionDetail.mergeSchema ?? []));
    setFieldLayout(normalizeLayout(versionDetail.fieldLayout ?? []));
    setDisplayName(versionDetail.displayName);
    setDescription(versionDetail.description);
    setPendingFile(null);
  }, [
    versionDetail.mergeSchema,
    versionDetail.fieldLayout,
    versionDetail.displayName,
    versionDetail.description,
  ]);

  const savedLayoutPrint = useMemo(
    () => layoutFingerprint(normalizeLayout(versionDetail.fieldLayout ?? [])),
    [versionDetail.fieldLayout],
  );
  const savedMergePrint = useMemo(
    () => JSON.stringify(normalizeMergeSchema(versionDetail.mergeSchema ?? [])),
    [versionDetail.mergeSchema],
  );

  const layoutDirty = layoutFingerprint(fieldLayout) !== savedLayoutPrint;
  const draftDirty =
    displayName !== versionDetail.displayName ||
    description !== versionDetail.description ||
    pendingFile !== null ||
    JSON.stringify(mergeRows) !== savedMergePrint;

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
  const unmappedKeys = mergeRows.filter((row) => !row.source).map((row) => row.key);

  const placementsByName = useMemo(() => {
    const index = new Map<string, number[]>();
    for (const field of fieldLayout) {
      const pages = index.get(field.name);
      if (pages) pages.push(field.page);
      else index.set(field.name, [field.page]);
    }
    return index;
  }, [fieldLayout]);

  const sourceOptions = versionDetail.mergeSourceOptions ?? [];
  const isDraft = versionDetail.status === "draft";
  const canEdit = Boolean(capabilities.canManage && isDraft);
  const hasPreview = Boolean(versionDetail.previewUrl || versionDetail.previewChecksum);
  const hasRequiredAgentFields = hasRequiredSignerFields(fieldLayout, "Agent");
  const hasRequiredCompanyFields = hasRequiredSignerFields(fieldLayout, "Company");

  const readiness = buildReadiness({
    hasSourcePdf: Boolean(versionDetail.sourcePdfUrl),
    placedFieldCount: fieldLayout.length,
    agentFieldCount: fieldLayout.filter((field) => field.role === "Agent").length,
    companyFieldCount: fieldLayout.filter((field) => field.role === "Company").length,
    hasRequiredAgentFields,
    hasRequiredCompanyFields,
    unsavedPrefillNames: prefillAwaitingSave,
    layoutDirty,
    mergeRowCount: mergeRows.length,
    unmappedKeys,
    hasPreview,
    previewStale: hasPreview && (layoutDirty || draftDirty),
  });
  const blockReason = publishBlockReason(readiness);

  function postAction(
    action: "preview" | "suggest_fields" | "publish" | "activate" | "retire",
  ) {
    if (action === "suggest_fields") setSuggesting(true);
    if (action === "preview") setPreviewing(true);
    router.post(
      routes.contract_template_action(versionDetail.id),
      { action },
      {
        preserveScroll: true,
        onFinish: () => {
          setSuggesting(false);
          setPreviewing(false);
        },
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

  function generatePreview() {
    if (!versionDetail.sourcePdfUrl || fieldLayout.length === 0) return;
    // Preview reads the saved layout. Persist current placement first so the
    // document the user sees and the document the server renders cannot drift.
    if (canEdit && layoutDirty) {
      setPreviewing(true);
      setSavingFields(true);
      router.post(
        routes.contract_template_field_layout(versionDetail.id),
        {
          fieldLayoutJson: JSON.stringify(fieldLayout),
          expectedVersion: versionDetail.version,
        },
        {
          preserveScroll: true,
          onSuccess: (page) => {
            const nextErrors = (
              page.props as unknown as ContractTemplateWorkspacePageProps
            ).errors;
            if (hasValidationErrors(nextErrors)) {
              setPreviewing(false);
              return;
            }
            router.post(
              routes.contract_template_action(versionDetail.id),
              { action: "preview" },
              {
                preserveScroll: true,
                onFinish: () => setPreviewing(false),
              },
            );
          },
          onError: () => setPreviewing(false),
          onFinish: () => setSavingFields(false),
        },
      );
      return;
    }
    postAction("preview");
  }

  /**
   * Name, description, source PDF, and the hub-source mapping are one draft
   * record on the server, so they save together no matter which tab the reader
   * edited them on. Inertia switches to multipart on its own once a File is in
   * the payload.
   */
  function saveDraft() {
    setSavingDraft(true);
    router.post(
      routes.contract_template_update(versionDetail.id),
      {
        display_name: displayName,
        description,
        merge_schema_json: JSON.stringify(mergeRows),
        expected_version: versionDetail.version,
        ...(pendingFile ? { source_document: pendingFile } : {}),
      },
      {
        preserveScroll: true,
        onFinish: () => setSavingDraft(false),
      },
    );
  }

  useEffect(() => {
    const suggestions = posted?.fieldSuggestions;
    if (!Array.isArray(suggestions) || suggestions.length === 0) return;
    setFieldLayout(
      normalizeLayout(suggestions as unknown as TemplateFieldLayoutItem[]),
    );
    setActiveTab("document");
  }, [posted]);

  function updateRowSource(key: string, source: string) {
    setMergeRows((rows) =>
      rows.map((row) => (row.key === key ? { ...row, source } : row)),
    );
  }

  /**
   * One gold control that always does whatever the draft is waiting for. The
   * row it replaces held up to five buttons of equal weight, which said the
   * five moves were interchangeable — they are a sequence, and only one of them
   * is available at a time.
   */
  const primaryAction = (() => {
    if (!isDraft && capabilities.canApprove) {
      return {
        label: "Activate this version",
        icon: BadgeCheck,
        onClick: () => postAction("activate"),
      };
    }
    if (readiness.ready && capabilities.canApprove) {
      return { label: "Publish", icon: Send, onClick: () => postAction("publish") };
    }
    const next = readiness.next;
    if (!next) {
      return {
        label: previewing ? "Generating preview…" : "Generate preview",
        icon: Eye,
        onClick: generatePreview,
      };
    }
    if (next.id === "preview") {
      return {
        label: previewing ? "Generating preview…" : "Generate preview",
        icon: Eye,
        onClick: generatePreview,
      };
    }
    // A stage that is stalled on unsaved work needs the save, not a trip to the
    // tab the reader is already looking at.
    if (next.id === "fields" && layoutDirty) {
      return { label: "Save field layout", icon: Save, onClick: saveFieldLayout };
    }
    if (next.id === "mapping" && draftDirty) {
      return { label: "Save draft", icon: Save, onClick: saveDraft };
    }
    const labels: Record<string, { label: string; icon: typeof Upload }> = {
      source: { label: "Upload the source PDF", icon: Upload },
      fields: { label: "Place fields", icon: PenSquare },
      mapping: { label: "Map hub data", icon: Link2 },
    };
    const entry = labels[next.id] ?? { label: "Continue", icon: PenSquare };
    return { ...entry, onClick: () => setActiveTab(next.tab) };
  })();
  const PrimaryIcon = primaryAction.icon;

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head
          title={`${versionDetail.displayName || versionDetail.versionLabel} Template`}
        />
        <PageHeader
          title={versionDetail.displayName || versionDetail.versionLabel}
          description={versionDetail.description || undefined}
          meta={
            <>
              <StatusBadge
                status={{
                  label: versionDetail.statusLabel,
                  tone: toStatusTone(versionDetail.statusTone),
                }}
              />
              <span>{versionDetail.template.name}</span>
              <span aria-hidden>·</span>
              <span className="tabular-nums">{versionDetail.versionLabel}</span>
              <span aria-hidden>·</span>
              <span className="tabular-nums">
                {readiness.doneCount} of {readiness.total} steps ready
              </span>
            </>
          }
          actions={
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
              {versionDetail.sourcePdfUrl &&
              !readiness.ready &&
              readiness.next?.id !== "preview" ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={generatePreview}
                  disabled={fieldLayout.length === 0 || savingFields || previewing}
                >
                  <Eye className="size-4" aria-hidden />
                  {previewing ? "Generating…" : "Generate preview"}
                </Button>
              ) : null}
              <Button
                type="button"
                onClick={primaryAction.onClick}
                disabled={savingFields || previewing}
              >
                <PrimaryIcon className="size-4" aria-hidden />
                {primaryAction.label}
              </Button>
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
                    <DropdownMenuItem
                      onSelect={generatePreview}
                      disabled={savingFields || previewing || fieldLayout.length === 0}
                    >
                      <Eye className="size-4" aria-hidden />
                      Generate preview
                    </DropdownMenuItem>
                    {isDraft ? (
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

        <ReadinessStrip steps={readiness.steps} onGoToTab={setActiveTab} />

        {isDraft && blockReason && capabilities.canApprove ? (
          <p className="text-muted-foreground text-sm">
            Publishing is blocked until this is cleared — {blockReason}.
          </p>
        ) : null}

        <WorkbenchTabs
          active={activeTab}
          onChange={setActiveTab}
          counts={{
            document: fieldLayout.length,
            mapping: mergeRows.length,
            details: null,
          }}
          attention={{
            document: layoutDirty,
            mapping: unmappedKeys.length > 0,
            details: draftDirty || !versionDetail.sourcePdfUrl,
          }}
        />

        <div
          role="tabpanel"
          id="workbench-panel-document"
          aria-labelledby="workbench-tab-document"
          hidden={activeTab !== "document"}
        >
          {activeTab === "document" ? (
            versionDetail.sourcePdfUrl ? (
              <div className="grid gap-4">
                <ContractTemplateFieldPlacer
                  pdfUrl={versionDetail.sourcePdfUrl}
                  value={fieldLayout}
                  onChange={setFieldLayout}
                  readOnly={!canEdit}
                  onSave={canEdit ? saveFieldLayout : undefined}
                  saving={savingFields}
                  dirty={layoutDirty}
                />
                {canEdit && (!hasRequiredCompanyFields || !hasRequiredAgentFields) ? (
                  <Callout tone="warning" title="Both signers need fields">
                    {!hasRequiredCompanyFields
                      ? "Add a Company signature and Company date. "
                      : null}
                    {!hasRequiredAgentFields
                      ? "Add an Agent signature and Agent date. "
                      : null}
                    Save the layout before previewing or publishing.
                  </Callout>
                ) : null}
                {prefillAwaitingSave.length > 0 ? (
                  <Callout
                    tone="info"
                    title="Save the layout to map these"
                    action={
                      canEdit ? (
                        <Button
                          type="button"
                          size="sm"
                          onClick={saveFieldLayout}
                          disabled={savingFields}
                        >
                          {savingFields ? "Saving…" : "Save field layout"}
                        </Button>
                      ) : undefined
                    }
                  >
                    {prefillAwaitingSave.join(", ")} — Prefill fields become mappable
                    once the layout is saved.
                  </Callout>
                ) : null}
              </div>
            ) : (
              <SurfaceCard>
                <EmptyState
                  icon={FileText}
                  title="No source PDF yet"
                  description="The field placer opens once a blank contract PDF is attached to this version."
                  actions={
                    capabilities.canManage ? (
                      <Button type="button" onClick={() => setActiveTab("details")}>
                        <Upload className="size-4" aria-hidden />
                        Upload the source PDF
                      </Button>
                    ) : undefined
                  }
                />
              </SurfaceCard>
            )
          ) : null}
        </div>

        <div
          role="tabpanel"
          id="workbench-panel-mapping"
          aria-labelledby="workbench-tab-mapping"
          hidden={activeTab !== "mapping"}
        >
          {activeTab === "mapping" ? (
            <SurfaceCard>
              <PanelHeader
                divided
                title="Prefill fields to hub data"
                description="Every Prefill box you placed is a slot the Hub fills at generation time. Choose which hub value goes into each one."
                meta={
                  mergeRows.length ? (
                    <span className="text-muted-foreground text-sm tabular-nums">
                      {mergeRows.length - unmappedKeys.length} of {mergeRows.length}{" "}
                      mapped
                    </span>
                  ) : undefined
                }
              />
              <SurfaceCardContent className="grid gap-4">
                {mergeRows.length === 0 ? (
                  <EmptyState
                    compact
                    tone="muted"
                    icon={MapPin}
                    title="Nothing to map yet"
                    description="Place Prefill fields on the document and save the layout — each saved name shows up here."
                    actions={
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setActiveTab("document")}
                      >
                        <PenSquare className="size-4" aria-hidden />
                        Go to the document
                      </Button>
                    }
                  />
                ) : (
                  <>
                    {unmappedKeys.length > 0 ? (
                      <Callout
                        tone="warning"
                        title="Every Prefill field needs a source"
                      >
                        Publish is refused while {unmappedKeys.join(", ")}{" "}
                        {unmappedKeys.length === 1 ? "has" : "have"} no hub source.
                      </Callout>
                    ) : null}
                    <div>
                      <div className="text-muted-foreground text-micro border-border hidden items-center gap-4 border-b pb-2 font-semibold tracking-[0.06em] uppercase @2xl:grid @2xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.7fr)_minmax(0,1.2fr)]">
                        <span>Field on the PDF</span>
                        <span>Where it sits</span>
                        <span>Hub source</span>
                      </div>
                      <ul className="divide-border/70 divide-y">
                        {mergeRows.map((row) => (
                          <li
                            key={row.key}
                            className="grid grid-cols-[minmax(0,1fr)] items-center gap-x-4 gap-y-2 py-3.5 @2xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.7fr)_minmax(0,1.2fr)]"
                          >
                            <div className="min-w-0">
                              {/* A dot, not a filled row. The unmapped ones still
                                  have to be findable in a long list, but tinting
                                  whole rows turns the panel into a warning. */}
                              <p className="flex items-center gap-2 font-mono text-sm font-medium">
                                {!row.source ? (
                                  <span
                                    className="bg-warning size-1.5 shrink-0 rounded-full"
                                    aria-hidden
                                  />
                                ) : null}
                                <span className="truncate">{row.key}</span>
                              </p>
                              <p className="text-muted-foreground truncate text-xs">
                                {row.label && row.label !== row.key
                                  ? `${row.label} · ${row.type}`
                                  : row.type}
                              </p>
                            </div>
                            <PlacementCell
                              pages={placementsByName.get(row.key)}
                              onOpen={() => setActiveTab("document")}
                            />
                            <Select
                              value={row.source || undefined}
                              disabled={!canEdit}
                              onValueChange={(next) => updateRowSource(row.key, next)}
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
                          </li>
                        ))}
                      </ul>
                    </div>
                  </>
                )}
                {canEdit && draftDirty ? (
                  <FormActionBar status="Unsaved changes to this draft.">
                    <Button
                      type="button"
                      variant={draftDirty ? "default" : "outline"}
                      onClick={saveDraft}
                      disabled={savingDraft || !draftDirty}
                    >
                      {savingDraft ? "Saving…" : "Save draft"}
                    </Button>
                  </FormActionBar>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
        </div>

        <div
          role="tabpanel"
          id="workbench-panel-details"
          aria-labelledby="workbench-tab-details"
          hidden={activeTab !== "details"}
        >
          {activeTab === "details" ? (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:items-start">
              <SurfaceCard>
                <PanelHeader
                  divided
                  title="Draft details"
                  description="What this template is called in the Hub, and the blank PDF the contract is drawn on."
                />
                <SurfaceCardContent className="grid gap-5">
                  {capabilities.canManage ? (
                    <>
                      <div className="grid gap-2">
                        <Label htmlFor="display_name">Display name</Label>
                        <Input
                          id="display_name"
                          name="display_name"
                          value={displayName}
                          disabled={!canEdit}
                          onChange={(event) => setDisplayName(event.target.value)}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="description">Description</Label>
                        <Textarea
                          id="description"
                          name="description"
                          rows={4}
                          value={description}
                          disabled={!canEdit}
                          onChange={(event) => setDescription(event.target.value)}
                        />
                        <p className="text-muted-foreground text-xs">
                          Shown to administrators choosing a template. Say what this
                          version is for, not how it works.
                        </p>
                      </div>
                      <div className="grid gap-2">
                        <Label>Source PDF</Label>
                        <FileUploader
                          label={
                            versionDetail.sourcePdfUrl
                              ? "Replace the source PDF"
                              : "Add the blank contract PDF"
                          }
                          description="PDF only. Placed fields keep their coordinates, so re-check them after replacing the source."
                          accept="application/pdf,.pdf"
                          preview={false}
                          disabled={!canEdit}
                          validate={(file) =>
                            file.type === "application/pdf" ||
                            file.name.toLowerCase().endsWith(".pdf")
                              ? null
                              : "Choose a PDF file."
                          }
                          upload={async (file) => {
                            setPendingFile(file);
                            return {
                              name: file.name,
                              size: file.size,
                              type: file.type,
                            };
                          }}
                          onChange={(file) => {
                            if (!file) setPendingFile(null);
                          }}
                        />
                      </div>
                    </>
                  ) : (
                    <Callout tone="neutral" title="Review access">
                      You can preview, publish, and activate this version. Draft edits
                      stay with the template authors.
                    </Callout>
                  )}
                  {!versionDetail.fieldAiConfigured && capabilities.canManage ? (
                    <Callout
                      tone="neutral"
                      title="Field suggestions are not configured"
                    >
                      Set CONTRACT_FIELD_AI_ENDPOINT and CONTRACT_FIELD_AI_API_KEY to
                      have the Hub propose field boxes from the PDF. Manual placement
                      always works.
                    </Callout>
                  ) : null}
                  {canEdit && draftDirty ? (
                    <FormActionBar status="Unsaved changes to this draft.">
                      <Button type="button" onClick={saveDraft} disabled={savingDraft}>
                        {savingDraft ? "Saving…" : "Save draft"}
                      </Button>
                    </FormActionBar>
                  ) : null}
                </SurfaceCardContent>
              </SurfaceCard>

              <SurfaceCard>
                <PanelHeader
                  divided
                  title="This version"
                  description="The record as the server has it, after the last save."
                />
                <SurfaceCardContent>
                  <dl className="divide-border -my-1 divide-y">
                    <RecordRow label="Source format">
                      {versionDetail.sourceFormat || "Not uploaded"}
                    </RecordRow>
                    <RecordRow label="Contracts on this version">
                      <span className="tabular-nums">
                        {versionDetail.contractsUsingVersion}
                      </span>
                    </RecordRow>
                    <RecordRow label="Saved Prefill fields">
                      {versionDetail.placeholderKeys.length ? (
                        <span className="flex flex-wrap gap-1">
                          {versionDetail.placeholderKeys.map((key) => (
                            <code
                              key={key}
                              className="border-border/60 bg-muted rounded-sm border px-1.5 py-0.5 font-mono text-xs"
                            >
                              {key}
                            </code>
                          ))}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">None saved yet</span>
                      )}
                    </RecordRow>
                    <RecordRow label="Preview generated">
                      {formatTimestamp(versionDetail.previewGeneratedAt) ?? (
                        <span className="text-muted-foreground">Never</span>
                      )}
                    </RecordRow>
                    <RecordRow label="Preview checksum">
                      {versionDetail.previewChecksum ? (
                        <span
                          className="block truncate font-mono text-xs"
                          title={versionDetail.previewChecksum}
                        >
                          {versionDetail.previewChecksum}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          No preview generated
                        </span>
                      )}
                    </RecordRow>
                    <RecordRow label="Published">
                      {formatTimestamp(versionDetail.publishedAt) ?? (
                        <span className="text-muted-foreground">Not published</span>
                      )}
                    </RecordRow>
                  </dl>
                  {versionDetail.sourcePdfUrl || versionDetail.previewUrl ? (
                    <div className="border-border mt-4 flex flex-wrap gap-2 border-t pt-4">
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
                </SurfaceCardContent>
              </SurfaceCard>
            </div>
          ) : null}
        </div>

        {/*
          One closing bar for both saves. They hit different endpoints, but a
          reader who has edited a name on one tab and moved a box on another has
          one question — "is my work stored" — and it is answered in one place
          instead of by hunting for two buttons in two panels.
        */}
      </div>
    </PermissionRequired>
  );
}

/**
 * Where a mapped name lives on the paper. A row that says only "PrefillDate" is
 * a string; a row that says "Page 3" is a box the reader can go and look at.
 */
function PlacementCell({
  pages,
  onOpen,
}: {
  pages: number[] | undefined;
  onOpen: () => void;
}) {
  if (!pages || pages.length === 0) {
    return <p className="text-muted-foreground text-xs">Not on the current layout</p>;
  }
  const unique = [...new Set(pages)].sort((a, b) => a - b);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="text-primary focus-visible:ring-ring justify-self-start rounded-sm text-sm font-medium underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:outline-none"
    >
      {unique.length === 1 ? `Page ${unique[0]}` : `Pages ${unique.join(", ")}`}
      {pages.length > 1 ? (
        <span className="text-muted-foreground font-normal">
          {" "}
          · {pages.length} boxes
        </span>
      ) : null}
    </button>
  );
}

function RecordRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-2.5 @md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] @md:items-baseline @md:gap-4">
      <dt className="text-muted-foreground text-xs font-semibold">{label}</dt>
      <dd className="min-w-0 text-sm break-words">{children}</dd>
    </div>
  );
}

const STEP_ICON: Record<WorkbenchStepState, typeof Check> = {
  done: Check,
  attention: TriangleAlert,
  todo: CircleDashed,
};

const STEP_MARK: Record<WorkbenchStepState, string> = {
  done: "border-chip-success-edge bg-chip-success text-success",
  attention: "border-chip-warning-edge bg-chip-warning text-warning-ink",
  todo: "border-border bg-muted text-muted-foreground",
};

/**
 * The pipeline, as one ruled strip rather than four cards.
 *
 * Publishing a template is a sequence with hard gates, and the old page said so
 * only in prose callouts a thousand pixels apart. Four cells on one surface put
 * the whole state on a single baseline and make the stalled stage the one thing
 * that is coloured.
 */
function ReadinessStrip({
  steps,
  onGoToTab,
}: {
  steps: WorkbenchStep[];
  onGoToTab: (tab: WorkbenchTabId) => void;
}) {
  return (
    <ol className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((step) => {
        const Icon = STEP_ICON[step.state];
        return (
          <li key={step.id}>
            <button
              type="button"
              onClick={() => onGoToTab(step.tab)}
              className="focus-visible:ring-ring group -mx-2 flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left transition-colors duration-(--motion-fast) hover:bg-muted/50 focus-visible:ring-3 focus-visible:outline-none"
            >
              <span
                className={cn(
                  "grid size-7 shrink-0 place-items-center rounded-full border",
                  STEP_MARK[step.state],
                )}
              >
                <Icon className="size-3.5" aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">
                  {step.label}
                </span>
                <span
                  className={cn(
                    "block truncate text-xs",
                    step.state === "attention"
                      ? "text-warning-ink"
                      : "text-muted-foreground",
                  )}
                >
                  {step.detail}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * A `tablist`, not a row of buttons: the arrow keys are how a reader expects to
 * move between three views of one record, and a screen reader should say
 * "tab, 2 of 3" rather than reading three unrelated controls.
 */
function WorkbenchTabs({
  active,
  onChange,
  counts,
  attention,
}: {
  active: WorkbenchTabId;
  onChange: (tab: WorkbenchTabId) => void;
  counts: Record<WorkbenchTabId, number | null>;
  attention: Record<WorkbenchTabId, boolean>;
}) {
  const refs = useRef(new Map<WorkbenchTabId, HTMLButtonElement>());

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const offset =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : null;
    if (offset === null) return;
    event.preventDefault();
    const index = TABS.findIndex((tab) => tab.id === active);
    const next = TABS[(index + offset + TABS.length) % TABS.length];
    if (!next) return;
    onChange(next.id);
    refs.current.get(next.id)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Template workspace views"
      onKeyDown={onKeyDown}
      className="border-border flex items-center gap-1 overflow-x-auto border-b"
    >
      {TABS.map((tab) => {
        const selected = tab.id === active;
        const count = counts[tab.id];
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`workbench-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`workbench-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            ref={(node) => {
              if (node) refs.current.set(tab.id, node);
              else refs.current.delete(tab.id);
            }}
            onClick={() => onChange(tab.id)}
            className={cn(
              "focus-visible:ring-ring relative flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-(--motion-fast) focus-visible:ring-3 focus-visible:-outline-offset-2 focus-visible:outline-none",
              selected
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {/* The indicator is its own mark on the rule below, not a border on
                the control — a rounded button carrying a 2px edge on one side
                only fights its own corners. */}
            {selected ? (
              <span
                className="bg-primary absolute inset-x-0 -bottom-px h-0.5"
                aria-hidden
              />
            ) : null}
            {tab.label}
            {count !== null ? (
              <span
                className={cn(
                  "rounded-sm px-1.5 py-0.5 text-xs tabular-nums",
                  selected ? "bg-accent text-foreground" : "bg-muted",
                )}
              >
                {count}
              </span>
            ) : null}
            {attention[tab.id] ? (
              <>
                <span className="bg-warning size-1.5 rounded-full" aria-hidden />
                <span className="sr-only">Needs attention</span>
              </>
            ) : null}
          </button>
        );
      })}
    </div>
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
