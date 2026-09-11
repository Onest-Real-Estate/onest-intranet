import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Copy,
  Download,
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
  MarketingAdminDetail,
  MarketingRecipientResult,
  MarketingWorkspacePageProps,
} from "@/types";

const MANAGE = { all: ["web.manage_marketing_resources"] };

const FIELD_LABELS: Record<string, string> = {
  owner_office: "Owning office",
  title: "Title",
  description: "Description",
  usage_instructions: "Usage instructions",
  category: "Category",
  asset_type: "Asset type",
  publish_at: "Publishes at",
  expires_at: "Expires at",
  jurisdiction_state_codes: "Jurisdictions",
  brand_codes: "Brands",
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
    title: "Publish this asset",
    description:
      "It becomes readable immediately by everyone the audience reaches. Check the preview first.",
    confirm: "Publish",
  },
  schedule: {
    label: "Schedule",
    title: "Schedule this asset",
    description:
      "It stays hidden until the publish time you set, then appears on its own.",
    confirm: "Schedule",
  },
  unpublish: {
    label: "Return to draft",
    title: "Return this asset to draft",
    description:
      "It leaves the library straight away and the publication date is cleared.",
    confirm: "Return to draft",
  },
  archive: {
    label: "Archive",
    title: "Archive this asset",
    description:
      "It leaves the library for good. The record, its files, and its history are kept.",
    confirm: "Archive",
  },
  restore: {
    label: "Restore as draft",
    title: "Restore this asset",
    description:
      "It comes back as a draft, not as live content. Publish it again deliberately when it is ready.",
    confirm: "Restore",
  },
};

