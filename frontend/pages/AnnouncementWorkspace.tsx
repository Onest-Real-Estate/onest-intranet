import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Eye,
  Images,
  Send,
  Undo2,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { AnnouncementArticle } from "@/components/announcements/AnnouncementArticle";
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
  AnnouncementAdminDetail,
  AnnouncementRecipientResult,
  AnnouncementWorkspacePageProps,
} from "@/types";

const MANAGE = { all: ["web.manage_announcements"] };

const FIELD_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  title: "Title",
  summary: "Summary",
  body: "Body",
  category: "Category",
  priority: "Priority",
  publish_at: "Publishes at",
  expires_at: "Expires at",
  cta_label: "Button text",
  cta_url: "Button link",
  audience_company: "Audience",
  audience_roles: "Roles",
  audience_regions: "Regions",
  audience_offices: "Offices",
  audience_users: "Named people",
};

/** Lifecycle moves offered for each derived state, in the order they belong. */
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
    title: "Publish this announcement",
    description:
      "It becomes readable immediately by everyone the audience reaches. Check the preview first.",
    confirm: "Publish",
  },
  schedule: {
    label: "Schedule",
    title: "Schedule this announcement",
    description:
      "It stays hidden until the publish time you set, then appears on its own. Nobody is notified before then.",
    confirm: "Schedule",
  },
  unpublish: {
    label: "Return to draft",
    title: "Return this announcement to draft",
    description:
      "It leaves the feed straight away and the publication date is cleared, so a later publish dates itself honestly.",
    confirm: "Return to draft",
  },
  archive: {
    label: "Archive",
    title: "Archive this announcement",
    description:
      "It leaves the feed for good. The record, its files, and its history are kept, and any pin is removed.",
    confirm: "Archive",
  },
  restore: {
    label: "Restore as draft",
    title: "Restore this announcement",
    description:
      "It comes back as a draft, not as a live notice. Publish it again deliberately when it is ready.",
    confirm: "Restore",
  },
};

interface DraftState {
  ownerOffice: string;
  title: string;
  summary: string;
  body: string;
  category: string;
  priority: string;
  publishAt: string;
  expiresAt: string;
  ctaLabel: string;
  ctaUrl: string;
  company: boolean;
  roles: string[];
  regions: number[];
  offices: number[];
  users: number[];
}

