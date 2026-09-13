import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CheckCircle2,
  CircleAlert,
  Copy,
  FileText,
  Send,
  Trash2,
  Undo2,
  Upload,
} from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FormActionBar,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  Timeline,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatBytes } from "@/lib/announcements";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type {
  ComplianceAdminDetail,
  ComplianceFileItem,
  ComplianceWorkspacePageProps,
} from "@/types";

const MANAGE = { all: ["web.manage_policies"] };

const FIELD_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  title: "Title",
  summary: "Summary",
  body: "Body",
  category: "Category",
  effective_at: "Effective at",
  expires_at: "Expires at",
  jurisdiction_state_codes: "Jurisdictions",
  is_mandatory: "Mandatory acknowledgement",
  reacknowledge_on_supersede: "Re-acknowledge on supersede",
  acknowledgement_disclosure: "Acknowledgement disclosure",
  disclosure_version: "Disclosure version",
  display_order: "Display order",
  audience: "Audience",
  audience_company: "Audience",
  audience_roles: "Roles",
  audience_regions: "Regions",
  audience_offices: "Offices",
  files: "Files",
};

const ACTIONS_BY_STATE: Record<string, string[]> = {
  draft: ["submit"],
  in_review: ["approve", "return_to_draft"],
  approved: ["publish", "return_to_draft"],
  published: ["retire"],
};

const ACTION_COPY: Record<
  string,
  { label: string; title: string; description: string; confirm: string }
> = {
  submit: {
    label: "Submit for review",
    title: "Submit this policy for review",
    description: "It moves to in-review. Approvers can then approve or return it.",
    confirm: "Submit",
  },
  approve: {
    label: "Approve",
    title: "Approve this policy",
    description: "It becomes ready to publish. Publishing is still a separate step.",
    confirm: "Approve",
  },
  publish: {
    label: "Publish",
    title: "Publish this policy",
    description:
      "It becomes readable by the audience immediately. Mandatory policies create acknowledgement requirements.",
    confirm: "Publish",
  },
  retire: {
    label: "Retire",
    title: "Retire this policy",
    description: "It leaves the library. History and acknowledgements are kept.",
    confirm: "Retire",
  },
  return_to_draft: {
    label: "Return to draft",
    title: "Return this policy to draft",
    description: "It leaves review or approval and can be edited again.",
    confirm: "Return to draft",
  },
};

interface DraftState {
  ownerOffice: string;
  title: string;
  summary: string;
  body: string;
  category: string;
  effectiveAt: string;
  expiresAt: string;
  jurisdictionStateCodes: string;
  isMandatory: boolean;
  reacknowledgeOnSupersede: boolean;
  acknowledgementDisclosure: string;
  disclosureVersion: string;
  displayOrder: string;
  company: boolean;
  roles: string[];
  regions: number[];
  offices: number[];
}

