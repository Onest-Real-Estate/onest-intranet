import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Archive,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Copy,
  Eye,
  FileText,
  Send,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
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
  DocumentsAdminDetail,
  DocumentsRecipientResult,
  DocumentsWorkspacePageProps,
} from "@/types";

const MANAGE = { all: ["web.manage_documents"] };

const FIELD_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  name: "Name",
  description: "Description",
  category: "Category",
  effective_at: "Effective at",
  expires_at: "Expires at",
  jurisdiction_state_codes: "Jurisdictions",
  display_order: "Display order",
  audience: "Audience",
  audience_company: "Audience",
  audience_roles: "Roles",
  audience_regions: "Regions",
  audience_offices: "Offices",
  audience_users: "Named people",
  files: "Files",
};

const ACTIONS_BY_STATE: Record<string, string[]> = {
  draft: ["publish", "schedule"],
  scheduled: [],
  live: ["retire"],
  expired: ["retire"],
  superseded: [],
  retired: [],
};

const ACTION_COPY: Record<
  string,
  { label: string; title: string; description: string; confirm: string }
> = {
  publish: {
    label: "Publish now",
    title: "Publish this document",
    description:
      "It becomes the current library version for this family. Check the preview first.",
    confirm: "Publish",
  },
  schedule: {
    label: "Schedule",
    title: "Schedule this document",
    description:
      "It stays hidden until the effective time you set, then becomes current. The previous live version expires at that moment.",
    confirm: "Schedule",
  },
  retire: {
    label: "Retire",
    title: "Retire this document",
    description: "It leaves the library. Files, history, and audit records are kept.",
    confirm: "Retire",
  },
};

