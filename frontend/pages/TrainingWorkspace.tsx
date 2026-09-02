import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Copy,
  Eye,
  Images,
  Send,
  Undo2,
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
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { TrainingArticle } from "@/components/training/TrainingArticle";
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
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type {
  TrainingAdminDetail,
  TrainingRecipientResult,
  TrainingWorkspacePageProps,
} from "@/types";

const MANAGE = { all: ["web.manage_training"] };

const FIELD_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  title: "Title",
  summary: "Summary",
  body: "Body",
  category: "Category",
  content_type: "Content type",
  tool_code: "Tool",
  estimated_minutes: "Estimated minutes",
  external_url: "External link",
  is_required: "Required",
  publish_at: "Publishes at",
  expires_at: "Expires at",
  audience_company: "Audience",
  audience_roles: "Roles",
  audience_regions: "Regions",
  audience_offices: "Offices",
  audience_users: "Named people",
};

const ACTIONS_BY_STATE: Record<string, string[]> = {
  draft: ["publish", "schedule", "archive"],
  scheduled: ["unpublish", "archive"],
  live: ["unpublish", "archive"],
  expired: ["unpublish", "archive"],
  archived: ["restore"],
};

const ACTION_COPY: Record<
  string,
  { label: string; title: string; description: string; confirm: string }
> = {
  publish: {
    label: "Publish now",
    title: "Publish this training",
    description:
      "It becomes readable immediately by everyone the audience reaches. Check the preview first.",
    confirm: "Publish",
  },
  schedule: {
    label: "Schedule",
    title: "Schedule this training",
    description:
      "It stays hidden until the publish time you set, then appears on its own.",
    confirm: "Schedule",
  },
  unpublish: {
    label: "Return to draft",
    title: "Return this training to draft",
    description:
      "It leaves the library straight away and the publication date is cleared.",
    confirm: "Return to draft",
  },
  archive: {
    label: "Archive",
    title: "Archive this training",
    description:
      "It leaves the library for good. The record, its files, and its history are kept.",
    confirm: "Archive",
  },
  restore: {
    label: "Restore as draft",
    title: "Restore this training",
    description:
      "It comes back as a draft, not as live content. Publish it again deliberately when it is ready.",
    confirm: "Restore",
  },
};