function localDateTime(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatMoment(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

function CheckboxRow({
  id,
  label,
  checked,
  onChange,
  disabled = false,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        id={id}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-primary size-4"
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

function initialDraft(
  policy: ComplianceAdminDetail | null,
  fallbackOffice: number | undefined,
): DraftState {
  const audience = policy?.audience ?? [];
  return {
    ownerOffice: String(policy?.ownerOffice.id ?? fallbackOffice ?? ""),
    title: policy?.title ?? "",
    summary: policy?.summary ?? "",
    body: policy?.body ?? "",
    category: policy?.categoryCode ?? "",
    effectiveAt: localDateTime(policy?.effectiveAt ?? null),
    expiresAt: localDateTime(policy?.expiresAt ?? null),
    jurisdictionStateCodes: (policy?.jurisdictionStateCodes ?? []).join(" "),
    isMandatory: policy?.isMandatory ?? false,
    reacknowledgeOnSupersede: policy?.reacknowledgeOnSupersede ?? false,
    acknowledgementDisclosure: policy?.acknowledgementDisclosure ?? "",
    disclosureVersion: String(policy?.disclosureVersion ?? 1),
    displayOrder: String(policy?.displayOrder ?? 100),
    company: audience.some((entry) => entry.kind === "company"),
    roles: audience.filter((entry) => entry.kind === "role").map((entry) => entry.code),
    regions: audience
      .filter((entry) => entry.kind === "region" && entry.officeId !== null)
      .map((entry) => entry.officeId as number),
    offices: audience
      .filter((entry) => entry.kind === "office" && entry.officeId !== null)
      .map((entry) => entry.officeId as number),
  };
}

function ComplianceWorkspacePage() {
  const {
    policy,
    officeOptions,
    categoryOptions,
    audienceOptions,
    capabilities,
    mediaLimits,
    errors,
  } = usePage<ComplianceWorkspacePageProps>().props;

  const editing = policy !== null;
  const [draft, setDraft] = useState<DraftState>(() =>
    initialDraft(policy, officeOptions[0]?.value),
  );
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [ackDueAt, setAckDueAt] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const statusCode = policy?.statusCode ?? "";
  const lifecycleActions = editing ? (ACTIONS_BY_STATE[statusCode] ?? []) : [];
  const checklist = policy?.validation;
  const immutable =
    statusCode === "published" ||
    statusCode === "superseded" ||
    statusCode === "retired";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const payload: Record<string, string | string[]> = {
      owner_office: draft.ownerOffice,
      title: draft.title,
      summary: draft.summary,
      body: draft.body,
      category: draft.category,
      effective_at: draft.effectiveAt,
      expires_at: draft.expiresAt,
      jurisdiction_state_codes: draft.jurisdictionStateCodes,
      acknowledgement_disclosure: draft.acknowledgementDisclosure,
      disclosure_version: draft.disclosureVersion,
      display_order: draft.displayOrder,
      audience_roles: draft.roles,
      audience_regions: draft.regions.map(String),
      audience_offices: draft.offices.map(String),
      expected_version: policy?.version ?? "",
    };
    if (draft.company) {
      payload.audience_company = "on";
    }
    if (draft.isMandatory) {
      payload.is_mandatory = "on";
    }
    if (draft.reacknowledgeOnSupersede) {
      payload.reacknowledge_on_supersede = "on";
    }
    router.post(
      editing ? routes.policy_admin_update(policy.id) : routes.policy_admin_create(),
      toFormData(payload),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function runAction(action: string) {
    setSubmitting(true);
    setPendingAction(null);
    router.post(
      routes.policy_admin_lifecycle(policy?.id ?? 0),
      toFormData({
        action,
        expected_version: policy?.version ?? "",
        ...(action === "publish" && ackDueAt ? { ack_due_at: ackDueAt } : {}),
      }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function duplicateVersion() {
    setSubmitting(true);
    router.post(
      routes.policy_admin_duplicate(policy?.id ?? 0),
      toFormData({ expected_version: policy?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function uploadFile(file: File) {
    if (!policy) {
      return;
    }
    setSubmitting(true);
    const body = new FormData();
    body.set("file", file);
    body.set("role", "document");
    router.post(routes.policy_admin_file_upload(policy.id), body, {
      forceFormData: true,
      onFinish: () => setSubmitting(false),
    });
  }

  function removeFile(file: ComplianceFileItem) {
    setSubmitting(true);
    router.post(routes.policy_admin_file_remove(file.id), toFormData({}), {
      onFinish: () => setSubmitting(false),
    });
  }

  function actionAllowed(action: string): boolean {
    if (action === "approve") {
      return capabilities.canApprove;
    }
    if (action === "publish" || action === "retire") {
      return capabilities.canPublish;
    }
    return capabilities.canAuthor;
  }

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:items-start">
      <Head title={editing ? policy.title : "New policy"} />

      <div className="grid gap-8">
        {editing ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border px-4 py-3">
            <Badge variant="secondary">{policy.versionLabel}</Badge>
            <span className="text-muted-foreground text-sm">
              Version {policy.versionNumber} of this policy.
            </span>
            {capabilities.canAuthor ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="ml-auto"
                disabled={submitting}
                onClick={duplicateVersion}
              >
                <Copy className="size-4" aria-hidden />
                Duplicate as new version
              </Button>
            ) : null}
          </div>
        ) : null}

        <PageHeader
          title={editing ? policy.title : "New policy"}
          description={
            editing
              ? "Saving changes never notifies anybody. Lifecycle moves are separate, deliberate steps."
              : "Describe the policy first. It reaches nobody until it is published."
          }
          meta={
            editing ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  status={{
                    label: policy.status.label,
                    tone: toStatusTone(policy.status.tone),
                  }}
                />
                <span className="text-muted-foreground text-xs">
                  Last edited {formatMoment(policy.updatedAt)}
                  {policy.updatedBy ? ` by ${policy.updatedBy}` : ""}
                </span>
              </span>
            ) : undefined
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.admin_compliance()}>Back to list</Link>
            </Button>
          }
        />

        <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

        <form className="grid gap-8" onSubmit={submit} noValidate>
          <SurfaceCard>
            <PanelHeader divided title="The policy" />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="title" required>
                  Title
                </FormLabel>
                <Input
                  id="title"
                  value={draft.title}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, title: event.target.value })
                  }
                  {...fieldA11yProps("title", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "title")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="summary" optional>
                  Summary
                </FormLabel>
                <Textarea
                  id="summary"
                  rows={2}
                  value={draft.summary}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, summary: event.target.value })
                  }
                  {...fieldA11yProps("summary", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "summary")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="body" optional>
                  Body
                </FormLabel>
                <Textarea
                  id="body"
                  rows={10}
                  value={draft.body}
                  disabled={immutable}
                  onChange={(event) => setDraft({ ...draft, body: event.target.value })}
                  {...fieldA11yProps("body", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "body")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="owner_office" required>
                  Owning office
                </FormLabel>
                <Select
                  value={draft.ownerOffice || undefined}
                  disabled={editing || immutable}
                  onValueChange={(value) => setDraft({ ...draft, ownerOffice: value })}
                >
                  <SelectTrigger
                    id="owner_office"
                    {...fieldA11yProps("owner_office", errors)}
                  >
                    <SelectValue placeholder="Choose an office" />
                  </SelectTrigger>
                  <SelectContent>
                    {officeOptions.map((option) => (
                      <SelectItem key={option.value} value={String(option.value)}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormFieldError message={firstFieldError(errors, "owner_office")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="category" optional>
                  Category
                </FormLabel>
                <Select
                  value={draft.category || "none"}
                  disabled={immutable}
                  onValueChange={(value) =>
                    setDraft({ ...draft, category: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="category" {...fieldA11yProps("category", errors)}>
                    <SelectValue placeholder="Choose a category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No category</SelectItem>
                    {categoryOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormFieldError message={firstFieldError(errors, "category")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="effective_at" optional>
                  Effective at
                </FormLabel>
                <Input
                  id="effective_at"
                  type="datetime-local"
                  value={draft.effectiveAt}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, effectiveAt: event.target.value })
                  }
                  {...fieldA11yProps("effective_at", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "effective_at")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="expires_at" optional>
                  Expires at
                </FormLabel>
                <Input
                  id="expires_at"
                  type="datetime-local"
                  value={draft.expiresAt}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, expiresAt: event.target.value })
                  }
                  {...fieldA11yProps("expires_at", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "expires_at")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="jurisdiction_state_codes" optional>
                  Jurisdiction state codes
                </FormLabel>
                <Input
                  id="jurisdiction_state_codes"
                  value={draft.jurisdictionStateCodes}
                  disabled={immutable}
                  placeholder="e.g. CA NY TX — empty means all"
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      jurisdictionStateCodes: event.target.value.toUpperCase(),
                    })
                  }
                  {...fieldA11yProps("jurisdiction_state_codes", errors)}
                />
                <FormDescription>
                  Comma- or space-separated US state codes. Empty means all
                  jurisdictions.
                </FormDescription>
                <FormFieldError
                  message={firstFieldError(errors, "jurisdiction_state_codes")}
                />
              </FormField>

              <FormField>
                <FormLabel htmlFor="display_order" optional>
                  Display order
                </FormLabel>
                <Input
                  id="display_order"
                  type="number"
                  value={draft.displayOrder}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, displayOrder: event.target.value })
                  }
                  {...fieldA11yProps("display_order", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "display_order")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="disclosure_version" optional>
                  Disclosure version
                </FormLabel>
                <Input
                  id="disclosure_version"
                  type="number"
                  min={1}
                  value={draft.disclosureVersion}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({ ...draft, disclosureVersion: event.target.value })
                  }
                  {...fieldA11yProps("disclosure_version", errors)}
                />
                <FormFieldError
                  message={firstFieldError(errors, "disclosure_version")}
                />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="acknowledgement_disclosure" optional>
                  Acknowledgement disclosure
                </FormLabel>
                <Textarea
                  id="acknowledgement_disclosure"
                  rows={3}
                  value={draft.acknowledgementDisclosure}
                  disabled={immutable}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      acknowledgementDisclosure: event.target.value,
                    })
                  }
                  {...fieldA11yProps("acknowledgement_disclosure", errors)}
                />
                <FormFieldError
                  message={firstFieldError(errors, "acknowledgement_disclosure")}
                />
              </FormField>

              <div className="sm:col-span-2 grid gap-3">
                <CheckboxRow
                  id="is_mandatory"
                  label="Require acknowledgement when published"
                  checked={draft.isMandatory}
                  disabled={immutable}
                  onChange={(checked) => setDraft({ ...draft, isMandatory: checked })}
                />
                <CheckboxRow
                  id="reacknowledge_on_supersede"
                  label="Require re-acknowledgement when a new version supersedes this one"
                  checked={draft.reacknowledgeOnSupersede}
                  disabled={immutable}
                  onChange={(checked) =>
                    setDraft({ ...draft, reacknowledgeOnSupersede: checked })
                  }
                />
              </div>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Audience"
              description="Who can see this policy once it is published."
            />
            <SurfaceCardContent className="grid gap-4">
              {audienceOptions.canTargetCompany ? (
                <CheckboxRow
                  id="audience_company"
                  label="Everyone at the brokerage"
                  checked={draft.company}
                  disabled={immutable}
                  onChange={(checked) => setDraft({ ...draft, company: checked })}
                />
              ) : null}
              <FormFieldError message={firstFieldError(errors, "audience_company")} />

              {audienceOptions.roles.length > 0 ? (
                <div className="grid gap-2">
                  <FormLabel optional>Roles</FormLabel>
                  <div className="flex flex-wrap gap-3">
                    {audienceOptions.roles.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`role-${option.value}`}
                        label={option.label}
                        checked={draft.roles.includes(option.value)}
                        disabled={immutable}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            roles: toggle(draft.roles, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                </div>
              ) : null}

              {audienceOptions.regions.length > 0 ? (
                <div className="grid gap-2">
                  <FormLabel optional>Regions</FormLabel>
                  <div className="flex flex-wrap gap-3">
                    {audienceOptions.regions.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`region-${option.value}`}
                        label={option.label}
                        checked={draft.regions.includes(option.value)}
                        disabled={immutable}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            regions: toggle(draft.regions, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                </div>
              ) : null}

              {audienceOptions.offices.length > 0 ? (
                <div className="grid gap-2">
                  <FormLabel optional>Offices</FormLabel>
                  <div className="flex flex-wrap gap-3">
                    {audienceOptions.offices.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`office-${option.value}`}
                        label={option.label}
                        checked={draft.offices.includes(option.value)}
                        disabled={immutable}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            offices: toggle(draft.offices, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          {!immutable && capabilities.canAuthor ? (
            <FormActionBar
              status={
                submitting
                  ? "Saving your changes…"
                  : "Saving stores a draft. Nobody is notified until it is published."
              }
            >
              <Button
                type="submit"
                disabled={submitting}
                aria-busy={submitting || undefined}
              >
                {submitting ? "Saving…" : editing ? "Save changes" : "Save draft"}
              </Button>
              <Button type="button" variant="outline" asChild>
                <Link href={routes.admin_compliance()}>Cancel</Link>
              </Button>
            </FormActionBar>
          ) : null}
        </form>
      </div>

      <div className="grid gap-8">
        {editing && checklist ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Ready to publish?"
              description="Outstanding items block publish until they are cleared."
            />
            <SurfaceCardContent>
              {checklist.isPublishable ? (
                <p className="text-sm flex items-start gap-2">
                  <CheckCircle2
                    className="text-success size-4 shrink-0 mt-0.5"
                    aria-hidden
                  />
                  Nothing outstanding — this version can be published.
                </p>
              ) : (
                <ul className="grid gap-2">
                  {checklist.items.map((item) => (
                    <li
                      key={`${item.field}-${item.message}`}
                      className="flex items-start gap-2 text-sm"
                    >
                      <CircleAlert
                        className="text-warning-ink mt-0.5 size-4 shrink-0"
                        aria-hidden
                      />
                      <span className="grid gap-0.5">
                        <strong className="text-foreground">
                          {FIELD_LABELS[item.field] ?? item.field}
                        </strong>
                        <span>{item.message}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Documents"
              description={`Up to ${mediaLimits.document.maxCount} files · ${formatBytes(mediaLimits.document.maxBytes)} each.`}
            />
            <SurfaceCardContent className="grid gap-3">
              {(policy.files.documents.length === 0 ? [] : policy.files.documents).map(
                (file) => (
                  <div
                    key={file.id}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <FileText className="size-4 shrink-0" aria-hidden />
                      <span className="truncate">{file.displayName}</span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {formatBytes(file.byteSize)}
                      </span>
                    </span>
                    {!immutable && capabilities.canAuthor ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={submitting}
                        onClick={() => removeFile(file)}
                      >
                        <Trash2 className="size-3.5" aria-hidden />
                        <span className="sr-only">Remove {file.displayName}</span>
                      </Button>
                    ) : null}
                  </div>
                ),
              )}
              {!immutable && capabilities.canAuthor ? (
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) {
                        uploadFile(file);
                      }
                      event.target.value = "";
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={submitting}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="size-4" aria-hidden />
                    Upload document
                  </Button>
                </div>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && lifecycleActions.some(actionAllowed) ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Lifecycle"
              description="Each move is explicit, audited, and refused if somebody else changed the record first."
            />
            <SurfaceCardContent className="flex flex-wrap gap-2">
              {lifecycleActions.filter(actionAllowed).map((action) => (
                <Button
                  key={action}
                  type="button"
                  variant={action === "publish" ? "default" : "outline"}
                  disabled={
                    submitting || (action === "publish" && !checklist?.isPublishable)
                  }
                  onClick={() => setPendingAction(action)}
                >
                  {action === "publish" || action === "submit" ? (
                    <Send className="size-4" aria-hidden />
                  ) : (
                    <Undo2 className="size-4" aria-hidden />
                  )}
                  {ACTION_COPY[action].label}
                </Button>
              ))}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && policy.history.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Publication history"
              description="Read from the audit trail — the same record governance answers from."
            />
            <SurfaceCardContent>
              <Timeline
                items={policy.history.map((entry) => ({
                  id: entry.id,
                  title: entry.label,
                  description: entry.actor,
                  meta: formatMoment(entry.occurredAt),
                  tone: entry.tone,
                }))}
              />
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>

      <Dialog
        open={pendingAction !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingAction(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {pendingAction ? ACTION_COPY[pendingAction].title : ""}
            </DialogTitle>
            <DialogDescription>
              {pendingAction ? ACTION_COPY[pendingAction].description : ""}
            </DialogDescription>
          </DialogHeader>
          {pendingAction === "publish" && policy?.isMandatory ? (
            <FormField>
              <FormLabel htmlFor="ack_due_at" optional>
                Acknowledgement due
              </FormLabel>
              <Input
                id="ack_due_at"
                type="datetime-local"
                value={ackDueAt}
                onChange={(event) => setAckDueAt(event.target.value)}
              />
              <FormDescription>
                Leave blank to use the default acknowledgement window.
              </FormDescription>
            </FormField>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={submitting}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="button"
              disabled={submitting}
              aria-busy={submitting || undefined}
              onClick={() => pendingAction && runAction(pendingAction)}
            >
              {pendingAction ? ACTION_COPY[pendingAction].confirm : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function ComplianceWorkspace() {
  return (
    <PermissionRequired permission={MANAGE}>
      <ComplianceWorkspacePage />
    </PermissionRequired>
  );
}

ComplianceWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Compliance workspace",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Compliance administration",
            href: routes.admin_compliance(),
          },
          { label: "Workspace" },
        ],
      },
      variant: "standard",
    },
  ] as const;