function localDateTime(value: string | null): string {
  if (!value) {
    return "";
  }
  // `datetime-local` wants `YYYY-MM-DDTHH:mm` with no zone suffix.
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

/**
 * Individual recipients, looked up through the scoped typeahead.
 *
 * The endpoint answers only from the actor's administered set and returns
 * nothing below its minimum query length, so this control cannot be used to
 * page through the directory — which is why it queries the server rather than
 * receiving a list of people up front.
 */
function RecipientPicker({
  chosen,
  onToggle,
}: {
  chosen: { id: number; name: string }[];
  onToggle: (person: { id: number; name: string }) => void;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<AnnouncementRecipientResult[]>([]);
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
        `${routes.announcement_recipient_search()}?q=${encodeURIComponent(query)}`,
        { signal: controller.signal, headers: { Accept: "application/json" } },
      )
        .then((response) => (response.ok ? response.json() : { results: [] }))
        .then((data) => setResults(data.results ?? []))
        // An aborted or failed lookup leaves the list as it was; the field is
        // an optional convenience, not something worth an error banner.
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

/**
 * Compose one announcement, check it, and move it through its lifecycle.
 *
 * Three rules from the server are mirrored here so nobody is surprised by a
 * rejection: the audience picker offers only what this actor may address, the
 * lifecycle buttons appear only with the publication grant, and the outstanding
 * checklist is shown before publishing rather than after it fails. None of it
 * is load-bearing — the server refuses the same things whatever this renders.
 */
function AnnouncementWorkspacePage() {
  const {
    announcement,
    officeOptions,
    categoryOptions,
    priorityOptions,
    audienceOptions,
    capabilities,
    preview,
    errors,
  } = usePage<AnnouncementWorkspacePageProps>().props;

  const editing = announcement !== null;
  const [draft, setDraft] = useState<DraftState>(() =>
    initialDraft(announcement, officeOptions[0]?.value),
  );
  const [people, setPeople] = useState<{ id: number; name: string }[]>(() =>
    (announcement?.audience ?? [])
      .filter((entry) => entry.kind === "user" && entry.userId !== null)
      .map((entry) => ({ id: entry.userId as number, name: entry.label })),
  );
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const lifecycleActions = useMemo(
    () => (announcement ? (ACTIONS_BY_STATE[announcement.lifecycle.code] ?? []) : []),
    [announcement],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const payload: Record<string, string | string[]> = {
      owner_office: draft.ownerOffice,
      title: draft.title,
      summary: draft.summary,
      body: draft.body,
      category: draft.category,
      priority: draft.priority,
      publish_at: draft.publishAt,
      expires_at: draft.expiresAt,
      cta_label: draft.ctaLabel,
      cta_url: draft.ctaUrl,
      audience_roles: draft.roles,
      audience_regions: draft.regions.map(String),
      audience_offices: draft.offices.map(String),
      audience_users: people.map((person) => String(person.id)),
      expected_version: announcement?.version ?? "",
    };
    if (draft.company) {
      payload.audience_company = "on";
    }
    router.post(
      editing
        ? routes.announcement_update(announcement.id)
        : routes.announcement_create(),
      // FormData, not a plain object: Inertia would send the latter as a JSON
      // body, which never reaches Django's request.POST. See lib/form-data.ts.
      toFormData(payload),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function runAction(action: string) {
    setSubmitting(true);
    setPendingAction(null);
    router.post(
      routes.announcement_lifecycle(announcement?.id ?? 0),
      toFormData({ action, expected_version: announcement?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function previewAs(patch: { office?: string; role?: string }) {
    router.get(
      routes.announcement_edit(announcement?.id ?? 0),
      {
        previewOffice:
          patch.office ?? (preview?.officeId != null ? String(preview.officeId) : ""),
        previewRole: patch.role ?? preview?.roleCode ?? "",
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const checklist = announcement?.validation;

  return (
    <div className="grid gap-10 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:items-start">
      <Head title={editing ? announcement.title : "New announcement"} />

      <div className="grid gap-8">
        <PageHeader
          title={editing ? announcement.title : "New announcement"}
          description={
            editing
              ? "Saving changes never notifies anybody. Publishing and archiving are separate, deliberate steps."
              : "Write the notice first. It reaches nobody until somebody with the publication grant publishes it."
          }
          meta={
            editing ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  status={{
                    label: announcement.lifecycle.label,
                    tone: announcement.lifecycle.tone,
                  }}
                />
                <span className="text-muted-foreground text-xs">
                  Last edited {formatMoment(announcement.updatedAt)}
                  {announcement.updatedBy ? ` by ${announcement.updatedBy}` : ""}
                </span>
              </span>
            ) : undefined
          }
          actions={
            editing ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={announcement.mediaHref}>
                  <Images className="size-4" aria-hidden />
                  Hero &amp; files
                </Link>
              </Button>
            ) : undefined
          }
        />

        <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

        <form className="grid gap-8" onSubmit={submit} noValidate>
          <SurfaceCard>
            <PanelHeader divided title="The notice" />
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
                  One line, shown under the headline in the feed.
                </FormDescription>
                <FormFieldError message={firstFieldError(errors, "summary")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="body" required>
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
                <FormDescription id="owner_office_help">
                  Who is publishing. Permanent once saved, and never widens the audience
                  on its own.
                </FormDescription>
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
                <FormLabel htmlFor="priority" required>
                  Priority
                </FormLabel>
                <Select
                  value={draft.priority || "none"}
                  onValueChange={(value) =>
                    setDraft({ ...draft, priority: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="priority">
                    <SelectValue placeholder="Choose a priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not chosen yet</SelectItem>
                    {priorityOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription id="priority_help">
                  Decides ordering and whether a notification is sent. Never who can see
                  it.
                </FormDescription>
                <FormFieldError message={firstFieldError(errors, "priority")} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Window"
              description="Leave both empty for a notice that goes live on publish and never expires."
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
              title="Call to action"
              description="Optional button under the body. Give it both words and a link, or neither."
            />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="cta_label" optional>
                  Button text
                </FormLabel>
                <Input
                  id="cta_label"
                  value={draft.ctaLabel}
                  onChange={(event) =>
                    setDraft({ ...draft, ctaLabel: event.target.value })
                  }
                  {...fieldA11yProps("cta_label", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "cta_label")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="cta_url" optional>
                  Button link
                </FormLabel>
                <Input
                  id="cta_url"
                  type="url"
                  inputMode="url"
                  value={draft.ctaUrl}
                  onChange={(event) =>
                    setDraft({ ...draft, ctaUrl: event.target.value })
                  }
                  {...fieldA11yProps("cta_url", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "cta_url")} />
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
              <Link href={routes.admin_announcements()}>Cancel</Link>
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
                  disabled={submitting}
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
              description="Exactly what a recipient sees, drawn by the reader-facing renderer. Previewing never makes the draft reachable."
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
                    ? "This reader would receive the announcement."
                    : "This reader would not receive the announcement."}
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
                  title="Choose a reader"
                  description="Pick an office or a role above to check whether the audience reaches them."
                />
              )}

              <AnnouncementArticle
                announcement={preview.article}
                headingLevel="h3"
                showAudience={false}
              />
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && announcement.history.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Publication history"
              description="Read from the audit trail — the same record governance answers from."
            />
            <SurfaceCardContent>
              <Timeline
                items={announcement.history.map((entry) => ({
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
  announcement: AnnouncementAdminDetail | null,
  fallbackOffice: number | undefined,
): DraftState {
  const audience = announcement?.audience ?? [];
  return {
    ownerOffice: String(announcement?.ownerOffice.id ?? fallbackOffice ?? ""),
    title: announcement?.title ?? "",
    summary: announcement?.summary ?? "",
    body: announcement?.body ?? "",
    category: announcement?.categoryCode ?? "",
    priority: announcement?.priorityCode ?? "",
    publishAt: localDateTime(announcement?.publishAt ?? null),
    expiresAt: localDateTime(announcement?.expiresAt ?? null),
    ctaLabel: announcement?.cta?.label ?? "",
    ctaUrl: announcement?.cta?.url ?? "",
    company: audience.some((entry) => entry.kind === "company"),
    roles: audience.filter((entry) => entry.kind === "role").map((entry) => entry.code),
    regions: audience
      .filter((entry) => entry.kind === "region" && entry.officeId !== null)
      .map((entry) => entry.officeId as number),
    offices: audience
      .filter((entry) => entry.kind === "office" && entry.officeId !== null)
      .map((entry) => entry.officeId as number),
    users: audience
      .filter((entry) => entry.kind === "user" && entry.userId !== null)
      .map((entry) => entry.userId as number),
  };
}

export default function AnnouncementWorkspace() {
  return (
    <PermissionRequired permission={MANAGE}>
      <AnnouncementWorkspacePage />
    </PermissionRequired>
  );
}

AnnouncementWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Announcements",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Announcements", href: routes.admin_announcements() },
        ],
      },
      variant: "standard",
    },
  ] as const;