interface DraftState {
  ownerOffice: string;
  title: string;
  summary: string;
  body: string;
  category: string;
  contentType: string;
  toolCode: string;
  estimatedMinutes: string;
  externalUrl: string;
  embedUrl: string;
  isRequired: boolean;
  publishAt: string;
  expiresAt: string;
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
  const [results, setResults] = useState<TrainingRecipientResult[]>([]);
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
      fetch(`${routes.training_recipient_search()}?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      })
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

function TrainingWorkspacePage() {
  const {
    content,
    officeOptions,
    categoryOptions,
    contentTypeOptions,
    toolOptions,
    audienceOptions,
    capabilities,
    preview,
    errors,
  } = usePage<TrainingWorkspacePageProps>().props;

  const editing = content !== null;
  const [draft, setDraft] = useState<DraftState>(() =>
    initialDraft(content, officeOptions[0]?.value),
  );
  const [people, setPeople] = useState<{ id: number; name: string }[]>(() =>
    (content?.audience ?? [])
      .filter((entry) => entry.kind === "user" && entry.userId !== null)
      .map((entry) => ({ id: entry.userId as number, name: entry.label })),
  );
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const lifecycleActions = useMemo(
    () => (content ? (ACTIONS_BY_STATE[content.lifecycle.code] ?? []) : []),
    [content],
  );

  const checklist = content?.validation;
  const publishBlocked = checklist ? !checklist.isPublishable : false;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const payload: Record<string, string | string[]> = {
      owner_office: draft.ownerOffice,
      title: draft.title,
      summary: draft.summary,
      body: draft.body,
      category: draft.category,
      content_type: draft.contentType,
      tool_code: draft.toolCode,
      estimated_minutes: draft.estimatedMinutes,
      external_url: draft.externalUrl,
      embed_url: draft.embedUrl,
      publish_at: draft.publishAt,
      expires_at: draft.expiresAt,
      audience_roles: draft.roles,
      audience_regions: draft.regions.map(String),
      audience_offices: draft.offices.map(String),
      audience_users: people.map((person) => String(person.id)),
      expected_version: content?.version ?? "",
    };
    if (draft.company) {
      payload.audience_company = "on";
    }
    if (draft.isRequired) {
      payload.is_required = "on";
    }
    router.post(
      editing ? routes.training_update(content.id) : routes.training_create(),
      toFormData(payload),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function runAction(action: string) {
    setSubmitting(true);
    setPendingAction(null);
    router.post(
      routes.training_lifecycle(content?.id ?? 0),
      toFormData({ action, expected_version: content?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function duplicateVersion() {
    setSubmitting(true);
    router.post(
      routes.training_duplicate_version(content?.id ?? 0),
      toFormData({ expected_version: content?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function previewAs(patch: { office?: string; role?: string }) {
    router.get(
      routes.training_edit(content?.id ?? 0),
      {
        previewOffice:
          patch.office ?? (preview?.officeId != null ? String(preview.officeId) : ""),
        previewRole: patch.role ?? preview?.roleCode ?? "",
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:items-start">
      <Head title={editing ? content.title : "New training"} />

      <div className="grid gap-8">
        {editing ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border px-4 py-3">
            <Badge variant="secondary">{content.versionLabel}</Badge>
            <span className="text-muted-foreground text-sm">
              Version {content.versionNumber} of this training item.
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
          title={editing ? content.title : "New training"}
          description={
            editing
              ? "Saving changes never notifies anybody. Publishing and archiving are separate, deliberate steps."
              : "Write the content first. It reaches nobody until somebody with the publication grant publishes it."
          }
          meta={
            editing ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  status={{
                    label: content.lifecycle.label,
                    tone: content.lifecycle.tone,
                  }}
                />
                <span className="text-muted-foreground text-xs">
                  Last edited {formatMoment(content.updatedAt)}
                  {content.updatedBy ? ` by ${content.updatedBy}` : ""}
                </span>
              </span>
            ) : undefined
          }
          actions={
            editing ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={content.mediaHref}>
                  <Images className="size-4" aria-hidden />
                  Media &amp; files
                </Link>
              </Button>
            ) : undefined
          }
        />

        <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

        <form className="grid gap-8" onSubmit={submit} noValidate>
          <SurfaceCard>
            <PanelHeader divided title="Content" />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="title" required>
                  Title
                </FormLabel>
                <Input
                  id="title"
                  value={draft.title}
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
                <Input
                  id="summary"
                  value={draft.summary}
                  onChange={(event) =>
                    setDraft({ ...draft, summary: event.target.value })
                  }
                  {...fieldA11yProps("summary", errors, "summary_help")}
                />
                <FormDescription id="summary_help">
                  One line, shown under the headline in the library.
                </FormDescription>
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
                <FormFieldError message={firstFieldError(errors, "owner_office")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="category" required>
                  Category
                </FormLabel>
                <Select
                  value={draft.category || "none"}
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
                <FormLabel htmlFor="content_type" required>
                  Content type
                </FormLabel>
                <Select
                  value={draft.contentType || "none"}
                  onValueChange={(value) =>
                    setDraft({ ...draft, contentType: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="content_type">
                    <SelectValue placeholder="Choose a type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not chosen yet</SelectItem>
                    {contentTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormFieldError message={firstFieldError(errors, "content_type")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="tool_code" optional>
                  Tool
                </FormLabel>
                <Select
                  value={draft.toolCode || "none"}
                  onValueChange={(value) =>
                    setDraft({ ...draft, toolCode: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="tool_code">
                    <SelectValue placeholder="No tool linked" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No tool linked</SelectItem>
                    {toolOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription id="tool_code_help">
                  For tool onboarding content only.
                </FormDescription>
                <FormFieldError message={firstFieldError(errors, "tool_code")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="estimated_minutes" optional>
                  Estimated minutes
                </FormLabel>
                <Input
                  id="estimated_minutes"
                  type="number"
                  min={1}
                  value={draft.estimatedMinutes}
                  onChange={(event) =>
                    setDraft({ ...draft, estimatedMinutes: event.target.value })
                  }
                  {...fieldA11yProps("estimated_minutes", errors)}
                />
                <FormFieldError
                  message={firstFieldError(errors, "estimated_minutes")}
                />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="external_url" optional>
                  External link
                </FormLabel>
                <Input
                  id="external_url"
                  type="url"
                  inputMode="url"
                  value={draft.externalUrl}
                  onChange={(event) =>
                    setDraft({ ...draft, externalUrl: event.target.value })
                  }
                  {...fieldA11yProps("external_url", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "external_url")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="embed_url" optional>
                  Video embed URL
                </FormLabel>
                <Input
                  id="embed_url"
                  type="url"
                  inputMode="url"
                  value={draft.embedUrl}
                  onChange={(event) =>
                    setDraft({ ...draft, embedUrl: event.target.value })
                  }
                  {...fieldA11yProps("embed_url", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "embed_url")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <CheckboxRow
                  id="is_required"
                  label="Required training for the matched audience"
                  checked={draft.isRequired}
                  onChange={(checked) => setDraft({ ...draft, isRequired: checked })}
                />
                <FormFieldError message={firstFieldError(errors, "is_required")} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Window"
              description="Leave both empty for content that goes live on publish and never expires."
            />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="publish_at" optional>
                  Publishes at
                </FormLabel>
                <Input
                  id="publish_at"
                  type="datetime-local"
                  value={draft.publishAt}
                  onChange={(event) =>
                    setDraft({ ...draft, publishAt: event.target.value })
                  }
                  {...fieldA11yProps("publish_at", errors, "publish_at_help")}
                />
                <FormDescription id="publish_at_help">
                  A future time here is what makes “Schedule” available.
                </FormDescription>
                <FormFieldError message={firstFieldError(errors, "publish_at")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="expires_at" optional>
                  Expires at
                </FormLabel>
                <Input
                  id="expires_at"
                  type="datetime-local"
                  value={draft.expiresAt}
                  onChange={(event) =>
                    setDraft({ ...draft, expiresAt: event.target.value })
                  }
                  {...fieldA11yProps("expires_at", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "expires_at")} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Audience"
              description="Choices combine as a union: anyone matching any one of them receives it. Only what you may address is listed."
            />
            <SurfaceCardContent className="grid gap-6">
              <fieldset className="grid gap-2">
                <legend className="text-sm font-semibold">Everyone</legend>
                <CheckboxRow
                  id="audience_company"
                  label="Everyone at the brokerage"
                  checked={draft.company}
                  onChange={(checked) => setDraft({ ...draft, company: checked })}
                />
                {!audienceOptions.canTargetCompany ? (
                  <FormDescription>
                    Only a brokerage-wide administrator can address everyone, so this
                    will be refused for your grant.
                  </FormDescription>
                ) : null}
                <FormFieldError message={firstFieldError(errors, "audience_company")} />
              </fieldset>

              {audienceOptions.roles.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-sm font-semibold">Roles</legend>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {audienceOptions.roles.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`role_${option.value}`}
                        label={option.label}
                        checked={draft.roles.includes(option.value)}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            roles: toggle(draft.roles, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                  <FormFieldError message={firstFieldError(errors, "audience_roles")} />
                </fieldset>
              ) : null}

              {audienceOptions.regions.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-sm font-semibold">
                    Regions and everything under them
                  </legend>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {audienceOptions.regions.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`region_${option.value}`}
                        label={option.label}
                        checked={draft.regions.includes(option.value)}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            regions: toggle(draft.regions, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                  <FormFieldError
                    message={firstFieldError(errors, "audience_regions")}
                  />
                </fieldset>
              ) : null}

              {audienceOptions.offices.length > 0 ? (
                <fieldset className="grid gap-2">
                  <legend className="text-sm font-semibold">Single offices</legend>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {audienceOptions.offices.map((option) => (
                      <CheckboxRow
                        key={option.value}
                        id={`office_${option.value}`}
                        label={option.label}
                        checked={draft.offices.includes(option.value)}
                        onChange={() =>
                          setDraft({
                            ...draft,
                            offices: toggle(draft.offices, option.value),
                          })
                        }
                      />
                    ))}
                  </div>
                  <FormFieldError
                    message={firstFieldError(errors, "audience_offices")}
                  />
                </fieldset>
              ) : null}

              <fieldset className="grid gap-2">
                <legend className="text-sm font-semibold">Named people</legend>
                <RecipientPicker
                  chosen={people}
                  onToggle={(person) =>
                    setPeople(
                      people.some((item) => item.id === person.id)
                        ? people.filter((item) => item.id !== person.id)
                        : [...people, person],
                    )
                  }
                />
                <FormFieldError message={firstFieldError(errors, "audience_users")} />
              </fieldset>
            </SurfaceCardContent>
          </SurfaceCard>

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
              <Link href={routes.admin_training()}>Cancel</Link>
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

        {editing && capabilities.canPublish ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Lifecycle"
              description="Each move is explicit, audited, and refused if somebody else changed the record first."
            />
            <SurfaceCardContent className="flex flex-wrap gap-2">
              {lifecycleActions.map((action) => (
                <Button
                  key={action}
                  type="button"
                  variant={action === "publish" ? "default" : "outline"}
                  disabled={submitting || (action === "publish" && publishBlocked)}
                  onClick={() => setPendingAction(action)}
                >
                  {action === "publish" ? (
                    <Send className="size-4" aria-hidden />
                  ) : action === "schedule" ? (
                    <CalendarClock className="size-4" aria-hidden />
                  ) : (
                    <Undo2 className="size-4" aria-hidden />
                  )}
                  {ACTION_COPY[action].label}
                </Button>
              ))}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : editing ? (
          <p className="text-muted-foreground text-sm">
            You can edit this draft. Publishing, scheduling, and archiving need the
            publication grant.
          </p>
        ) : null}

        {editing && preview ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Preview"
              description="Exactly what a learner sees, drawn by the reader-facing renderer. Previewing never makes the draft reachable."
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
                    ? "This learner would receive the training."
                    : "This learner would not receive the training."}
                  {preview.reach.hasNamedRecipients ? (
                    <span className="text-muted-foreground">
                      Individually named people are addressed separately and are not
                      covered by an office-and-role preview.
                    </span>
                  ) : null}
                </p>
              ) : (
                <EmptyState
                  icon={Eye}
                  title="Choose a learner"
                  description="Pick an office or a role above to check whether the audience reaches them."
                />
              )}

              <TrainingArticle content={preview.article} />
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && content.history.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Publication history"
              description="Read from the audit trail — the same record governance answers from."
            />
            <SurfaceCardContent>
              <Timeline
                items={content.history.map((entry) => ({
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

        {editing ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Usage"
              description="Completion counts for audience-matched learners."
            />
            <SurfaceCardContent className="grid gap-3 sm:grid-cols-4">
              <div>
                <p className="text-muted-foreground text-xs">Recipients</p>
                <p className="text-lg font-semibold tabular-nums">
                  {content.usage.recipientEstimate}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Completed</p>
                <p className="text-lg font-semibold tabular-nums">
                  {content.usage.completed}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">In progress</p>
                <p className="text-lg font-semibold tabular-nums">
                  {content.usage.inProgress}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Not started</p>
                <p className="text-lg font-semibold tabular-nums">
                  {content.usage.notStarted}
                </p>
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Correct progress"
              description="Scoped correction with a required reason for the audit trail."
            />
            <SurfaceCardContent>
              <form
                className="grid gap-4 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const form = new FormData(event.currentTarget);
                  router.post(
                    routes.training_progress_correct(content.id),
                    {
                      learnerId: form.get("learnerId"),
                      status: form.get("status"),
                      reason: form.get("reason"),
                      kind: form.get("kind") || "progress",
                    },
                    { preserveScroll: true },
                  );
                }}
              >
                <FormField>
                  <FormLabel htmlFor="correct-learner">Learner id</FormLabel>
                  <Input id="correct-learner" name="learnerId" required />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="correct-status">Status</FormLabel>
                  <select
                    id="correct-status"
                    name="status"
                    defaultValue="completed"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  >
                    <option value="not_started">Not started</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">Completed</option>
                    <option value="registered">Registered</option>
                    <option value="attended">Attended</option>
                    <option value="cancelled">Cancelled</option>
                    <option value="no_show">No show</option>
                  </select>
                </FormField>
                <FormField className="sm:col-span-2">
                  <FormLabel htmlFor="correct-kind">Correction kind</FormLabel>
                  <select
                    id="correct-kind"
                    name="kind"
                    defaultValue="progress"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  >
                    <option value="progress">Progress</option>
                    <option value="attendance">Attendance</option>
                  </select>
                </FormField>
                <FormField className="sm:col-span-2">
                  <FormLabel htmlFor="correct-reason">Reason</FormLabel>
                  <Textarea id="correct-reason" name="reason" required rows={3} />
                </FormField>
                <div className="sm:col-span-2">
                  <Button type="submit" size="sm">
                    Save correction
                  </Button>
                </div>
              </form>
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
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={submitting}>
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="button"
              disabled={submitting || (pendingAction === "publish" && publishBlocked)}
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
  content: TrainingAdminDetail | null,
  fallbackOffice: number | undefined,
): DraftState {
  const audience = content?.audience ?? [];
  return {
    ownerOffice: String(content?.ownerOffice.id ?? fallbackOffice ?? ""),
    title: content?.title ?? "",
    summary: content?.summary ?? "",
    body: content?.body ?? "",
    category: content?.categoryCode ?? "",
    contentType: content?.contentTypeCode ?? "",
    toolCode: content?.toolCode ?? "",
    estimatedMinutes:
      content?.estimatedMinutes != null ? String(content.estimatedMinutes) : "",
    externalUrl: content?.externalUrl ?? "",
    embedUrl: content?.embedUrl ?? "",
    isRequired: content?.isRequired ?? false,
    publishAt: localDateTime(content?.publishAt ?? null),
    expiresAt: localDateTime(content?.expiresAt ?? null),
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

export default function TrainingWorkspace() {
  return (
    <PermissionRequired permission={MANAGE}>
      <TrainingWorkspacePage />
    </PermissionRequired>
  );
}

TrainingWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Training",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Training", href: routes.admin_training() },
        ],
      },
      variant: "standard",
    },
  ] as const;