interface DraftState {
  ownerOffice: string;
  title: string;
  description: string;
  usageInstructions: string;
  category: string;
  assetType: string;
  publishAt: string;
  expiresAt: string;
  jurisdictionStateCodes: string;
  brandCodes: string;
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
  const [results, setResults] = useState<MarketingRecipientResult[]>([]);
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
      fetch(`${routes.marketing_recipient_search()}?q=${encodeURIComponent(query)}`, {
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

function MarketingWorkspacePage() {
  const {
    asset,
    officeOptions,
    categoryOptions,
    assetTypeOptions,
    audienceOptions,
    capabilities,
    preview,
    errors,
  } = usePage<MarketingWorkspacePageProps>().props;

  const editing = asset !== null;
  const [draft, setDraft] = useState<DraftState>(() =>
    initialDraft(asset, officeOptions[0]?.value),
  );
  const [people, setPeople] = useState<{ id: number; name: string }[]>(() =>
    (asset?.audience ?? [])
      .filter((entry) => entry.kind === "user" && entry.userId !== null)
      .map((entry) => ({ id: entry.userId as number, name: entry.label })),
  );
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const lifecycleActions = useMemo(
    () => (asset ? (ACTIONS_BY_STATE[asset.lifecycle.code] ?? []) : []),
    [asset],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    const payload: Record<string, string | string[]> = {
      owner_office: draft.ownerOffice,
      title: draft.title,
      description: draft.description,
      usage_instructions: draft.usageInstructions,
      category: draft.category,
      asset_type: draft.assetType,
      publish_at: draft.publishAt,
      expires_at: draft.expiresAt,
      jurisdiction_state_codes: draft.jurisdictionStateCodes,
      brand_codes: draft.brandCodes,
      display_order: draft.displayOrder,
      audience_roles: draft.roles,
      audience_regions: draft.regions.map(String),
      audience_offices: draft.offices.map(String),
      audience_users: people.map((person) => String(person.id)),
      expected_version: asset?.version ?? "",
    };
    if (draft.company) {
      payload.audience_company = "on";
    }
    router.post(
      editing ? routes.marketing_update(asset.id) : routes.marketing_create(),
      toFormData(payload),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function runAction(action: string) {
    setSubmitting(true);
    setPendingAction(null);
    router.post(
      routes.marketing_lifecycle(asset?.id ?? 0),
      toFormData({ action, expected_version: asset?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function duplicateVersion() {
    setSubmitting(true);
    router.post(
      routes.marketing_duplicate_version(asset?.id ?? 0),
      toFormData({ expected_version: asset?.version ?? "" }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  function previewAs(patch: { office?: string; role?: string }) {
    router.get(
      routes.marketing_edit(asset?.id ?? 0),
      {
        previewOffice:
          patch.office ?? (preview?.officeId != null ? String(preview.officeId) : ""),
        previewRole: patch.role ?? preview?.roleCode ?? "",
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const checklist = asset?.validation;
  const showSources =
    capabilities.canDownloadSources && (asset?.files.sources.length ?? 0) > 0;

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:items-start">
      <Head title={editing ? asset.title : "New marketing asset"} />

      <div className="grid gap-8">
        {editing ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border px-4 py-3">
            <Badge variant="secondary">{asset.versionLabel}</Badge>
            <span className="text-muted-foreground text-sm">
              Version {asset.versionNumber} of this marketing asset.
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
          title={editing ? asset.title : "New marketing asset"}
          description={
            editing
              ? "Saving changes never notifies anybody. Publishing and archiving are separate, deliberate steps."
              : "Describe the asset first. It reaches nobody until somebody with the publication grant publishes it."
          }
          meta={
            editing ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  status={{
                    label: asset.lifecycle.label,
                    tone: asset.lifecycle.tone,
                  }}
                />
                <span className="text-muted-foreground text-xs">
                  Last edited {formatMoment(asset.updatedAt)}
                  {asset.updatedBy ? ` by ${asset.updatedBy}` : ""}
                </span>
              </span>
            ) : undefined
          }
          actions={
            editing ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={routes.marketing_media_manager(asset.id)}>
                  <Images className="size-4" aria-hidden />
                  Export &amp; source files
                </Link>
              </Button>
            ) : undefined
          }
        />

        <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

        <form className="grid gap-8" onSubmit={submit} noValidate>
          <SurfaceCard>
            <PanelHeader divided title="The asset" />
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
                <FormLabel htmlFor="description" optional>
                  Description
                </FormLabel>
                <Textarea
                  id="description"
                  rows={3}
                  value={draft.description}
                  onChange={(event) =>
                    setDraft({ ...draft, description: event.target.value })
                  }
                  {...fieldA11yProps("description", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "description")} />
              </FormField>

              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="usage_instructions" optional>
                  Usage instructions
                </FormLabel>
                <Textarea
                  id="usage_instructions"
                  rows={4}
                  value={draft.usageInstructions}
                  onChange={(event) =>
                    setDraft({ ...draft, usageInstructions: event.target.value })
                  }
                  {...fieldA11yProps("usage_instructions", errors)}
                />
                <FormFieldError
                  message={firstFieldError(errors, "usage_instructions")}
                />
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
                <FormLabel htmlFor="asset_type" required>
                  Asset type
                </FormLabel>
                <Select
                  value={draft.assetType || "none"}
                  onValueChange={(value) =>
                    setDraft({ ...draft, assetType: value === "none" ? "" : value })
                  }
                >
                  <SelectTrigger id="asset_type">
                    <SelectValue placeholder="Choose a type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not chosen yet</SelectItem>
                    {assetTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormFieldError message={firstFieldError(errors, "asset_type")} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="display_order" optional>
                  Display order
                </FormLabel>
                <Input
                  id="display_order"
                  type="number"
                  value={draft.displayOrder}
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
              description="Leave both empty for an asset that goes live on publish and never expires."
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
              title="Jurisdiction & brand"
              description="Empty means all states or all brands. Codes are space- or comma-separated."
            />
            <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="jurisdiction_state_codes" optional>
                  State codes
                </FormLabel>
                <Input
                  id="jurisdiction_state_codes"
                  value={draft.jurisdictionStateCodes}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      jurisdictionStateCodes: event.target.value,
                    })
                  }
                  placeholder="VA MD DC"
                  {...fieldA11yProps("jurisdiction_state_codes", errors)}
                />
                <FormFieldError
                  message={firstFieldError(errors, "jurisdiction_state_codes")}
                />
              </FormField>

              <FormField>
                <FormLabel htmlFor="brand_codes" optional>
                  Brand codes
                </FormLabel>
                <Input
                  id="brand_codes"
                  value={draft.brandCodes}
                  onChange={(event) =>
                    setDraft({ ...draft, brandCodes: event.target.value })
                  }
                  placeholder="onest"
                  {...fieldA11yProps("brand_codes", errors)}
                />
                <FormFieldError message={firstFieldError(errors, "brand_codes")} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Audience"
              description="Choices combine as a union: anyone matching any one of them can see it."
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
              <Link href={routes.admin_marketing_resources()}>Cancel</Link>
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
              description="Exports are what recipients download. Sources stay with administrators who hold the download grant."
            />
            <SurfaceCardContent className="grid gap-3">
              <p className="text-muted-foreground text-sm">
                {asset.files.exports.length} export
                {asset.files.exports.length === 1 ? "" : "s"}
                {showSources
                  ? ` · ${asset.files.sources.length} source${asset.files.sources.length === 1 ? "" : "s"}`
                  : ""}
              </p>
              {asset.files.exports.length > 0 ? (
                <ul className="grid gap-2">
                  {asset.files.exports.map((file) => (
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
              {showSources ? (
                <ul className="grid gap-2" aria-label="Source files">
                  {asset.files.sources.map((file) => (
                    <li
                      key={file.id}
                      className="flex items-center justify-between gap-2 text-sm"
                    >
                      <span className="truncate">{file.displayName}</span>
                      {file.url ? (
                        <Button variant="ghost" size="sm" asChild>
                          <a href={file.url} download>
                            <Download className="size-3.5" aria-hidden />
                            Source
                          </a>
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              <Button variant="outline" size="sm" asChild>
                <Link href={routes.marketing_media_manager(asset.id)}>
                  Manage files
                </Link>
              </Button>
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
                  disabled={
                    submitting ||
                    (action === "publish" && !checklist?.isPublishable) ||
                    (action === "schedule" && !draft.publishAt)
                  }
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
                    ? "This reader would see the asset."
                    : "This reader would not see the asset."}
                </p>
              ) : (
                <EmptyState
                  icon={Eye}
                  title="Choose a reader"
                  description="Pick an office or a role above to check whether the audience reaches them."
                />
              )}

              <div className="grid gap-2 rounded-lg border p-4">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge
                    status={{
                      label: preview.article.assetType.label,
                      tone: toStatusTone(preview.article.assetType.tone),
                    }}
                  />
                  {preview.article.category ? (
                    <StatusBadge
                      status={{
                        label: preview.article.category.label,
                        tone: toStatusTone(preview.article.category.tone),
                      }}
                    />
                  ) : null}
                </div>
                <h3 className="text-base font-semibold">{preview.article.title}</h3>
                {preview.article.description ? (
                  <p className="text-muted-foreground text-sm">
                    {preview.article.description}
                  </p>
                ) : null}
                <p className="text-muted-foreground text-xs">
                  {preview.article.exportCount} export
                  {preview.article.exportCount === 1 ? "" : "s"} available to download
                </p>
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {editing && asset.history.length > 0 ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Publication history"
              description="Read from the audit trail — the same record governance answers from."
            />
            <SurfaceCardContent>
              <Timeline
                items={asset.history.map((entry) => ({
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
  asset: MarketingAdminDetail | null,
  fallbackOffice: number | undefined,
): DraftState {
  const audience = asset?.audience ?? [];
  return {
    ownerOffice: String(asset?.ownerOffice.id ?? fallbackOffice ?? ""),
    title: asset?.title ?? "",
    description: asset?.description ?? "",
    usageInstructions: asset?.usageInstructions ?? "",
    category: asset?.categoryCode ?? "",
    assetType: asset?.assetTypeCode ?? "",
    publishAt: localDateTime(asset?.publishAt ?? null),
    expiresAt: localDateTime(asset?.expiresAt ?? null),
    jurisdictionStateCodes: (asset?.jurisdictionStateCodes ?? []).join(" "),
    brandCodes: (asset?.brandCodes ?? []).join(" "),
    displayOrder: asset?.displayOrder != null ? String(asset.displayOrder) : "",
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

export default function MarketingWorkspace() {
  return (
    <PermissionRequired permission={MANAGE}>
      <MarketingWorkspacePage />
    </PermissionRequired>
  );
}

MarketingWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Marketing resources",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Marketing resources",
            href: routes.admin_marketing_resources(),
          },
        ],
      },
      variant: "standard",
    },
  ] as const;