interface DraftState {
  ownerOffice: string;
  name: string;
  description: string;
  category: string;
  effectiveAt: string;
  expiresAt: string;
  jurisdictionStateCodes: string;
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
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-primary size-4"
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

function RecipientPicker({
  chosen,
  onToggle,
}: {
  chosen: { id: number; name: string }[];
  onToggle: (person: { id: number; name: string }) => void;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<DocumentsRecipientResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const query = term.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearching(true);
      fetch(
        `${routes.document_admin_recipient_search()}?q=${encodeURIComponent(query)}`,
        { signal: controller.signal, headers: { Accept: "application/json" } },
      )
        .then((response) => (response.ok ? response.json() : { results: [] }))
        .then((data) => setResults(data.results ?? []))
        .catch(() => undefined)
        .finally(() => setSearching(false));
    }, 250);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [term]);

  return (
    <div className="grid gap-2">
      <FormLabel htmlFor="audience_users" optional>
        Search people
      </FormLabel>
      <Input
        id="audience_users"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder="Search people you administer"
        aria-describedby="audience_users_help"
      />
      <FormDescription id="audience_users_help">
        Type at least two characters. Only people inside your own grant appear.
      </FormDescription>
      <p aria-live="polite" className="sr-only">
        {searching ? "Searching" : `${results.length} people found`}
      </p>
      {results.length > 0 ? (
        <ul className="border-border/60 grid max-h-48 gap-1 overflow-y-auto rounded-lg border p-2">
          {results.map((person) => (
            <li key={person.id}>
              <CheckboxRow
                id={`recipient_${person.id}`}
                label={`${person.name} · ${person.officeName || "No office"}`}
                checked={chosen.some((item) => item.id === person.id)}
                onChange={() => onToggle({ id: person.id, name: person.name })}
              />
            </li>
          ))}
        </ul>
      ) : null}
      {chosen.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {chosen.map((person) => (
            <li key={person.id}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onToggle(person)}
              >
                {person.name}
                <span className="sr-only">Remove {person.name}</span>
                <span aria-hidden>×</span>
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function DocumentsWorkspacePage() {
  const {
    document: current,
    officeOptions,
    categoryOptions,
    audienceOptions,
    capabilities,
    preview,
    errors,
  } = usePage<DocumentsWorkspacePageProps>().props;

  const editing = current !== null;
  const locked = editing && current.status.code !== "draft";
  const [draft, setDraft] = useState<DraftState>(() =>
    initialDraft(current, officeOptions[0]?.value),
  );
  const [people, setPeople] = useState<{ id: number; name: string }[]>(() =>
    (current?.audience ?? [])
      .filter((entry) => entry.kind === "user" && entry.userId !== null)
      .map((entry) => ({ id: entry.userId as number, name: entry.label })),
  );
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const lifecycleActions = useMemo(
    () => (current ? (ACTIONS_BY_STATE[current.lifecycle.code] ?? []) : []),
    [current],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const payload: Record<string, string | string[]> = {
      owner_office: draft.ownerOffice,
      name: draft.name,
      description: draft.description,
      category: draft.category,
      effective_at: draft.effectiveAt,
      expires_at: draft.expiresAt,
      jurisdiction_state_codes: draft.jurisdictionStateCodes,
      display_order: draft.displayOrder,
      audience_roles: draft.roles,
      audience_regions: draft.regions.map(String),
      audience_offices: draft.offices.map(String),
      audience_users: people.map((person) => String(person.id)),
      expected_version: current?.version ?? "",
    };
    if (draft.company) {
      payload.audience_company = "on";
    }
    router.post(
      editing
        ? routes.document_admin_update(current.id)
        : routes.document_admin_create(),
      toFormData(payload),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function runAction(action: string) {
    setSubmitting(true);
    setPendingAction(null);
    router.post(
      routes.document_admin_lifecycle(current?.id ?? 0),
      toFormData({ action, expected_version: current?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function duplicateVersion() {
    setSubmitting(true);
    router.post(
      routes.document_admin_duplicate(current?.id ?? 0),
      toFormData({ expected_version: current?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function previewAs(patch: { office?: string; role?: string }) {
    router.get(
      routes.document_admin_edit(current?.id ?? 0),
      {
        previewOffice:
          patch.office ?? (preview?.officeId != null ? String(preview.officeId) : ""),
        previewRole: patch.role ?? preview?.roleCode ?? "",
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const checklist = current?.validation;
  const usage = current?.usage;

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:items-start">
      <Head title={editing ? current.name : "New document"} />

      <div className="grid gap-8">
        {editing ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border px-4 py-3">
            <Badge variant="secondary">{current.versionLabel}</Badge>
            <span className="text-muted-foreground text-sm">
              Version {current.versionNumber} of {current.key}.
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
          title={editing ? current.name : "New document"}
          description={
            editing
              ? locked
                ? "Published versions are immutable. Duplicate as a new version to replace the file or change the audience."
                : "Saving changes never notifies anybody. Publishing and retirement are separate, deliberate steps."
              : "Describe the document first. It reaches nobody until somebody with the publication grant publishes it."
          }
          meta={
            editing ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  status={{
                    label: current.lifecycle.label,
                    tone: toStatusTone(current.lifecycle.tone),
                  }}
                />
                <span className="text-muted-foreground text-xs">
                  Last edited {formatMoment(current.updatedAt)}
                  {current.updatedBy ? ` by ${current.updatedBy}` : ""}
                </span>
              </span>
            ) : undefined
          }
          actions={
            editing ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={routes.document_admin_media(current.id)}>
                  <FileText className="size-4" aria-hidden />
                  Files
                </Link>
              </Button>
            ) : undefined
          }
        />

        <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

        <form className="grid gap-8" onSubmit={submit} noValidate>
          <SurfaceCard>
            <PanelHeader divided title="The document" />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="name" required>
                  Name
                </FormLabel>
                <Input
                  id="name"
                  value={draft.name}
                  disabled={locked}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  {...fieldA11yProps("name", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "name")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="description" optional>
                  Description
                </FormLabel>
                <Textarea
                  id="description"
                  rows={3}
                  value={draft.description}
                  disabled={locked}
                  onChange={(event) =>
                    setDraft({ ...draft, description: event.target.value })
                  }
                  {...fieldA11yProps("description", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "description")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="owner_office" required>
                  Owning office
                </FormLabel>
                <Select
                  value={draft.ownerOffice}
                  disabled={editing}
                  onValueChange={(value) => setDraft({ ...draft, ownerOffice: value })}
                >
                  <SelectTrigger id="owner_office">
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
                <FormDescription>
                  Who is publishing. Permanent once saved.
                </FormDescription>
                <FormFieldError message={firstFieldError(errors, "owner_office")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="category">Category</FormLabel>
                <Select
                  value={draft.category || "none"}
                  disabled={locked}
                  onValueChange={(value) =>
                    setDraft({ ...draft, category: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="category">
                    <SelectValue placeholder="Choose a category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not chosen yet</SelectItem>
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
                <FormLabel htmlFor="display_order" optional>
                  Display order
                </FormLabel>
                <Input
                  id="display_order"
                  type="number"
                  value={draft.displayOrder}
                  disabled={locked}
                  onChange={(event) =>
                    setDraft({ ...draft, displayOrder: event.target.value })
                  }
                  {...fieldA11yProps("display_order", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "display_order")} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Window"
              description="Leave both empty for a document that goes live on publish and never expires."
            />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="effective_at" optional>
                  Effective at
                </FormLabel>
                <Input
                  id="effective_at"
                  type="datetime-local"
                  value={draft.effectiveAt}
                  disabled={locked}
                  onChange={(event) =>
                    setDraft({ ...draft, effectiveAt: event.target.value })
                  }
                  {...fieldA11yProps("effective_at", errors, "effective_at_help")}
                />
                <FormDescription id="effective_at_help">
                  A future time here is what makes “Schedule” available.
                </FormDescription>
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
                  disabled={locked}
                  onChange={(event) =>
                    setDraft({ ...draft, expiresAt: event.target.value })
                  }
                  {...fieldA11yProps("expires_at", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "expires_at")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="jurisdiction_state_codes" optional>
                  Jurisdictions
                </FormLabel>
                <Input
                  id="jurisdiction_state_codes"
                  value={draft.jurisdictionStateCodes}
                  disabled={locked}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      jurisdictionStateCodes: event.target.value,
                    })
                  }
                  {...fieldA11yProps("jurisdiction_state_codes", errors)}
                />
                <FormDescription>
                  Space-separated state codes. Empty means every state — only
                  brokerage-wide publishers may leave it empty.
                </FormDescription>
                <FormFieldError
                  message={firstFieldError(errors, "jurisdiction_state_codes")}
                />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Audience"
              description="Anyone matching any selector can see it. You can only pick targets inside your grant."
            />
            <SurfaceCardContent className="grid gap-4">
              <CheckboxRow
                id="audience_company"
                label="Everyone at the brokerage"
                checked={draft.company}
                onChange={(checked) =>
                  !locked && setDraft({ ...draft, company: checked })
                }
              />
              {!audienceOptions.canTargetCompany ? (
                <FormDescription>
                  Only a brokerage-wide administrator can address everyone.
                </FormDescription>
              ) : null}

              {audienceOptions.regions.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-xs font-semibold">Regions</legend>
                  {audienceOptions.regions.map((option) => (
                    <CheckboxRow
                      key={option.value}
                      id={`region_${option.value}`}
                      label={option.label}
                      checked={draft.regions.includes(Number(option.value))}
                      onChange={() =>
                        !locked &&
                        setDraft({
                          ...draft,
                          regions: toggle(draft.regions, Number(option.value)),
                        })
                      }
                    />
                  ))}
                </fieldset>
              ) : null}

              {audienceOptions.offices.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-xs font-semibold">Offices</legend>
                  {audienceOptions.offices.map((option) => (
                    <CheckboxRow
                      key={option.value}
                      id={`office_${option.value}`}
                      label={option.label}
                      checked={draft.offices.includes(Number(option.value))}
                      onChange={() =>
                        !locked &&
                        setDraft({
                          ...draft,
                          offices: toggle(draft.offices, Number(option.value)),
                        })
                      }
                    />
                  ))}
                </fieldset>
              ) : null}

              {audienceOptions.roles.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-xs font-semibold">Roles</legend>
                  {audienceOptions.roles.map((option) => (
                    <CheckboxRow
                      key={option.value}
                      id={`role_${option.value}`}
                      label={option.label}
                      checked={draft.roles.includes(option.value)}
                      onChange={() =>
                        !locked &&
                        setDraft({
                          ...draft,
                          roles: toggle(draft.roles, option.value),
                        })
                      }
                    />
                  ))}
                </fieldset>
              ) : null}

              {!locked ? (
                <RecipientPicker
                  chosen={people}
                  onToggle={(person) =>
                    setPeople((currentPeople) =>
                      currentPeople.some((item) => item.id === person.id)
                        ? currentPeople.filter((item) => item.id !== person.id)
                        : [...currentPeople, person],
                    )
                  }
                />
              ) : null}
              <FormFieldError message={firstFieldError(errors, "audience_company")} />
            </SurfaceCardContent>
          </SurfaceCard>

          <FormActionBar
            status={
              submitting
                ? "Saving your changes…"
                : locked
                  ? "This version is immutable."
                  : "Saving stores a draft. Nobody is notified until it is published."
            }
          >
            <Button
              type="submit"
              disabled={submitting || locked}
              aria-busy={submitting || undefined}
            >
              {submitting ? "Saving…" : editing ? "Save changes" : "Save draft"}
            </Button>
            <Button type="button" variant="outline" asChild>
              <Link href={routes.admin_documents()}>Cancel</Link>
            </Button>
          </FormActionBar>
        </form>
      </div>

      <div className="grid gap-8">
        {editing && checklist ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Before it can go out"
              description="Everything the server checks at publish, listed while there is still time to fix it."
            />
            <SurfaceCardContent>
              {checklist.isPublishable ? (
                <p className="text-success flex items-center gap-2 text-sm">
                  <CheckCircle2 className="size-4 shrink-0" aria-hidden />
                  Nothing outstanding — this is ready to publish.
                </p>
              ) : (
                <ul className="grid gap-2">
                  {checklist.items.map((item) => (
                    <li
                      key={`${item.field}-${item.message}`}
                      className="text-muted-foreground flex items-start gap-2 text-sm"
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
              title="Files"
              description="Protected downloads use the same authorization as the library."
            />
            <SurfaceCardContent className="grid gap-3">
              <p className="text-muted-foreground text-sm">
                {current.files.length} file{current.files.length === 1 ? "" : "s"}
              </p>
              {current.files.length > 0 ? (
                <ul className="grid gap-2">
                  {current.files.map((file) => (
                    <li
                      key={file.id}
                      className="flex items-center justify-between gap-2 text-sm"
                    >
                      <span className="truncate">{file.displayName}</span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {formatBytes(file.byteSize)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              <Button variant="outline" size="sm" asChild>
                <Link href={routes.document_admin_media(current.id)}>Manage files</Link>
              </Button>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && lifecycleActions.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Lifecycle"
              description="Each move is explicit, audited, and refused if somebody else changed the record first."
            />
            <SurfaceCardContent className="flex flex-wrap gap-2">
              {lifecycleActions.map((action) => {
                const allowed =
                  action === "retire"
                    ? capabilities.canRetire
                    : capabilities.canPublish;
                return (
                  <Button
                    key={action}
                    type="button"
                    variant={action === "publish" ? "default" : "outline"}
                    disabled={
                      submitting ||
                      !allowed ||
                      (action === "publish" && !checklist?.isPublishable) ||
                      (action === "schedule" && !draft.effectiveAt)
                    }
                    onClick={() => setPendingAction(action)}
                  >
                    {action === "publish" ? (
                      <Send className="size-4" aria-hidden />
                    ) : action === "schedule" ? (
                      <CalendarClock className="size-4" aria-hidden />
                    ) : (
                      <Archive className="size-4" aria-hidden />
                    )}
                    {ACTION_COPY[action].label}
                  </Button>
                );
              })}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
        {editing && !capabilities.canPublish && !capabilities.canRetire ? (
          <p className="text-muted-foreground text-sm">
            You can edit this draft. Publishing, scheduling, and retirement need their
            own grants.
          </p>
        ) : null}

        {editing && preview ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Preview"
              description="What a recipient would see. Previewing never makes the draft reachable."
            />
            <SurfaceCardContent className="grid gap-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField>
                  <FormLabel htmlFor="preview_office">Preview as office</FormLabel>
                  <Select
                    value={preview.officeId != null ? String(preview.officeId) : "none"}
                    onValueChange={(value) =>
                      previewAs({ office: value === "none" ? "" : value })
                    }
                  >
                    <SelectTrigger id="preview_office">
                      <SelectValue placeholder="Choose an office" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No office</SelectItem>
                      {officeOptions.map((option) => (
                        <SelectItem key={option.value} value={String(option.value)}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
                <FormField>
                  <FormLabel htmlFor="preview_role">Preview as role</FormLabel>
                  <Select
                    value={preview.roleCode || "none"}
                    onValueChange={(value) =>
                      previewAs({ role: value === "none" ? "" : value })
                    }
                  >
                    <SelectTrigger id="preview_role">
                      <SelectValue placeholder="Choose a role" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No role</SelectItem>
                      {audienceOptions.roles.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
              </div>

              {preview.reach.chosen ? (
                <p
                  aria-live="polite"
                  className="flex items-start gap-2 rounded-lg border px-3 py-2 text-sm"
                >
                  <Eye className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {preview.reach.matched
                    ? "This reader would see the document."
                    : "This reader would not see the document."}
                </p>
              ) : (
                <EmptyState
                  icon={Eye}
                  title="Choose a reader"
                  description="Pick an office or a role above to check whether the audience reaches them."
                />
              )}

              <div className="grid gap-2 rounded-lg border p-4">
                {preview.article.category ? (
                  <StatusBadge
                    status={{
                      label: preview.article.category.label,
                      tone: toStatusTone(preview.article.category.tone),
                    }}
                  />
                ) : null}
                <h3 className="text-base font-semibold">{preview.article.name}</h3>
                {preview.article.description ? (
                  <p className="text-muted-foreground text-sm">
                    {preview.article.description}
                  </p>
                ) : null}
                <p className="text-muted-foreground text-xs">
                  {preview.article.fileCount} file
                  {preview.article.fileCount === 1 ? "" : "s"} available to download
                </p>
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && current.history.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Publication history"
              description="Read from the audit trail — the same record governance answers from."
            />
            <SurfaceCardContent>
              <Timeline
                items={current.history.map((entry) => ({
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
              {pendingAction === "retire" && usage
                ? `${ACTION_COPY.retire.description} ${usage.familyKey} v${usage.versionNumber} has ${usage.fileCount} files and ${usage.downloadCount} recorded downloads.${usage.wouldLeaveFamilyWithoutCurrent ? " This is the current library version — retiring it leaves the family without a live form until another version is published." : ""}`
                : pendingAction
                  ? ACTION_COPY[pendingAction].description
                  : ""}
            </DialogDescription>
          </DialogHeader>
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

function initialDraft(
  document: DocumentsAdminDetail | null,
  fallbackOffice: number | undefined,
): DraftState {
  const audience = document?.audience ?? [];
  return {
    ownerOffice: String(document?.ownerOffice.id ?? fallbackOffice ?? ""),
    name: document?.name ?? "",
    description: document?.description ?? "",
    category: document?.categoryCode ?? "",
    effectiveAt: localDateTime(document?.effectiveAt ?? null),
    expiresAt: localDateTime(document?.expiresAt ?? null),
    jurisdictionStateCodes: (document?.jurisdictionStateCodes ?? []).join(" "),
    displayOrder: document?.displayOrder != null ? String(document.displayOrder) : "",
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

export default function DocumentsWorkspace() {
  return (
    <PermissionRequired permission={MANAGE}>
      <DocumentsWorkspacePage />
    </PermissionRequired>
  );
}

DocumentsWorkspace.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Documents",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Documents", href: routes.admin_documents() },
        ],
      },
    },
  ] as const;
